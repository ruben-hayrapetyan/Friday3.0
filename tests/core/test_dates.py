from datetime import date

import pytest

from friday.core.dates import parse_duration, parse_time, read_date, read_moment

TODAY = date(2026, 10, 18)  # a Sunday


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("30m", 30),
        ("90m", 90),
        ("1h", 60),
        ("1.5h", 90),
        ("1h30m", 90),
        ("2h5m", 125),
        ("h", None),
        ("", None),
        ("0m", None),
        ("3x", None),
    ],
)
def test_durations(text: str, minutes: int | None) -> None:
    assert parse_duration(text) == minutes


@pytest.mark.parametrize(
    ("text", "minute"),
    [
        ("15:00", 900),
        ("3pm", 900),
        ("9:30am", 570),
        ("12am", 0),
        ("12pm", 720),
        ("0:05", 5),
        ("24:00", None),
        ("13pm", None),
        ("noon", 720),
        ("midnight", 1439),
    ],
)
def test_times(text: str, minute: int | None) -> None:
    assert parse_time(text) == minute


@pytest.mark.parametrize(
    ("words", "expected", "used"),
    [
        (["today"], date(2026, 10, 18), 1),
        (["tomorrow"], date(2026, 10, 19), 1),
        (["sun"], date(2026, 10, 18), 1),  # today is that weekday
        (["mon"], date(2026, 10, 19), 1),
        (["friday"], date(2026, 10, 23), 1),
        (["+3d"], date(2026, 10, 21), 1),
        (["in", "3d"], date(2026, 10, 21), 2),
        (["10-14"], date(2027, 10, 14), 1),  # already past this year
        (["10-20"], date(2026, 10, 20), 1),
        (["oct", "14"], date(2027, 10, 14), 2),
        (["december", "1"], date(2026, 12, 1), 2),
        (["2026-10-14"], date(2026, 10, 14), 1),
        (["next", "week"], date(2026, 10, 19), 2),
        (["eow"], date(2026, 10, 18), 1),
        (["eom"], date(2026, 10, 31), 1),
    ],
)
def test_dates(words: list[str], expected: date, used: int) -> None:
    assert read_date(words, 0, TODAY) == (expected, used)


@pytest.mark.parametrize("word", ["someday", "13-40", "2026-02-30", "in"])
def test_words_that_are_not_dates(word: str) -> None:
    assert read_date([word], 0, TODAY) is None


def test_date_and_time_join_with_a_space_or_an_at_sign() -> None:
    assert read_moment(["fri", "3pm"], 0, TODAY) == (date(2026, 10, 23), 900, 2)
    assert read_moment(["fri@3pm"], 0, TODAY) == (date(2026, 10, 23), 900, 1)
    assert read_moment(["oct", "20", "9:30am"], 0, TODAY) == (date(2026, 10, 20), 570, 3)
    assert read_moment(["5pm"], 0, TODAY) == (TODAY, 1020, 1)
    assert read_moment(["tue", "reading"], 0, TODAY) == (date(2026, 10, 20), None, 1)
