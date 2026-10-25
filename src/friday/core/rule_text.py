"""Rules from sentences (v22 Rules, M11): a fixed grammar, no LLM, from what you type to a Reading (what, when,
which days), and from a Reading and a strength to one of the planner's rule types. It reads:

- `lunch before 1pm`, `no work after 10pm on weekdays`, `deep work in the morning`, `gym between 5 and 7pm`:
  `time_preference` (Always forbids the other hours);
- `no work on sundays`, `reading only on weekends`: `time_preference` by day;
- `keep saturday mornings free`, `keep evenings free`: `reserve` (Always forbids the window);
- `at most 6 hours a day`, `no more than 2h of reading a day`: `daily_load`;
- `finish things a day early`, `finish essays 2 days before they're due`: `finish_early`;
- `gym right after class`: `after_event`;
- `go easier on saturday and go harder on sunday`, `take it easy on weekends`: a pace for those weekdays, every week
  (not a planner rule: `pace.weekly`, which the day's dials come from);
- `push when necessary for work not to be late`, `don't let work be late`: deadlines first, which is built in
  (`late_work`), so it's said to be on already rather than added;
- `gym and climbing club are optional`, `skip gym if there's too much work`: `skippable`, events whose time is
  used only when work would otherwise be late;
- `no work after 10pm the night before climbing club`, `if I'm going to climbing club the next day, the day before
  must end at 10`: `before_event`.
"""

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from friday.core.time import ampm_in

Strength = Literal["Prefer", "Strongly", "Always"]
Kind = Literal["window", "days", "free", "cap", "early", "after", "pace", "deadlines", "optional", "night_before"]
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
NAMES = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
}
PARTS = {
    "morning": ("08:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "22:00"),
    "night": ("22:00", "02:00"),
}
EVERYTHING = {"work", "anything", "things", "tasks", "stuff", "it"}
DEEP = {"deep work", "focused work", "hard work", "focus work"}
TIME = r"(noon|midnight|\d{1,2}(?::\d\d)?\s*(?:am|pm)?)"
DAY = r"(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?s?"
DAY_WORDS = rf"((?:{DAY}|weekdays?|weekends?|every day)(?:\s*(?:,|and|&)\s*{DAY})*)"


@dataclass(frozen=True)
class Reading:
    kind: Kind
    subject: str = "work"  # "work" is everything; else deep work, an area, a preset or a title
    rel: Literal["before", "after", "between", "not_between", "on", "not_on"] | None = None
    at: str | None = None  # HH:MM
    until: str | None = None  # HH:MM, for between
    days: tuple[str, ...] | None = None  # None is every day
    amount: float | None = None  # hours a day for cap, days for early
    event: str | None = None  # after
    paces: tuple[tuple[str, str], ...] | None = None  # pace: (weekday, pace name), every week
    events: tuple[str, ...] | None = None  # optional, night_before: words in the events' titles

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clock(text: str) -> str | None:
    t = text.strip().lower().replace(" ", "")
    if t == "noon":
        return "12:00"
    if t == "midnight":
        return "00:00"
    m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?(am|pm)?", t)
    if not m:
        return None
    hour, minute = int(m[1]), int(m[2] or 0)
    if m[3] == "pm" and hour < 12:
        hour += 12
    if m[3] == "am" and hour == 12:
        hour = 0
    if not m[3] and hour < 7:  # "between 5 and 7" means the evening, as people say it
        hour += 12
    return f"{hour % 24:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def days_of(text: str) -> tuple[str, ...] | None:
    t = text.lower()
    if "every day" in t:
        return None
    out: list[str] = []
    if "weekday" in t:
        out += DAYS[:5]
    if "weekend" in t:
        out += DAYS[5:]
    for word in re.findall(r"[a-z]+", t):
        for name, short in NAMES.items():
            if word.rstrip("s") in (name, short, name[:3], name[:4]) or word == name + "s":
                out.append(short)
    found = tuple(d for d in DAYS if d in out)
    return found or None


def read(text: str) -> tuple[Reading | None, Strength]:
    """What a sentence asks for, and how strongly; None when the grammar can't read it."""
    t = " " + re.sub(r"\s+", " ", text.lower().strip().rstrip(".!")) + " "
    strength: Strength = "Prefer"
    if re.search(r"\b(always|never|must|absolutely)\b", t):
        strength = "Always"
    elif re.search(r"\b(really|strongly|definitely)\b", t):
        strength = "Strongly"
    t = re.sub(
        r"\b(i(?:'d| would)? (?:really )?(?:prefer|like|want)(?: to)?|please|ideally|always|really|strongly"
        r"|definitely|try to|i)\b",
        " ",
        t,
    )
    t = re.sub(r"\s+", " ", t)
    negated = bool(re.search(r"\b(no|never|don't|not|avoid)\b", t))
    t = re.sub(r"\b(no|never|don't do|don't|do not|not|avoid)\b", " ", t)
    readers = (read_pace, read_optional, read_night_before, read_cap, read_early, read_free, read_window, read_days,
               read_after, read_deadlines)  # fmt: skip
    for parse in readers:
        found = parse(" " + " ".join(t.split()) + " ", negated)
        if found:
            return found, strength
    return None, strength


def subject_of(words: str) -> str:
    s = re.sub(r"\b(eating|having|doing|do|my|the|a|an|any|of|to)\b", " ", words).strip()
    s = " ".join(s.split())
    if not s or s in EVERYTHING:
        return "work"
    return "deep work" if s in DEEP else s


PACE_WORDS = {
    **dict.fromkeys(("easier", "easy", "lighter", "light", "less", "relaxed", "slower"), "Easy"),
    **dict.fromkeys(("harder", "hard", "heavier", "heavy", "more", "push", "faster"), "Push"),
    **dict.fromkeys(("normal", "regular", "usual"), "Normal"),
}
PACE = "(" + "|".join(PACE_WORDS) + ")"
LEAD = r"(?:(?:go|take it|keep it|be|work|do|plan|push it|make it)\s+)?"
FULL_DAY = {short: name for name, short in NAMES.items()}


def read_pace(t: str, negated: bool) -> Reading | None:
    """`go easier on saturday and go harder on sunday`, `push on sundays`, `saturdays are easy`: every clause names a
    pace and days (a clause of days alone takes the one before's); anything else isn't read as paces."""
    if negated:
        return None
    found: dict[str, str] = {}
    pace = None
    first = rf"{LEAD}(?:an? )?{PACE}(?: days?| pace| work)?(?: on| for)? {DAY_WORDS}"  # go easier on saturday
    last = rf"{DAY_WORDS} (?:are |is |should be |will be |as )?(?:an? )?{PACE}(?: days?| pace)?"  # sundays are hard
    for clause in (c.strip() for c in re.split(r",|;|\band\b|\bbut\b|\bthen\b", t) if c.strip()):
        if m := re.fullmatch(first, clause):
            word, days = m[1], m[2]
        elif m := re.fullmatch(last, clause):
            days, word = m[1], m[2]
        elif pace and re.fullmatch(rf"(?:on )?{DAY_WORDS}", clause):
            word, days = None, clause
        else:
            return None
        pace = PACE_WORDS[word] if word else pace
        for day in days_of(days) or DAYS:
            found[day] = pace  # type: ignore[assignment]
    if not found:
        return None
    return Reading("pace", "pace", paces=tuple((d, found[d]) for d in DAYS if d in found))


def titles_in(words: str) -> tuple[str, ...]:
    """The events a sentence names: `the gym sessions on tuesday and thursday as well as climbing club` is gym and
    climbing club (the days go: a title is matched on every day it's on)."""
    words = re.sub(rf"\b(?:on|every) {DAY_WORDS}", " ", words)
    out = []
    for part in re.split(r"\s*(?:,|&|\band\b|\bas well as\b|\bplus\b|\bor\b)\s*", words):
        part = re.sub(r"\b(?:make|the|my|going to|go to|sessions?|meetings?|practices?)\b", " ", part)
        part = " ".join(part.split())
        if part and not days_of(part):
            out.append(part)
    return tuple(out)


OPTIONAL = r"(?:optional|skippable|flexible)"
REQUIRED = r"(?:mandatory|required|compulsory|necessary|essential)"
BUSY = r"(?:too much|a lot|lots|busy|behind|swamped|work|late|time)"


def read_optional(t: str, negated: bool) -> Reading | None:
    """Events that give way to work: `X are optional`, `X not mandatory`, `skip X if there's too much work`."""
    found = (
        re.search(rf"^ ?(?:make |treat |consider )?(.+?) (?:be |is |are |as )?{OPTIONAL}\b", t)
        or (negated and re.search(rf"^ ?(?:make |treat )?(.+?) (?:be|is|are) {REQUIRED}\b", t))
        or re.search(
            rf"^ ?(?:can |may |you can |friday can |ok to )?(?:skip|miss|drop) (.+?) (?:if|when|whenever) .*{BUSY}", t
        )
        or re.search(r"^ ?(.+?) (?:can|may) be (?:skipped|missed|dropped)\b", t)
        or re.search(rf"^ ?if .*{BUSY}.*?,? (?:then )?(?:skip|miss|drop) (.+?) ?$", t)
        or (negated and re.search(rf"^ ?(?:go to|attend) (.+?) (?:if|when|whenever) .*{BUSY}", t))
    )
    titles = titles_in(found[1]) if found else ()
    return Reading("optional", "events", events=titles) if titles else None


def evening(raw: str) -> str | None:
    """A time the day ends at: `10` or `10:00` with no am or pm is the evening's."""
    at = clock(raw)
    if at and not re.search(r"(am|pm|noon|midnight)", raw) and int(at[:2]) < 12:
        at = f"{int(at[:2]) + 12:02d}{at[2:]}"
    return at


def read_night_before(t: str, negated: bool) -> Reading | None:
    """`no work after 10pm the night before climbing club`, `stop working at 10 before climbing club`, `if I'm going to
    climbing club the next day, the day before must end at 10`."""
    before = r"(?:on )?(?:the )?(?:night|day|evening)?s? ?before"
    stop = r"(?:stop working|stop work|end(?: the| my)? day|finish(?: work)?|be done|wrap up|go to bed|be in bed)"
    ended = negated and re.search(rf"^ ?(?:work |anything )?(?:after|past) {TIME} {before} (.+?) ?$", t)
    if m := ended or re.search(rf"^ ?{stop} (?:at|by) {TIME} {before} (.+?) ?$", t):
        at, titles = evening(m[1]), titles_in(m[2])  # no work after 10pm, or stop working at 10, the night before X
    elif m := re.search(
        rf"^ ?if (?:'m |am |im )?(?:going to|have|got) (.+?) (?:the )?(?:next day|tomorrow|next morning),? (?:then )?"
        rf"(?:the )?(?:previous day|day before|night before|evening before|previous night)? ?"
        rf"(?:must |should |has to |needs to |to )?(?:end|stop|finish|be done|wrap up) (?:at|by) {TIME}",
        t,
    ):
        titles, at = titles_in(m[1]), evening(m[2])
    else:
        return None
    return Reading("night_before", "work", at=at, events=titles) if at and titles else None


def read_deadlines(t: str, negated: bool) -> Reading | None:
    """Work more when it must, so nothing is late: what `late_work` already does, read last so any other rule wins."""
    late = re.search(r"\b(late|on time|deadlines?|overdue|miss(?:ed|ing)?)\b", t)
    push = re.search(r"\b(push|harder|more|longer|later|necessary|needed|need|must|have to|whatever|sure|let|be)\b", t)
    return Reading("deadlines", "work") if late and push else None


def read_cap(t: str, negated: bool) -> Reading | None:
    m = re.search(
        r"(?:at most|no more than|more than|max(?:imum)?|up to) (\d+(?:\.\d+)?) ?(?:h|hrs?|hours?)"
        r"(?: of ([a-z ]+?))? (?:a|per|each) day",
        t,
    )
    if not m:
        return None
    return Reading("cap", subject_of(m[2] or "work"), amount=float(m[1]))


def read_early(t: str, negated: bool) -> Reading | None:
    m = re.search(r"finish(?: ([a-z ]+?))? (a|one|two|three|\d+) days? (?:early|before|ahead)", t)
    if not m:
        return None
    n = {"a": 1, "one": 1, "two": 2, "three": 3}.get(m[2]) or int(m[2])
    return Reading("early", subject_of(m[1] or "work"), amount=float(n))


LIGHTER = r"lighter|light|easier|easy|quieter|quiet|calmer|less busy"
LIGHTER_SHARE = 0.5  # a lighter stretch keeps about half its time free: less work there, not none


def read_free(t: str, negated: bool) -> Reading | None:
    """`keep saturday mornings free` keeps all of it; `keep friday and saturday nights lighter` (or `lighter friday
    evenings`) about half."""
    m = re.search(
        rf"(?:keep|make) (?:my )?{DAY_WORDS}? ?(mornings?|afternoons?|evenings?|nights?)? ?"
        rf"(?:from {TIME} (?:to|until|-) {TIME} )?(free|clear|open|{LIGHTER})\b",
        t,
    )
    if m and (m[1] or m[2] or m[3]):
        days, part, start, end, how = m[1], m[2], m[3], m[4], m[5]
    elif m := re.search(rf"\b({LIGHTER}) {DAY_WORDS} ?(mornings?|afternoons?|evenings?|nights?)\b", t):
        how, days, part, start, end = m[1], m[2], m[3], None, None
    else:
        return None
    span = PARTS.get((part or "").rstrip("s"), (clock(start) if start else None, clock(end) if end else None))
    share = None if how in ("free", "clear", "open") else LIGHTER_SHARE
    return Reading(
        "free", "work", rel="between" if span[0] else None, at=span[0], until=span[1], days=days_of(days or ""),
        amount=share,
    )  # fmt: skip


def read_window(t: str, negated: bool) -> Reading | None:
    on = re.search(rf" on {DAY_WORDS} ", t)
    days = days_of(on[1]) if on else None
    if on:
        t = t.replace(on[0], " ")
    between = "not_between" if negated else "between"  # "no work between 7 and 10am" keeps those hours free
    if m := re.search(r"^ ?([a-z ]*?) ?(?:in the|during the) (morning|afternoon|evening|night)s? ", t):
        start, end = PARTS[m[2]]
        return Reading("window", subject_of(m[1]), rel=between, at=start, until=end, days=days)
    if m := re.search(rf"^ ?([a-z ]*?) ?(?:between|from) {TIME} (?:and|to|until|-) {TIME} ", t):
        start, end = clock(m[2]), clock(m[3])
        if start and end and end <= start and not re.search(r"(am|pm)", m[3]) and int(end[:2]) < 12:
            end = f"{int(end[:2]) + 12:02d}{end[2:]}"
        return (
            Reading("window", subject_of(m[1]), rel=between, at=start, until=end, days=days) if start and end else None
        )
    if m := re.search(rf"^ ?([a-z ]*?) ?(before|after|by|until|past) {TIME} ", t):
        at = clock(m[3])
        rel = "before" if m[2] in ("before", "by", "until") else "after"
        if negated:
            rel = "after" if rel == "before" else "before"
        return Reading("window", subject_of(m[1]), rel=rel, at=at, days=days) if at else None
    return None


def read_days(t: str, negated: bool) -> Reading | None:
    m = re.search(rf"^ ?([a-z ]*?) ?(only )?on {DAY_WORDS} ", t) or re.search(rf"^ ?(rest|off) {DAY_WORDS} ", t)
    if not m:
        return None
    if m[1] in ("rest", "off"):
        return Reading("days", "work", rel="not_on", days=days_of(m[2]))
    rel = "not_on" if negated else "on"
    return Reading("days", subject_of(m[1]), rel=rel, days=days_of(m[3]))


def read_after(t: str, negated: bool) -> Reading | None:
    m = re.search(r"^ ?([a-z ]+?) (?:right |straight |just )?after (?:my |the )?([a-z ]+?) ", t)
    if not m or clock(m[2]) or negated:
        return None
    return Reading("after", subject_of(m[1]), event=m[2].strip())


def with_overrides(r: Reading, overrides: dict[str, Any]) -> Reading:
    known = {
        k: (tuple(v) if k == "days" and v is not None else v)
        for k, v in overrides.items()
        if k in Reading.__dataclass_fields__
    }
    return replace(r, **known)


DAY_LABEL = {("mon", "tue", "wed", "thu", "fri"): "on weekdays", ("sat", "sun"): "on weekends"}


def days_words(days: tuple[str, ...] | None) -> str:
    if not days:
        return ""
    return DAY_LABEL.get(days) or "on " + ", ".join(d.capitalize() for d in days)


def titled(words: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in words.split())


def days_spoken(days: tuple[str, ...]) -> str:
    """Saturdays; Saturdays and Sundays; weekends."""
    if days in (DAYS[:5], DAYS[5:]):
        return "weekdays" if days == DAYS[:5] else "weekends"
    names = [FULL_DAY[d].capitalize() + "s" for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def sentence(r: Reading) -> str:
    """The rule in plain words, as the Rules list shows it, on a 12-hour clock."""
    return ampm_in(said(r))


def said(r: Reading) -> str:
    if r.kind == "deadlines":
        return "Deadlines come first"
    if r.kind == "optional":
        names = [titled(e) for e in r.events or ()]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        return f"{listed} {'is' if len(names) == 1 else 'are'} optional: work takes the time when it must"
    if r.kind == "night_before":
        return f"No work after {r.at} the night before {' or '.join(titled(e) for e in r.events or ())}"
    if r.kind == "pace":
        by_pace: dict[str, list[str]] = {}
        for day, pace in r.paces or ():
            by_pace.setdefault(pace, []).append(day)
        return ", ".join(f"{pace} on {days_spoken(tuple(days))}" for pace, days in by_pace.items())
    subject = "Work" if r.subject == "work" else r.subject[0].upper() + r.subject[1:]
    on = (" " + days_words(r.days)) if r.days else ""
    if r.kind == "window":
        if r.rel == "between":
            return f"{subject} between {r.at} and {r.until}{on}"
        if r.rel == "not_between":
            return f"No {r.subject} between {r.at} and {r.until}{on}"
        if r.subject == "work":  # "no work after 22:00" says it the way people do
            return f"No work {'after' if r.rel == 'before' else 'before'} {r.at}{on}"
        return f"{subject} {r.rel} {r.at}{on}"
    if r.kind == "days":
        return f"No {r.subject} {days_words(r.days)}" if r.rel == "not_on" else f"{subject} only {days_words(r.days)}"
    if r.kind == "free":
        when = f" {r.at}–{r.until}" if r.at else ""
        how = "lighter" if r.amount else "free"
        return f"Keep {days_words(r.days).removeprefix('on ') or 'every day'}{when} {how}"
    if r.kind == "cap":
        of = "" if r.subject == "work" else f" of {r.subject}"
        return f"At most {r.amount:g} h{of} a day"
    if r.kind == "early":
        n = int(r.amount or 1)
        return (
            f"Finish {'things' if r.subject == 'work' else r.subject} {n} day{'s' if n > 1 else ''} before they're due"
        )
    return f"{subject} right after {r.event}"


def scope_of(subject: str, areas: list[str], presets: list[str]) -> dict[str, Any] | None:
    if subject == "work":
        return None
    if subject == "deep work":
        return {"energy": "deep"}
    for a in areas:
        if a.lower() == subject:
            return {"area": a}
    for p in presets:
        if p.lower() in (subject, subject.rstrip("s")):
            return {"preset": p}
    return {"title": subject}


PRICE = {"Prefer": 2.0, "Strongly": 6.0}
WEIGHT = {"Prefer": 1.0, "Strongly": 3.0, "Always": 10.0}


def spec(r: Reading, strength: Strength, name: str, areas: list[str], presets: list[str]) -> dict[str, Any]:
    """The planner rule for a reading: {type, name, weight, scope, reason, params}."""
    if r.kind == "optional":  # their time is priced, not walled off (build), so it goes only when work must
        return {"name": name, "type": "skippable", "weight": 1.0, "scope": None, "reason": sentence(r),
                "params": {"titles": list(r.events or ()), "price": 8.0}}  # fmt: skip
    if r.kind == "night_before":
        price: Any = "forbid" if strength == "Always" else PRICE[strength]
        return {"name": name, "type": "before_event", "weight": 1.0, "scope": None, "reason": sentence(r),
                "params": {"titles": list(r.events or ()), "after": r.at, "price": price}}  # fmt: skip
    if r.kind == "deadlines":  # built in: `rule_add` makes sure it's on rather than adding a second one
        return {"name": "late_work", "type": "late_work", "weight": 10.0, "scope": None, "reason": sentence(r),
                "params": {}}  # fmt: skip
    if r.kind == "pace":  # a setting, not a planner rule: `rule_add` writes `pace.weekly`
        return {"name": name, "type": "pace", "weight": 0.0, "scope": None, "reason": sentence(r),
                "params": {"weekly": dict(r.paces or ())}}  # fmt: skip
    scope = scope_of(r.subject, areas, presets)
    price: Any = "forbid" if strength == "Always" else PRICE[strength]
    base = {"name": name, "scope": scope, "reason": sentence(r)}
    if r.kind == "window":
        # The hours to avoid: after `at` (for before), before it (for after), outside [at, until) (for between),
        # inside it (for not_between).
        start, end = {
            "before": (r.at, "04:00"),
            "after": ("04:00", r.at),
            "between": (r.until, r.at),
            "not_between": (r.at, r.until),
        }[r.rel or "before"]
        params = {"start": start, "end": end, "price": price} | ({"days": list(r.days)} if r.days else {})
        return base | {"type": "time_preference", "weight": 1.0, "params": params}
    if r.kind == "days":
        key = "days" if r.rel == "not_on" else "days_except"
        return base | {"type": "time_preference", "weight": 1.0, "params": {key: list(r.days or ()), "price": price}}
    if r.kind == "free":
        window = {"start": r.at, "end": r.until} if r.at else {}
        days = {"days": list(r.days)} if r.days else {}
        if strength == "Always" and not r.amount:
            return base | {
                "type": "time_preference",
                "weight": 1.0,
                "scope": None,
                "params": window | days | {"price": "forbid"},
            }
        hours = hours_between(r.at, r.until) if r.at and r.until else 24
        kept = round(hours * (r.amount or 1) * 4) / 4  # lighter: about half kept free, to the quarter hour
        return base | {
            "type": "reserve",
            "weight": WEIGHT[strength] * 2,
            "scope": None,
            "params": window | days | {"free": f"{kept:g}h"},
        }
    if r.kind == "cap":
        return base | {"type": "daily_load", "weight": WEIGHT[strength] * 5, "params": {"threshold": f"{r.amount:g}h"}}
    if r.kind == "early":
        return base | {"type": "finish_early", "weight": WEIGHT[strength], "params": {"days": int(r.amount or 1)}}
    events = {"event_kind": "class"} if (r.event or "").rstrip("s") in ("class", "lecture") else {"title": r.event}
    params = {"events": events, "measure_from": "last", "slope": 1, "cap": 3}
    return base | {"type": "after_event", "weight": WEIGHT[strength], "params": params}


def hours_between(start: str, end: str) -> float:
    a = int(start[:2]) * 60 + int(start[3:])
    b = int(end[:2]) * 60 + int(end[3:])
    return ((b - a) % 1440) / 60
