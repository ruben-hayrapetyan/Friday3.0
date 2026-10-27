"""Date, time and duration shorthand (DESIGN §9.4), read from lists of lowercase words."""

import calendar
import re
from datetime import date, timedelta

from friday.core.time import WEEKDAYS

WEEKDAY_NAMES = (
    {name: i for i, name in enumerate(WEEKDAYS)}
    | {name.lower(): i for i, name in enumerate(calendar.day_name)}
    | {"tues": 1, "weds": 2, "thur": 3, "thurs": 3}
)
TOMORROW = {"tomorrow", "tmrw", "tmr", "tmw"}
TIME_WORDS = {"noon": 12 * 60, "midnight": 23 * 60 + 59}  # midnight as a due is the end of that day
MONTH_NAMES = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name} | {
    name.lower(): i for i, name in enumerate(calendar.month_name) if name
}

DURATION = re.compile(r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+)m)?$")
TIME_24H = re.compile(r"^(\d{1,2}):(\d{2})$")
TIME_12H = re.compile(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$")
OFFSET_DAYS = re.compile(r"^\+?(\d+)d$")
MONTH_DAY = re.compile(r"^(\d{1,2})-(\d{1,2})$")
SLASH_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?$")  # 10/30, 10/30/26
TIME_RANGE = re.compile(r"^(\d{1,2}(?::\d{2})?(?:am|pm)?)-(\d{1,2}(?::\d{2})?(?:am|pm)?)$")  # 3-4pm, 10:10-11:25
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_duration(text: str) -> int | None:
    """Minutes in `30m`, `1.5h` or `1h30m`."""
    match = DURATION.match(text)
    if not match or not any(match.groups()):
        return None
    hours, minutes = match.groups()
    total = float(hours or 0) * 60 + int(minutes or 0)
    return round(total) if total > 0 else None


def parse_time(text: str) -> int | None:
    """Minutes after midnight in `15:00`, `3pm`, `9:30am` or `noon`."""
    if text in TIME_WORDS:
        return TIME_WORDS[text]
    if match := TIME_24H.match(text):
        hour, minute = int(match[1]), int(match[2])
        if len(match[1]) == 1 and 1 <= hour <= 6:
            hour += 12  # "6:15" without am or pm is the evening, as people write it; "06:15" stays the morning
    elif match := TIME_12H.match(text):
        hour, minute = int(match[1]) % 12 + (12 if match[3] == "pm" else 0), int(match[2] or 0)
        if int(match[1]) > 12:
            return None
    else:
        return None
    return hour * 60 + minute if hour < 24 and minute < 60 else None


def parse_time_range(text: str) -> tuple[int, int] | None:
    """Start and end minutes in `3-4pm` (the start takes the end's am or pm), `7:30pm-9pm` or `10:10-11:25`."""
    match = TIME_RANGE.match(text)
    if not match:
        return None
    first, last = match.groups()
    end = parse_time(last)
    suffix = last[-2:] if last.endswith(("am", "pm")) else ""
    start = parse_time(first if first.endswith(("am", "pm")) or not suffix else first + suffix)
    if start is not None and end is not None and start >= end and suffix == "pm" and not first.endswith("pm"):
        start = parse_time(first + "am")  # 11-1pm is 11am to 1pm
    if start is not None and end is not None and start >= end and not suffix and end < 12 * 60:
        end += 12 * 60  # 6:15-7:30 is 6:15pm to 7:30pm: the end follows the start
    return (start, end) if start is not None and end is not None and start < end else None


def time_start(text: str) -> int | None:
    """A time, or the start of a time range."""
    found = parse_time(text)
    if found is None and (span := parse_time_range(text)):
        return span[0]
    return found


def next_weekday(today: date, weekday: int) -> date:
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def next_month_day(today: date, month: int, day: int) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def read_date(words: list[str], i: int, today: date) -> tuple[date, int] | None:
    """The date starting at words[i] and how many words it used."""
    word = words[i]
    following = words[i + 1] if i + 1 < len(words) else ""
    if word == "in" and (match := OFFSET_DAYS.match(following)) and not following.startswith("+"):
        return today + timedelta(days=int(match[1])), 2
    if word == "next" and following == "week":
        return today + timedelta(days=7 - today.weekday()), 2
    if word == "next" and following in WEEKDAY_NAMES:  # that day of next week
        return today + timedelta(days=7 - today.weekday() + WEEKDAY_NAMES[following]), 2
    if word in MONTH_NAMES and following.isdigit():
        found = next_month_day(today, MONTH_NAMES[word], int(following))
        return (found, 2) if found else None
    single = parse_date_word(word, today)
    return (single, 1) if single else None


def parse_date_word(word: str, today: date) -> date | None:
    if word == "today":
        return today
    if word in TOMORROW:
        return today + timedelta(days=1)
    if word in WEEKDAY_NAMES:
        return next_weekday(today, WEEKDAY_NAMES[word])
    if word == "eow":
        return next_weekday(today, 6)
    if word == "eom":
        return date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    if word.startswith("+") and (match := OFFSET_DAYS.match(word)):
        return today + timedelta(days=int(match[1]))
    if match := MONTH_DAY.match(word):
        return next_month_day(today, int(match[1]), int(match[2]))
    if match := SLASH_DATE.match(word):
        if match[3]:
            try:
                return date(int(match[3]) + (2000 if len(match[3]) == 2 else 0), int(match[1]), int(match[2]))
            except ValueError:
                return None
        return next_month_day(today, int(match[1]), int(match[2]))
    if ISO_DATE.match(word):
        try:
            return date.fromisoformat(word)
        except ValueError:
            return None
    return None


def read_moment(words: list[str], i: int, today: date) -> tuple[date, int | None, int] | None:
    """A date with an optional time (`fri 3pm`, `fri@3pm`, `fri 3-4pm`, `10/30 at 9am`, or a bare time meaning
    today), and words used; a time range gives its start (`parse_time_range` has the end)."""
    if "@" in words[i]:
        day_part, _, time_part = words[i].partition("@")
        day, minute = parse_date_word(day_part, today), parse_time(time_part)
        return (day, minute, 1) if day and minute is not None else None
    if (minute := time_start(words[i])) is not None:
        return today, minute, 1
    found = read_date(words, i, today)
    if not found:
        return None
    day, used = found
    if i + used < len(words) and (minute := time_start(words[i + used])) is not None:
        return day, minute, used + 1
    if (
        i + used + 1 < len(words)
        and words[i + used] == "at"
        and (minute := time_start(words[i + used + 1])) is not None
    ):
        return day, minute, used + 2  # 10/30 at 9am
    return day, None, used
