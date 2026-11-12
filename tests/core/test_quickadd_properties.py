"""Quick-add lines generated from the grammar, in any order: a title, a day, a time or a range, a length, a repeat and
markers. Whatever the line, the parser doesn't crash, the title is just the words you typed for it, an event ends
after it starts, a repeat gets a rule, a due or a time is kept, and `format_line` writes a line that parses back."""

from datetime import date, datetime, timedelta

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from friday.core.dates import WEEKDAY_NAMES, parse_duration, parse_time, parse_time_range, read_date
from friday.core.presets import DEFAULT_PRESETS
from friday.core.quickadd import format_line, parse
from friday.core.recurrence import is_valid_rule

NOW = datetime(2026, 10, 18, 10, 0)  # Sunday
AREAS = ["CS 1110", "Psych", "Health"]
QUICK = settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])

# Words the grammar never reads, so a title made of them must come back whole.
TITLE_WORDS = ["essay", "laundry", "PS5", "report", "notes", "groceries", "salsa", "dentist", "call", "mom", "draft",
               "taxes", "chem", "review", "Lab", "club"]  # fmt: skip
DATES = ["fri", "friday", "next friday", "tomorrow", "tmrw", "10/30", "oct 30", "today", "in 3d", "2026-11-02",
         "eow", "eom", "tue", "tues", "11-02", "sat", "next week", "11/15", "thurs", "dec 1", "10/30/26"]  # fmt: skip
TIMES = ["3pm", "6:15", "6:15pm", "9:30am", "noon", "15:00", "10am", "7pm", "8:45am", "12pm", "06:30"]
RANGES = ["3-4pm", "6:15-7:30pm", "11-1pm", "7:30pm-9pm", "10:10-11:25", "9-10am", "6:15-7:30", "1-2:30pm"]
TILDE_LENGTHS = ["~2h", "~30m", "~1.5h", "~1h30m", "~20m-45m", "~1h-2h"]
BARE_LENGTHS = ["30-45m", "1-2h", "45m", "2h", "90m", "1.5h", "1h30m"]
REPEATS = ["every week", "every day", "every mon,wed", "every mon wed fri", "every tue and thu", "every other week",
           "every 2 weeks", "every 2w thu", "monthly", "weekly", "daily", "every month 1", "every weekdays",
           "biweekly", "3x a week", "twice a week", "every week 3x", "every week until 12-11", "every friday",
           "every other tuesday", "every 3 days", "yearly", "fortnightly", "every 4 weeks"]  # fmt: skip
# Each marker and the field it sets; one per field in a line (a second `#area` simply wins).
MARKERS = {
    "maybe": ("certainty", "tentative"),
    "#cs1110": ("area", "CS 1110"),
    "#psych": ("area", "Psych"),
    "#newarea": ("area", "newarea"),
    "+reading": ("tags", ["reading"]),
    "/chore": ("preset", "Chore"),
    "/errand": ("preset", "Errand"),
    "/reading": ("preset", "Reading"),
    "!4": ("importance", 4),
    "!high": ("importance", 5),
    "!low": ("importance", 1),
    "@deep": ("energy", "deep"),
    "@light": ("energy", "light"),
    "one-sitting": ("shape", "one_sitting"),
    "split": ("shape", "split"),
    "after:T12": ("after", [12]),
    'before:"lab report"': ("before", ["lab report"]),
    "runs by itself": ("background", True),
    "in the background": ("background", True),
}
FLEXIBLE_MARKERS = {"/chore", "/errand"}


@st.composite
def when_parts(draw: st.DrawFn) -> tuple[str, str] | None:
    """A due, a bare day, an event's time (several ways), a weekday window, or nothing."""
    d, t, r = draw(st.sampled_from(DATES)), draw(st.sampled_from(TIMES)), draw(st.sampled_from(RANGES))
    return draw(
        st.sampled_from(
            [
                None,
                ("due", f"due {d}"),
                ("due", f"by {d}"),
                ("due", f"due {d} {t}"),
                ("due", f"due {d} at {t}"),
                ("day", d),
                ("event", f"at {t}"),
                ("event", f"at {d} {t}"),
                ("event", f"{d} {t}"),
                ("event", f"{d} {r}"),
                ("event", f"{r} {d}"),
                ("event", f"{d} at {t}"),
                ("event", f"at {t} for 90m"),
                ("event", "between 6 and 8pm"),
                ("event", "between 9am and 11am"),
                ("event", "from 6:15 to 7:30"),
                ("event", "from 6:15pm until 7:30pm"),
                ("event", "from 9am to 10am"),
                ("event", "from 6:15-7:30pm"),
                ("window", draw(st.sampled_from(["sat-sun", "mon-fri", "fri-sun", "tue-thu"]))),
            ]
        )
    )


@st.composite
def lines(draw: st.DrawFn) -> tuple[str, str, list[tuple[str, str]]]:
    """A line, the title in it, and its other parts (kind, words), in a random order."""
    parts: list[tuple[str, str]] = []
    if when := draw(when_parts()):
        parts.append(when)
    if draw(st.booleans()):
        parts.append(("length", draw(st.sampled_from(TILDE_LENGTHS + BARE_LENGTHS))))
    if draw(st.booleans()):
        parts.append(("repeat", draw(st.sampled_from(REPEATS))))
    chosen = draw(st.lists(st.sampled_from(sorted(MARKERS)), max_size=4, unique_by=lambda m: MARKERS[m][0]))
    parts += [("marker", m) for m in chosen]
    parts = draw(st.permutations(parts))
    title = " ".join(draw(st.lists(st.sampled_from(TITLE_WORDS), min_size=1, max_size=3, unique=True)))
    at = draw(st.integers(0, len(parts))) if draw(st.integers(0, 3)) == 0 else 0  # mostly first, as people type
    parts.insert(at, ("title", title))
    return " ".join(words for _, words in parts), title, [p for p in parts if p[0] != "title"]


def quick(text: str) -> dict:
    return parse(text, NOW, areas=AREAS, presets=DEFAULT_PRESETS).fields


@QUICK
@given(lines())
def test_every_part_of_a_generated_line_lands_where_it_belongs(line: tuple[str, str, list[tuple[str, str]]]) -> None:
    text, title, parts = line
    kinds = {kind for kind, _ in parts}
    fields = quick(text)
    assert fields["title"] == title
    for key in ("start_local", "end_local", "release_local", "due_local", "dtstart_local"):
        if key in fields:
            datetime.fromisoformat(fields[key])
    if "start_local" in fields:
        assert fields["end_local"] > fields["start_local"]
    if "repeat" in kinds:
        assert "rrule" in fields and is_valid_rule(fields["rrule"]) and "dtstart_local" in fields
    if "due" in kinds:
        assert "due_local" in fields
    if "event" in kinds:  # an event, or (with a length of its own, or a flexible kind) the window it may go in
        assert "start_local" in fields or ("release_local" in fields and "due_local" in fields)
    if "window" in kinds:
        assert fields["release_local"] < fields["due_local"]
    markers = [words for kind, words in parts if kind == "marker"]
    for marker in markers:
        name, value = MARKERS[marker]
        assert fields.get(name) == value, marker
    length = next((words for kind, words in parts if kind == "length"), None)
    if length and "start_local" not in fields:  # a flexible kind's time is its window; the length is still its own
        assert "duration_units" in fields or fields.get("amount") == "elastic"
    if fields.get("amount") == "elastic":
        assert 0 < fields["min_units"] <= fields["ideal_units"] <= fields["max_units"]


@QUICK
@given(lines())
def test_format_line_parses_back_to_the_same_fields(line: tuple[str, str, list[tuple[str, str]]]) -> None:
    fields = quick(line[0])
    assert quick(format_line(fields)) == fields


SOUP = ("due by from at every between and to until till - on in next week fri friday tue mon,wed sat-sun mon-fri "
        "tomorrow tmrw today 10/30 10/30/26 13/45 oct 30 feb 30 2/30 02-30 2026-02-30 2026-11-02 eow eom +3d in 0d 3d "
        "3pm 6:15 6:15pm 0:00 24:00 12am 12pm 13pm 0am 9:30am noon 15:00 3-4pm 11-1pm 12-1am 11pm-1am 6:15-7:30 "
        "7:30pm-9pm 10:10-11:25 1-2 ~2h ~0m ~0h ~30m ~1.5h ~1h30m ~2h-1h 30-45m 45-30m 1-2h ~20m-45m 45m 2h 0m 90m "
        "1.5h for 0 x 3x 0x 99x twice once 3 times a per day month 1 31 32 other second weekdays 2w 0w 99 weeks days "
        "months fortnight monthly weekly daily biweekly yearly maybe #cs1110 # + / /chore /nosuch +tag ! !4 !9 @deep "
        "@x one-sitting split open runs by itself background the after:T12 before:t0 after: after:\"\" "
        "rrule:FREQ=DAILY rrule:BAD fri@3pm fri@25pm @3pm lunch dinner with lecture class cs1110 essay T1"
        ).split()  # fmt: skip


@settings(max_examples=500, deadline=None)
@given(
    st.lists(st.sampled_from(SOUP), min_size=1, max_size=9),
    st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2027, 12, 31, 23, 59)),
)
def test_any_jumble_of_grammar_words_parses_to_sane_fields(words: list[str], now: datetime) -> None:
    """Days, times and lengths in any order, against any clock: no crash, real times, and amounts that make sense."""
    fields = parse(" ".join(words), now, areas=AREAS, presets=DEFAULT_PRESETS, find_item=lambda t: None).fields
    for key in ("start_local", "end_local", "release_local", "due_local", "dtstart_local"):
        if key in fields:
            datetime.fromisoformat(fields[key])
    if "start_local" in fields:
        assert fields["end_local"] > fields["start_local"]
    if "rrule" in fields:
        assert is_valid_rule(fields["rrule"])
    for key in ("duration_units", "min_units", "ideal_units", "max_units"):
        assert fields.get(key, 1) > 0
    if fields.get("amount") == "elastic":
        assert fields["min_units"] <= fields["ideal_units"] <= fields["max_units"]
    assert 1 <= fields.get("importance", 3) <= 5
    format_line(fields)


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=40))
def test_any_text_at_all_parses_without_a_crash(text: str) -> None:
    parse(text, NOW, areas=AREAS, presets=DEFAULT_PRESETS, find_item=lambda t: None)


# Bugs these properties found (27 Oct), each as a minimal line, fixed the same day.


@pytest.mark.parametrize("text", ["party 11pm 2h sat", "movie 10:30pm for 2h fri", "x 23:59 eom"])
def test_an_event_that_crosses_midnight_ends_after_it_starts(text: str) -> None:
    fields = quick(text)
    assert fields["end_local"] > fields["start_local"]


@pytest.mark.parametrize("text", ["groceries /errand at 10am 45m", "laundry /chore at 3pm 2h", "x /errand sat 9am 90m"])
def test_a_length_after_a_time_is_kept_for_a_flexible_kind(text: str) -> None:
    fields = quick(text)
    assert "duration_units" in fields


def test_a_bare_day_offset_is_a_day_not_a_tag() -> None:
    fields = quick("essay +3d")
    assert fields.get("due_local") == "2026-10-21T23:59" and "tags" not in fields


def test_format_line_keeps_a_task_that_runs_by_itself() -> None:
    fields = quick("laundry every week ~2h runs by itself")
    assert quick(format_line(fields)) == fields


# the last: a time said after the day, which moves the time to that day (audit, 12 Nov: past 9999 it crashed)
@pytest.mark.parametrize("text", ["x 12/31/9999 23:59", "x oct 99999999999999999999", "x 12/31/9999 !high 23:59"])
def test_out_of_range_dates_do_not_crash(text: str) -> None:
    quick(text)


@pytest.mark.parametrize("text", ["x oct ²", "x every ² days", "x ² times a week", "x every month ²"])
def test_superscript_digits_do_not_crash(text: str) -> None:
    quick(text)


# dates.py on its own: every clock time, length and date form.


@settings(max_examples=200, deadline=None)
@given(st.integers(0, 23), st.integers(0, 59))
def test_twenty_four_hour_and_twelve_hour_times_agree(hour: int, minute: int) -> None:
    twelve = f"{hour % 12 or 12}:{minute:02d}{'am' if hour < 12 else 'pm'}"
    assert parse_time(twelve) == hour * 60 + minute
    assert parse_time(f"{hour:02d}:{minute:02d}") == hour * 60 + minute
    if minute == 0:
        assert parse_time(f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}") == hour * 60


@settings(max_examples=300, deadline=None)
@given(
    st.integers(1, 12), st.sampled_from(["", ":15", ":30", ":45"]), st.sampled_from(["", "am", "pm"]),
    st.integers(1, 12), st.sampled_from(["", ":10", ":30"]), st.sampled_from(["", "am", "pm"]),
)  # fmt: skip
def test_a_time_range_always_runs_forward_within_the_day(h1: int, m1: str, s1: str, h2: int, m2: str, s2: str) -> None:
    span = parse_time_range(f"{h1}{m1}{s1}-{h2}{m2}{s2}")
    if span is not None:
        assert 0 <= span[0] < span[1] <= 24 * 60


@settings(max_examples=200, deadline=None)
@given(st.integers(0, 12), st.integers(0, 59))
def test_lengths_in_hours_and_minutes(hours: int, minutes: int) -> None:
    assume(hours or minutes)
    assert parse_duration(f"{hours}h{minutes}m" if hours and minutes else f"{hours}h" if hours else f"{minutes}m") == (
        hours * 60 + minutes
    )


@settings(max_examples=300, deadline=None)
@given(st.dates(min_value=date(2026, 1, 1), max_value=date(2028, 12, 31)), st.sampled_from(sorted(WEEKDAY_NAMES)))
def test_weekdays_and_next_weekdays_land_in_the_right_week(today: date, name: str) -> None:
    day, used = read_date([name], 0, today)  # type: ignore[misc]
    assert used == 1 and day.weekday() == WEEKDAY_NAMES[name] and 0 <= (day - today).days <= 6
    later, used = read_date(["next", name], 0, today)  # type: ignore[misc]
    monday = today + timedelta(days=7 - today.weekday())
    assert used == 2 and later.weekday() == WEEKDAY_NAMES[name] and monday <= later < monday + timedelta(days=7)


@settings(max_examples=300, deadline=None)
@given(st.dates(min_value=date(2026, 1, 1), max_value=date(2028, 12, 31)), st.dates())
def test_a_month_and_day_is_its_next_occurrence(today: date, wanted: date) -> None:
    assume((wanted.month, wanted.day) != (2, 29))  # only in leap years: found or not
    said = (
        [f"{wanted.month}/{wanted.day}"],
        [f"{wanted.month}-{wanted.day}"],
        [f"{wanted:%b}".lower(), str(wanted.day)],
    )
    for words in said:
        found = read_date(words, 0, today)
        assert found is not None, words
        day, _ = found
        assert (day.month, day.day) == (wanted.month, wanted.day) and today <= day < today + timedelta(days=366)
