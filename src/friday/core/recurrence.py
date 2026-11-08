"""Repeats: shorthand → RRULE, RRULE → words, and expansion in local time (DESIGN §6.3)."""

import calendar
import re
from datetime import date, datetime, timedelta

from dateutil.rrule import rrulestr

from friday.core.dates import WEEKDAY_NAMES, read_date

RRULE_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WEEKDAYS_SET = {"MO", "TU", "WE", "TH", "FR"}
EVERY_N_WEEKS = re.compile(r"^(\d+)w$")
UNITS = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}


def read_repeat(words: list[str], i: int, today: date) -> tuple[str, int] | None:
    """The RRULE for the shorthand starting at words[i] and how many words it used."""
    found = read_base_rule(words, i)
    if not found:
        return None
    rule, used = found
    if i + used + 1 < len(words) and words[i + used] == "until":
        until = read_date(words, i + used + 1, today)
        if until:
            rule += f";UNTIL={until[0]:%Y%m%d}T235959"
            used += 1 + until[1]
    return rule, used


def read_base_rule(words: list[str], i: int) -> tuple[str, int] | None:
    word = words[i]
    following = words[i + 1] if i + 1 < len(words) else ""
    if word.startswith("rrule:"):
        rule = word.removeprefix("rrule:").upper()
        return (rule, 1) if is_valid_rule(rule) else None
    if word == "day":
        return "FREQ=DAILY", 1
    if word == "week":
        return "FREQ=WEEKLY", 1
    if word == "weekdays":
        return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", 1
    if word == "month" and following.isdecimal() and 1 <= int(following) <= 31:
        return f"FREQ=MONTHLY;BYMONTHDAY={int(following)}", 2
    if word in UNITS and not following.isdecimal():  # every month, every year ("month 40" is no day of a month)
        return f"FREQ={UNITS[word]}", 1
    if word in ("other", "second") and following in UNITS:  # every other week
        return f"FREQ={UNITS[following]};INTERVAL=2", 2
    if word in ("other", "second") and (days := byday(following)):  # every other tuesday
        return f"FREQ=WEEKLY;INTERVAL=2;BYDAY={days}", 2
    if word == "fortnight":
        return "FREQ=WEEKLY;INTERVAL=2", 1
    if word.isdecimal() and 1 <= int(word) <= 99 and following.rstrip("s") in UNITS:  # every 4 weeks, every 3 days
        return f"FREQ={UNITS[following.rstrip('s')]};INTERVAL={int(word)}", 2
    if (match := EVERY_N_WEEKS.match(word)) and (days := byday(following)):
        return f"FREQ=WEEKLY;INTERVAL={int(match[1])};BYDAY={days}", 2
    if byday(word):
        names, used = word.split(","), 1
        while i + used < len(words):  # "mon wed fri" and "tue and thu" as well as "mon,wed,fri"
            nxt = words[i + used]
            if nxt == "and" and i + used + 1 < len(words) and byday(words[i + used + 1]):
                used += 1
            elif byday(nxt):
                names += nxt.split(",")
                used += 1
            else:
                break
        return f"FREQ=WEEKLY;BYDAY={byday(','.join(dict.fromkeys(names)))}", used
    return None


def byday(word: str) -> str | None:
    names = word.split(",")
    if not all(name in WEEKDAY_NAMES for name in names):
        return None
    return ",".join(RRULE_DAYS[WEEKDAY_NAMES[name]] for name in names)


def is_valid_rule(rule: str) -> bool:
    try:
        repeat, _ = rule_and_skips(rule)
        rrulestr(repeat, dtstart=datetime(2026, 1, 1))
    except (ValueError, TypeError):
        return False
    return True


def rule_and_skips(rule: str) -> tuple[str, set[datetime]]:
    """A stored rule apart from the times it skips: `EXDATE=20261124T100000,…` (local), as a calendar feed's EXDATE
    cancels one week's lecture. Everything else reads the rule as it is and passes that part over."""
    parts = rule.split(";")
    skips = {
        datetime.strptime(moment, "%Y%m%dT%H%M%S")
        for part in parts
        if part.upper().startswith("EXDATE=")
        for moment in part.split("=", 1)[1].split(",")
        if moment
    }
    return ";".join(p for p in parts if not p.upper().startswith("EXDATE=")), skips


def rule_parts(rule: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in rule.upper().split(";") if "=" in part)


def describe(rule: str) -> str:
    parts = rule_parts(rule)
    text = describe_frequency(parts)
    if "UNTIL" in parts:
        until = datetime.strptime(parts["UNTIL"][:8], "%Y%m%d")
        text += f" until {until:%b} {until.day}"
    if "COUNT" in parts:
        text += f", {parts['COUNT']} times"
    return text


def describe_frequency(parts: dict[str, str]) -> str:
    interval = int(parts.get("INTERVAL", "1"))
    freq = parts.get("FREQ")
    if freq == "DAILY":
        return "Every day" if interval == 1 else f"Every {interval} days"
    if freq == "WEEKLY":
        return describe_weekly(parts.get("BYDAY", "").split(",") if "BYDAY" in parts else [], interval)
    if freq == "MONTHLY":
        day = parts.get("BYMONTHDAY")
        every = "Monthly" if interval == 1 else f"Every {interval} months"
        return f"{every} on the {ordinal(int(day))}" if day else every
    if freq == "YEARLY":
        return "Yearly" if interval == 1 else f"Every {interval} years"
    return f"Repeats ({';'.join(f'{k}={v}' for k, v in parts.items())})"


def describe_weekly(days: list[str], interval: int) -> str:
    if not days:
        return {1: "Every week", 2: "Every other week"}.get(interval, f"Every {interval} weeks")
    if set(days) == WEEKDAYS_SET and interval == 1:
        return "Every weekday"
    full = [calendar.day_name[RRULE_DAYS.index(d)] for d in days]
    if len(days) == 1:
        if interval == 1:
            return f"Every {full[0]}"
        if interval == 2:
            return f"Every other {full[0]}"
        return f"Every {interval} weeks on {full[0]}"
    listed = join_words([calendar.day_abbr[RRULE_DAYS.index(d)] for d in days])
    if interval == 1:
        return f"Every {listed}"
    return f"Every {'other week' if interval == 2 else f'{interval} weeks'} on {listed}"


def join_words(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def occurrences(rule: str, dtstart: datetime, start: datetime, end: datetime) -> list[datetime]:
    """Local occurrence times in [start, end), less the ones it skips. Local, so a weekly 08:00 stays 08:00 across
    DST changes."""
    repeat, skips = rule_and_skips(rule)
    return [t for t in rrulestr(repeat, dtstart=dtstart).between(start, end, inc=True) if t < end and t not in skips]


def next_occurrence(rule: str, dtstart: datetime, after: datetime) -> datetime | None:
    repeat, skips = rule_and_skips(rule)
    found = rrulestr(repeat, dtstart=dtstart).after(after)
    while found is not None and found in skips:
        found = rrulestr(repeat, dtstart=dtstart).after(found)
    return found


def ending_before(rule: str, day: date) -> str:
    """The rule cut off so its last occurrence is before `day` (editing a series from a date on)."""
    kept = [part for part in rule.split(";") if not part.upper().startswith(("UNTIL=", "COUNT="))]
    return ";".join([*kept, f"UNTIL={day - timedelta(days=1):%Y%m%d}T235959"])


SET_DATE_PARTS = ("BYYEARDAY", "BYWEEKNO", "BYSETPOS", "BYEASTER")


def moved_rule(rule: str, old_day: date, new_day: date) -> str | None:
    """The rule once its time on `old_day` moves to `new_day` (5 Nov: "change jaspers bday to nov 6 yearly"): a
    weekday it names, or the day of the month or the month, becomes the new day's; the others stay. None when the
    move can't be said in the rule: two days of a month, the second Tuesday, a weekday it repeats on already."""
    out = []
    shift = new_day - old_day
    days = rule_parts(rule).get("BYDAY", "").split(",")
    for part in rule.split(";"):
        key, _, value = part.partition("=")
        name = key.upper()
        if name == "BYDAY":
            old, new = RRULE_DAYS[old_day.weekday()], RRULE_DAYS[new_day.weekday()]
            if old not in days or (new != old and new in days):
                return None
            value = ",".join(new if d == old else d for d in days)
        elif name in ("BYMONTHDAY", "BYMONTH"):
            was, now = (old_day.day, new_day.day) if name == "BYMONTHDAY" else (old_day.month, new_day.month)
            if value != str(was):
                return None
            value = str(now)
        elif name in SET_DATE_PARTS:
            return None
        elif name == "UNTIL" and shift.days > 0 and len(days) == 1:
            # Every time moves later, so the last one does too rather than falling past the end.
            end = datetime.strptime(value[:8], "%Y%m%d") + shift
            value = f"{end:%Y%m%d}{value[8:]}"
        out.append(f"{key}={value}" if _ else part)
    return ";".join(out)
