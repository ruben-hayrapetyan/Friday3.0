"""Quick-add: one line → the fields of an `add` (DESIGN §9.4). Times come out local, as the API speaks."""

import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from friday.core.dates import (
    MONTH_DAY,
    WEEKDAY_NAMES,
    next_weekday,
    parse_duration,
    parse_time_range,
    read_moment,
)
from friday.core.guess import guess_preset
from friday.core.recurrence import read_repeat
from friday.core.textnorm import plain_words
from friday.core.time import UNIT_MIN, format_local, local_midnight

# A repeat at a set time is a class only when it says so; "club meeting every tue 7pm" is an event.
CLASSLIKE = re.compile(
    r"\b([a-z]{2,5} ?\d{4}|lecture|lec|discussion|disc|recitation|section|seminar|lab|class)\b", re.IGNORECASE
)

TOKEN = re.compile(r'(?:after|before):"[^"]*"|\S+')
LENGTH = re.compile(r"^~([0-9.hm]+)(?:-([0-9.hm]+))?$")
BARE_LENGTH = re.compile(r"^\d+(\.\d+)?h(\d+m)?$|^\d+m$")  # `30m`, `2h`, `1.5h`, `1h30m`: a length without `~`
BARE_ELASTIC = re.compile(r"^\d+(\.\d+)?[hm]?-\d+(\.\d+)?[hm]$")  # `30-45m`, `1-2h`: never `3-4pm`, a time
REPEAT_WORDS = {
    "daily": "FREQ=DAILY",
    "weekly": "FREQ=WEEKLY",
    "weekdays": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "biweekly": "FREQ=WEEKLY;INTERVAL=2",
    "fortnightly": "FREQ=WEEKLY;INTERVAL=2",
    "monthly": "FREQ=MONTHLY",
    "yearly": "FREQ=YEARLY",
    "annually": "FREQ=YEARLY",
}
# Meals are routines, and their time range is when they may happen, not a fixed sitting.
MEAL = re.compile(r"\b(breakfast|brunch|lunch|dinner|supper|meal)s?\b", re.IGNORECASE)
FLEXIBLE_KINDS = {"Routine", "Habit", "Chore", "Errand"}
SCHOOLWORK = {"Assignment", "Exam prep", "Project", "Reading"}
PER_WINDOW = re.compile(r"^(\d+)x$")
TIMES_A_WEEK = {"once": 1, "twice": 2}  # "twice a week", like "2x a week"
A_WEEK = (("a", "week"), ("per", "week"), ("times", "a", "week"))
WEEKDAY_RANGE = re.compile(r"^([a-z]+)-([a-z]+)$")
ITEM_REF = re.compile(r"^t(\d+)$")
IMPORTANCE = {"!high": 5, "!low": 1} | {f"!{n}": n for n in range(1, 6)}
ENERGY = {"@deep", "@light", "@physical", "@social"}
END_OF_DAY = 23 * 60 + 59
DEFAULT_FIXED_LENGTH_MIN = 60


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str
    value: Any


@dataclass
class ParseResult:
    fields: dict[str, Any] = field(default_factory=dict)
    spans: list[Span] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Token:
    text: str
    start: int
    end: int

    @property
    def word(self) -> str:
        return self.text.lower()


def parse(
    text: str,
    now: datetime,
    day_start: int = 4 * 60,
    areas: Iterable[str] = (),
    presets: Iterable[str] = (),
    find_item: Callable[[str], int | None] | None = None,
) -> ParseResult:
    """Parse against the server's local `now`. `find_item` resolves `after:`/`before:` titles when given."""
    tokens = [Token(m[0], m.start(), m.end()) for m in TOKEN.finditer(text)]
    parser = Parser(tokens, now, day_start, list(areas), list(presets), find_item)
    parser.run()
    return parser.result


class Parser:
    def __init__(self, tokens: list[Token], now: datetime, day_start: int, areas: list[str],
                 presets: list[str], find_item: Callable[[str], int | None] | None):  # fmt: skip
        self.tokens = tokens
        self.words = [t.word for t in tokens]
        self.today = (now - timedelta(minutes=day_start)).date()
        self.day_start = day_start
        self.areas = areas
        self.presets = presets
        self.find_item = find_item
        self.result = ParseResult()
        self.fields = self.result.fields
        self.title_parts: list[str] = []
        self.bare_day = False  # a day with no `due`, as in "groceries sat": a to-do for that day, not coursework

    def run(self) -> None:
        i = 0
        while i < len(self.tokens):
            used = self.read_token(i)
            if used == 0:
                self.title_parts.append(self.tokens[i].text)
                used = 1
            i += used
        self.finish()

    def read_token(self, i: int) -> int:
        word = self.words[i]
        readers = {"due": self.read_due, "by": self.read_due, "from": self.read_from, "at": self.read_at,
                   "every": self.read_every}  # fmt: skip
        if word in readers:
            return readers[word](i)
        if word in REPEAT_WORDS and "rrule" not in self.fields:
            return self.mark(i, 1, "rrule", REPEAT_WORDS[word])
        if word == "between":
            return self.read_between(i)
        if BARE_ELASTIC.match(word):
            return self.read_length(i, bare=True)
        if word in IMPORTANCE:
            return self.mark(i, 1, "importance", IMPORTANCE[word])
        if word in ENERGY:
            return self.mark(i, 1, "energy", word[1:])
        if word == "maybe":
            return self.mark(i, 1, "certainty", "tentative")
        if word in ("one-sitting", "split"):
            return self.mark(i, 1, "shape", word.replace("-", "_"))
        if word.startswith("#") and len(word) > 1:
            return self.read_area(i)
        if word.startswith("+") and len(word) > 1:
            self.fields.setdefault("tags", []).append(word[1:])
            return self.span(i, 1, "tag", word[1:])
        if word.startswith("/") and len(word) > 1:
            return self.read_preset(i)
        if word.startswith("~"):
            return self.read_length(i)
        if word.startswith(("after:", "before:")):
            return self.read_dependency(i)
        if WEEKDAY_RANGE.match(word):
            return self.read_weekday_range(i)
        counted = PER_WINDOW.match(word) or word in TIMES_A_WEEK or word.isdigit()
        if counted and "rrule" not in self.fields and (used := self.read_times_a_week(i)):
            return used
        if word == "open" and i == len(self.words) - 1 and i > 0:
            return self.mark(i, 1, "amount", "open")  # last word only, so "open bank account" stays a title
        if parse_duration(word) is not None and BARE_LENGTH.match(word):
            return self.read_length(i, bare=True)
        return self.read_bare_moment(i)

    def span(self, i: int, used: int, kind: str, value: Any) -> int:
        self.result.spans.append(Span(self.tokens[i].start, self.tokens[i + used - 1].end, kind, value))
        return used

    def mark(self, i: int, used: int, name: str, value: Any) -> int:
        self.fields[name] = value
        return self.span(i, used, name, value)

    def moment_after(self, i: int) -> tuple[datetime, bool, int] | None:
        """The moment in the words after words[i], whether it had a time, and words used."""
        if i + 1 >= len(self.words):
            return None
        found = read_moment(self.words, i + 1, self.today)
        if not found:
            return None
        day, minute, used = found
        self.warn_if_ambiguous(self.words[i + 1], day)
        moment = local_midnight(day) + timedelta(minutes=minute if minute is not None else 0)
        return moment, minute is not None, used

    def read_due(self, i: int) -> int:
        found = self.moment_after(i)
        if not found:
            return 0
        moment, has_time, used = found
        due = moment if has_time else moment + timedelta(minutes=END_OF_DAY)
        return self.mark(i, used + 1, "due_local", format_local(due))

    def read_from(self, i: int) -> int:
        found = self.moment_after(i)
        if not found:
            return 0
        moment, has_time, used = found
        release = moment if has_time else moment + timedelta(minutes=self.day_start)
        return self.mark(i, used + 1, "release_local", format_local(release))

    def read_at(self, i: int) -> int:
        found = self.moment_after(i)
        if not found or not found[1]:
            return 0
        moment, _, used = found
        return self.fixed_at(i, moment, used + 1)

    def read_bare_moment(self, i: int) -> int:
        """A day with a time and no keyword, as in `call mom sat 3pm 30m`, is an `at`; a day alone, as in
        `groceries sat`, is when it's due."""
        found = read_moment(self.words, i, self.today)
        if not found:
            return 0
        day, minute, used = found
        if minute is None:
            if "due_local" in self.fields or "start_local" in self.fields:
                return 0
            self.bare_day = True
            return self.mark(i, used, "due_local", format_local(local_midnight(day) + timedelta(minutes=END_OF_DAY)))
        return self.fixed_at(i, local_midnight(day) + timedelta(minutes=minute), used)

    def read_times_a_week(self, i: int) -> int:
        """`3x a week`, `3 times a week`, `twice a week`: that many each week."""
        word = self.words[i]
        count = TIMES_A_WEEK.get(word) or (int(word) if word.isdigit() else int(word[:-1]))
        for tail in A_WEEK:
            if tuple(self.words[i + 1 : i + 1 + len(tail)]) == tail and not (word.isdigit() and tail[0] != "times"):
                self.fields["rrule"] = "FREQ=WEEKLY"
                if count > 1:
                    self.fields["per_window"] = count
                return self.span(i, 1 + len(tail), "repeat", "FREQ=WEEKLY")
        return 0

    def fixed_at(self, i: int, moment: datetime, used: int) -> int:
        """A fixed item from `moment`; its length is the time range it was given (`3-4pm`), a following `for DUR`,
        or a bare `DUR`."""
        length = None
        if span := parse_time_range(self.words[i + used - 1]):
            length = span[1] - span[0]
        elif i + used + 1 < len(self.words) and self.words[i + used] == "for":
            length = parse_duration(self.words[i + used + 1])
            if length is not None:
                used += 2
        elif i + used < len(self.words) and BARE_LENGTH.match(self.words[i + used]):
            length = parse_duration(self.words[i + used])
            if length is not None:
                used += 1
        if length is None:
            length = DEFAULT_FIXED_LENGTH_MIN
            self.result.warnings.append("no length given; 1 h assumed")
        self.fields["start_local"] = format_local(moment)
        self.fields["end_local"] = format_local(moment + timedelta(minutes=length))
        return self.span(i, used, "at", self.fields["start_local"])

    def read_every(self, i: int) -> int:
        if i + 1 >= len(self.words):
            return 0
        found = read_repeat(self.words, i + 1, self.today)
        if not found:
            return 0
        rule, used = found
        used += 1
        self.fields["rrule"] = rule
        if i + used < len(self.words) and (match := PER_WINDOW.match(self.words[i + used])):
            self.fields["per_window"] = int(match[1])
            used += 1
        return self.span(i, used, "repeat", rule)

    def read_area(self, i: int) -> int:
        typed = self.tokens[i].text[1:]
        known = next((a for a in self.areas if "".join(plain_words(a)) == "".join(plain_words(typed))), None)
        self.fields["area"] = known or typed
        if known is None:
            self.result.warnings.append(f"new area {typed}")
        return self.span(i, 1, "area", {"name": known or typed, "new": known is None})

    def read_preset(self, i: int) -> int:
        typed = self.words[i][1:].replace("-", " ").replace("_", " ")
        known = next((p for p in self.presets if p.lower() == typed), None)
        if known is None:
            self.result.warnings.append(f"unknown preset /{typed}")
            return 0
        return self.mark(i, 1, "preset", known)

    def read_between(self, i: int) -> int:
        """`between 6 and 8pm`, read as the range `6-8pm`."""
        if i + 3 >= len(self.words) or self.words[i + 2] != "and":
            return 0
        span = parse_time_range(f"{self.words[i + 1]}-{self.words[i + 3]}")
        if span is None:
            return 0
        start = local_midnight(self.today) + timedelta(minutes=span[0])
        self.fields["start_local"] = format_local(start)
        self.fields["end_local"] = format_local(start + timedelta(minutes=span[1] - span[0]))
        return self.span(i, 4, "at", self.fields["start_local"])

    def read_length(self, i: int, bare: bool = False) -> int:
        match = LENGTH.match(self.words[i] if not bare else "~" + self.words[i])
        if not match:
            return 0
        if match[2] and match[1].replace(".", "").isdigit():  # `30-45m`: the unit is said once, at the end
            match = LENGTH.match(f"~{match[1]}{match[2][-1]}-{match[2]}")
            assert match is not None
        low = parse_duration(match[1])
        high = parse_duration(match[2]) if match[2] else None
        if low is None or (match[2] and (high is None or high < low)):
            return 0
        # The last length typed wins, so a fixed and an elastic length never both survive.
        self.fields.pop("length_min", None)
        self.fields.pop("elastic_min", None)
        if high is None:
            self.fields["length_min"] = low
            return self.span(i, 1, "length", low)
        self.fields["elastic_min"] = (low, high)
        return self.span(i, 1, "length", [low, high])

    def read_dependency(self, i: int) -> int:
        kind, _, target = self.tokens[i].text.partition(":")
        target = target.strip('"')
        if not target:
            return 0
        if match := ITEM_REF.match(target.lower()):
            ref: int | str = int(match[1])
        else:
            ref = self.find_item(target) if self.find_item else None
            if ref is None:
                ref = target
                if self.find_item:
                    self.result.warnings.append(f"unknown dependency {target}")
        self.fields.setdefault(kind.lower(), []).append(ref)
        return self.span(i, 1, kind.lower(), ref)

    def read_weekday_range(self, i: int) -> int:
        first, last = WEEKDAY_RANGE.match(self.words[i]).groups()  # type: ignore[union-attr]
        if first not in WEEKDAY_NAMES or last not in WEEKDAY_NAMES:
            return 0
        start = next_weekday(self.today, WEEKDAY_NAMES[first])
        end = next_weekday(start, WEEKDAY_NAMES[last])
        self.fields["release_local"] = format_local(local_midnight(start) + timedelta(minutes=self.day_start))
        self.fields["due_local"] = format_local(local_midnight(end) + timedelta(minutes=END_OF_DAY))
        return self.span(i, 1, "window", [self.fields["release_local"], self.fields["due_local"]])

    def warn_if_ambiguous(self, word: str, day: date) -> None:
        match = MONTH_DAY.match(word)
        if match and int(match[1]) <= 12 and int(match[2]) <= 12 and match[1] != match[2]:
            self.result.warnings.append(f"{word} read as {day:%b} {day.day}")

    def finish(self) -> None:
        self.fields["title"] = " ".join(self.title_parts)
        if not self.title_parts:
            self.result.warnings.append("no title")
        sized = "length_min" in self.fields or "elastic_min" in self.fields
        windowed = sized and self.range_as_window()
        if "preset" not in self.fields:
            self.fields["preset"] = (
                "Errand" if windowed and not MEAL.search(self.fields["title"]) else self.inferred_preset()
            )
        if self.fields["preset"] in FLEXIBLE_KINDS:
            self.range_as_window()
        if self.fields["preset"] == "Routine" and "rrule" in self.fields and "due_local" not in self.fields:
            self.result.warnings.append("no time window, so it can land any time of day; add one like 11:30am-2pm")
        self.set_amount()
        if "rrule" in self.fields:
            self.fields["dtstart_local"] = self.fields.get("start_local") or format_local(
                self.series_start_date() + timedelta(minutes=self.day_start)
            )

    def range_as_window(self) -> bool:
        """`lunch every day 11:30am-2pm 30-45m`: a range with its own length, or a flexible kind's range, is when it
        may happen, not a fixed sitting that long."""
        if "start_local" not in self.fields:
            return False
        self.fields["release_local"] = self.fields.pop("start_local")
        self.fields["due_local"] = self.fields.pop("end_local")
        return True

    def inferred_preset(self) -> str:
        if self.fields.get("amount") == "open":
            return "Side project"
        if MEAL.search(self.fields["title"]):
            return "Routine"
        if "start_local" in self.fields:
            return "Class" if "rrule" in self.fields and CLASSLIKE.search(self.fields["title"]) else "Event"
        if self.fields.get("certainty") == "tentative":
            return "Maybe"
        due = "due_local" in self.fields and not self.bare_day
        if due and "rrule" in self.fields and guess_preset(self.fields["title"], SCHOOLWORK) is None:
            return "Errand"  # "groceries every week due sunday"; "problem set every week due fri" is schoolwork
        return "Assignment" if due else "Errand"

    def set_amount(self) -> None:
        length = self.fields.pop("length_min", None)
        elastic = self.fields.pop("elastic_min", None)
        if "start_local" in self.fields:
            return  # a fixed item is exact to the minute and already has its end
        if length is not None:
            self.fields["duration_units"] = units(length)
        if elastic is not None:
            low, high = units(elastic[0]), units(elastic[1])
            self.fields |= {"amount": "elastic", "min_units": low, "ideal_units": high, "max_units": high}

    def series_start_date(self) -> datetime:
        release = self.fields.get("release_local")
        return local_midnight(datetime.fromisoformat(release).date() if release else self.today)


def units(minutes: int) -> int:
    return math.ceil(minutes / UNIT_MIN)


def format_line(fields: dict[str, Any]) -> str:
    """A quick-add line that parses back to the same fields."""
    parts = [fields.get("title", "")]
    if "area" in fields:
        parts.append("#" + fields["area"].replace(" ", ""))
    parts += [f"+{tag}" for tag in fields.get("tags", [])]
    if "preset" in fields:
        parts.append("/" + fields["preset"].lower().replace(" ", "-"))
    if "start_local" in fields:
        start, end = (
            datetime.fromisoformat(fields["start_local"]),
            datetime.fromisoformat(fields["end_local"]),
        )
        parts.append(f"at {start:%Y-%m-%d %H:%M} for {(end - start) // timedelta(minutes=1)}m")
    if "release_local" in fields:
        parts.append(f"from {datetime.fromisoformat(fields['release_local']):%Y-%m-%d %H:%M}")
    if "due_local" in fields:
        parts.append(f"due {datetime.fromisoformat(fields['due_local']):%Y-%m-%d %H:%M}")
    if fields.get("amount") == "elastic":
        parts.append(f"~{fields['min_units'] * UNIT_MIN}m-{fields['max_units'] * UNIT_MIN}m")
    elif "duration_units" in fields:
        parts.append(f"~{fields['duration_units'] * UNIT_MIN}m")
    if "rrule" in fields:
        parts.append(f"every rrule:{fields['rrule']}")
        if "per_window" in fields:
            parts.append(f"{fields['per_window']}x")
    if "importance" in fields:
        parts.append(f"!{fields['importance']}")
    if "energy" in fields:
        parts.append(f"@{fields['energy']}")
    if fields.get("certainty") == "tentative":
        parts.append("maybe")
    if "shape" in fields:
        parts.append(fields["shape"].replace("_", "-"))
    for kind in ("after", "before"):
        parts += [f"{kind}:T{ref}" if isinstance(ref, int) else f'{kind}:"{ref}"' for ref in fields.get(kind, [])]
    if fields.get("amount") == "open":
        parts.append("open")  # read only as the last word
    return " ".join(p for p in parts if p)
