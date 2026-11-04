"""When you do work with no due date, read from recorded sittings (learn/undated.py, 3 Nov)."""

from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.learn.undated import MIN_DAYS, MIN_HOURS, SHARE, Habit, clock_said, habit, sentence

MON = datetime(2026, 10, 19)


def sit(day: int, start: str, minutes: int) -> tuple[datetime, datetime]:
    h, m = map(int, start.split(":"))
    at = MON + timedelta(days=day, hours=h, minutes=m)
    return at, at + timedelta(minutes=minutes)


# black box: what is read as a habit


def test_afternoons_and_evenings_read_as_that_window() -> None:
    found = habit([sit(d, "14:00", 90) for d in range(5)] + [sit(d, "20:00", 60) for d in range(5)])
    assert found is not None
    assert (found.start, found.end) == (14, 21)
    assert found.days == 5 and found.share == 1.0 and round(found.hours, 1) == 12.5


def test_late_nights_past_midnight_read_as_one_window() -> None:
    found = habit([sit(d, "23:00", 120) for d in range(4)])
    assert found is not None and (found.start, found.end) == (23, 1)


def test_too_little_or_too_few_days_says_nothing() -> None:
    assert habit([sit(d, "14:00", 60) for d in range(4)]) is None  # 4 h
    assert habit([sit(d, "14:00", 180) for d in range(3)]) is None  # 3 days


def test_work_spread_over_the_day_says_nothing() -> None:
    spread = [sit(d, f"{h:02d}:00", 60) for d in range(6) for h in range(6, 24, 1)]
    assert habit(spread) is None


def test_a_rare_late_night_doesnt_stretch_the_window() -> None:
    usual = [sit(d, "15:00", 120) for d in range(10)]  # 20 h
    found = habit([*usual, sit(3, "23:00", 60)])  # an hour outside: under a tenth
    assert found is not None and (found.start, found.end) == (15, 17)


def test_the_rule_in_the_words_the_rules_page_reads() -> None:
    assert sentence(Habit(14, 22, 10, 1, 5)) == "undated work only between 2pm and 10pm"
    assert sentence(Habit(23, 1, 10, 1, 5)) == "undated work only between 11pm and 1am"
    assert [clock_said(h) for h in (0, 9, 12, 13)] == ["12am", "9am", "12pm", "1pm"]


# glass box: the window holds its share, and nothing shorter would


@settings(max_examples=150, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 20), st.integers(0, 23), st.integers(15, 240)), min_size=1, max_size=40))
def test_the_window_found_is_the_shortest_holding_its_share(raw: list[tuple[int, int, int]]) -> None:
    sittings = [sit(d, f"{h:02d}:00", m) for d, h, m in raw]
    found = habit(sittings)
    total = sum((e - s).total_seconds() / 60 for s, e in sittings)
    # the planning days each sitting touches (they start at 4am): a sitting from 1am to 5am is on two
    days = {(at - timedelta(hours=4)).date() for s, e in sittings for at in (s, e - timedelta(minutes=1))}
    if total / 60 < MIN_HOURS or len(days) < MIN_DAYS:
        assert found is None
        return
    if found is None:
        return  # spread wider than a waking day
    span = (found.end - found.start) % 24 or 24
    assert found.share >= SHARE - 1e-9
    assert 1 <= span <= 16
