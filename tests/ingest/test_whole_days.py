"""An event timed from midnight to 11:59 PM is a whole-day one (3 Nov: "don't make full day events actually look like
they take the full day"): the Mac gives some birthdays so, drawn the height of the day and counted busy."""

import re

from hypothesis import given
from hypothesis import strategies as st

from friday.ingest.ics import Reading, classify, whole_days

NONE = re.compile(r"(?!x)x")
READ = Reading(due=NONE, exam=NONE, lesson=NONE)


# glass box: the times it takes and the days it gives


def test_midnight_to_eleven_fifty_nine_is_that_day() -> None:
    assert whole_days("2026-11-05T00:00", "2026-11-05T23:59") == ("2026-11-05", "2026-11-06")


def test_midnight_to_a_later_midnight_is_the_days_between() -> None:
    assert whole_days("2026-11-05T00:00", "2026-11-07T00:00") == ("2026-11-05", "2026-11-07")


def test_over_several_days_to_eleven_fifty_nine() -> None:
    assert whole_days("2026-12-31T00:00", "2027-01-02T23:59") == ("2026-12-31", "2027-01-03")


def test_anything_else_is_timed() -> None:
    assert whole_days("2026-11-05T00:00", "2026-11-05T00:00") is None  # nothing long
    assert whole_days("2026-11-05T00:01", "2026-11-05T23:59") is None
    assert whole_days("2026-11-05T00:00", "2026-11-05T23:30") is None
    assert whole_days("2026-11-05T09:00", "2026-11-06T00:00") is None
    assert whole_days("2026-11-05T00:00", None) is None


@given(st.dates(), st.integers(0, 23), st.integers(0, 59), st.integers(0, 3), st.integers(0, 23), st.integers(0, 59))
def test_whole_days_start_at_the_events_start_and_end_after_it(day, h1, m1, extra, h2, m2) -> None:  # type: ignore[no-untyped-def]
    from datetime import timedelta

    start, end = f"{day}T{h1:02}:{m1:02}", f"{day + timedelta(days=extra)}T{h2:02}:{m2:02}"
    days = whole_days(start, end)
    whole = (h1, m1) == (0, 0) and ((h2, m2) == (23, 59) or ((h2, m2) == (0, 0) and extra > 0))
    assert (days is not None) == whole
    if days:
        assert days[0] == str(day) and days[1] > days[0]


# black box: what reading such an event proposes


def test_a_birthday_timed_over_its_day_comes_in_as_a_whole_day_that_isnt_busy() -> None:
    (only,) = classify("Jasper's Birthday", "2026-11-05T00:00", "2026-11-05T23:59", None, None, READ)
    assert only.fixed
    assert only.input["start"] == "2026-11-05T00:00" and only.input["end"] == "2026-11-06T00:00"
    assert only.input["blocks_time"] is False


def test_an_ordinary_timed_event_is_left_as_it_is() -> None:
    (only,) = classify("Dentist", "2026-11-05T10:00", "2026-11-05T11:00", None, None, READ)
    assert only.input["start"] == "2026-11-05T10:00" and only.input["end"] == "2026-11-05T11:00"
    assert "blocks_time" not in only.input
