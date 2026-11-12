from datetime import date, datetime

import pytest

from friday.core.recurrence import describe, ending_before, next_occurrence, occurrences, read_repeat
from friday.core.time import to_utc

TODAY = date(2026, 10, 18)


@pytest.mark.parametrize(
    ("text", "rule", "words"),
    [
        ("mon", "FREQ=WEEKLY;BYDAY=MO", "Every Monday"),
        ("mon,wed,fri", "FREQ=WEEKLY;BYDAY=MO,WE,FR", "Every Mon, Wed and Fri"),
        ("weekdays", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "Every weekday"),
        ("day", "FREQ=DAILY", "Every day"),
        ("week", "FREQ=WEEKLY", "Every week"),
        ("2w thu", "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH", "Every other Thursday"),
        ("3w tue,thu", "FREQ=WEEKLY;INTERVAL=3;BYDAY=TU,TH", "Every 3 weeks on Tue and Thu"),
        ("month 15", "FREQ=MONTHLY;BYMONTHDAY=15", "Monthly on the 15th"),
        ("month 1", "FREQ=MONTHLY;BYMONTHDAY=1", "Monthly on the 1st"),
        ("mon until 12-11", "FREQ=WEEKLY;BYDAY=MO;UNTIL=20261211T235959", "Every Monday until Dec 11"),
        ("day until dec 11", "FREQ=DAILY;UNTIL=20261211T235959", "Every day until Dec 11"),
        ("rrule:FREQ=DAILY;INTERVAL=3", "FREQ=DAILY;INTERVAL=3", "Every 3 days"),
        ("rrule:freq=weekly;interval=2", "FREQ=WEEKLY;INTERVAL=2", "Every other week"),
        ("month", "FREQ=MONTHLY", "Monthly"),
        ("other week", "FREQ=WEEKLY;INTERVAL=2", "Every other week"),
        ("other tue", "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU", "Every other Tuesday"),
        ("4 weeks", "FREQ=WEEKLY;INTERVAL=4", "Every 4 weeks"),
        ("3 days", "FREQ=DAILY;INTERVAL=3", "Every 3 days"),
        ("2 months", "FREQ=MONTHLY;INTERVAL=2", "Every 2 months"),
        ("fortnight", "FREQ=WEEKLY;INTERVAL=2", "Every other week"),
    ],
)
def test_shorthand_becomes_a_rule_and_reads_back_in_words(text: str, rule: str, words: str) -> None:
    found = read_repeat(text.split(), 0, TODAY)
    assert found == (rule, len(text.split()))
    assert describe(rule) == words


@pytest.mark.parametrize("text", ["someday", "rrule:FREQ=SOMETIMES", "month 40", "2w"])
def test_words_that_are_not_repeats(text: str) -> None:
    assert read_repeat(text.split(), 0, TODAY) is None


def test_until_without_a_date_is_left_for_the_title() -> None:
    assert read_repeat(["mon", "until", "done"], 0, TODAY) == ("FREQ=WEEKLY;BYDAY=MO", 1)


def test_every_other_week_skips_weeks() -> None:
    times = occurrences(
        "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH",
        datetime(2026, 10, 22, 10),
        datetime(2026, 10, 1),
        datetime(2026, 11, 30),
    )
    assert [t.day for t in times] == [22, 5, 19]


def test_until_is_inclusive_of_its_day() -> None:
    times = occurrences(
        "FREQ=DAILY;UNTIL=20261021T235959",
        datetime(2026, 10, 19, 23, 0),
        datetime(2026, 10, 1),
        datetime(2026, 12, 1),
    )
    assert [t.day for t in times] == [19, 20, 21]


def test_weekly_series_keeps_its_local_time_across_a_dst_change() -> None:
    tz = "America/New_York"
    times = occurrences(
        "FREQ=WEEKLY;BYDAY=MO", datetime(2026, 10, 26, 8), datetime(2026, 10, 26), datetime(2026, 11, 10)
    )
    assert [t.hour for t in times] == [8, 8, 8]
    utc_hours = [to_utc(t, tz) // 60 % 24 for t in times]
    assert utc_hours == [12, 13, 13]  # EDT, then EST after Nov 1


def test_next_occurrence_and_cutting_a_rule_at_a_date() -> None:
    rule = "FREQ=WEEKLY;BYDAY=MO,WE"
    start = datetime(2026, 10, 19, 9)
    assert next_occurrence(rule, start, start) == datetime(2026, 10, 21, 9)
    cut = ending_before(rule, date(2026, 10, 28))
    assert describe(cut) == "Every Mon and Wed until Oct 27"
    assert occurrences(cut, start, start, datetime(2026, 12, 1))[-1] == datetime(2026, 10, 26, 9)


def test_describe_shows_count() -> None:
    assert describe("FREQ=DAILY;COUNT=5") == "Every day, 5 times"


def test_rules_said_in_words_every_few_weeks_and_ones_friday_has_no_words_for() -> None:
    assert describe("FREQ=WEEKLY;INTERVAL=3;BYDAY=MO") == "Every 3 weeks on Monday"
    assert describe("FREQ=HOURLY;INTERVAL=2") == "Repeats (FREQ=HOURLY;INTERVAL=2)"


def test_the_next_time_passes_over_the_ones_it_skips() -> None:
    start = datetime(2026, 10, 19, 10)
    rule = "FREQ=DAILY;EXDATE=20261020T100000,20261021T100000"
    assert next_occurrence(rule, start, start) == datetime(2026, 10, 22, 10)
