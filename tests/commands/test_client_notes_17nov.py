"""A client's notes, 17 Nov (Friday Notes.pdf): a rule clash in the Inbox said "moves Prep: CHEM 2090 Prelim 3 to
10:15am from 10:15am"; and "focus on exams starting 5 days before", the rewording the client tried, wasn't read as exam
focus (it went to the AI, and a rule finishing exam prep 5 days early clashed in its place)."""

from datetime import datetime
from types import SimpleNamespace as NS

import pytest

from friday.core.rule_text import read, sentence
from friday.core.time import to_utc
from friday.planner.views import cost_said

TZ = "America/New_York"


def at(local: str) -> int:
    return to_utc(datetime.fromisoformat(local), TZ)


def block(start: str, end: str) -> NS:
    return NS(start_utc=at(start), end_utc=at(end))


SNAPSHOT = NS(settings={"time": NS(timezone=TZ, day_start="04:00")}, now_utc=at("2026-11-16T09:00"))


def test_a_clash_that_keeps_the_first_start_says_the_times_that_change() -> None:
    was = [block("2026-11-18T10:15", "2026-11-18T11:15"), block("2026-11-18T14:00", "2026-11-18T15:00")]
    now = [block("2026-11-18T10:15", "2026-11-18T12:15")]
    said = cost_said("finish_early", "Prep: CHEM 2090 Prelim 3", was, now, SNAPSHOT)
    assert said == "plans Prep: CHEM 2090 Prelim 3 10:15am–12:15pm instead of 10:15am–11:15am and 2pm–3pm"
    assert "to 10:15am from 10:15am" not in said


def test_a_clash_that_moves_the_start_still_says_from_when() -> None:
    was = [block("2026-11-18T10:15", "2026-11-18T11:15")]
    now = [block("2026-11-18T13:00", "2026-11-18T14:00")]
    assert cost_said("finish_early", "Lab 9", was, now, SNAPSHOT) == "moves Lab 9 to 1pm from 10:15am"


@pytest.mark.parametrize(
    ("words", "days"),
    [
        ("focus on exams starting 5 days before", 5),
        ("Focus on an exam's course starting 5 days before it", 5),
        ("focus on exams from 3 days before", 3),
        ("starting 2 days before a final, study only for that class", 2),
        ("focus on exams 5 days before", 5),  # as before
    ],
)
def test_focus_starting_some_days_before_is_exam_focus(words: str, days: int) -> None:
    reading, _ = read(words)
    assert reading is not None and reading.kind == "exam_focus" and reading.amount == days
    assert sentence(reading) == f"Focus on an exam's course {days} days before it"


def test_finishing_prep_early_is_still_finishing_early() -> None:
    reading, _ = read("finish exam prep 5 days before")
    assert reading is not None and reading.kind == "early"
