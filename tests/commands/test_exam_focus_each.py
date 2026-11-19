"""Exam focus for each exam (19 Nov, a user's notes: "what is the point of this dropdown if it affects all classes'
exams and not just this one? ... you wouldn't study as much for a quiz compared to a prelim (and compared to a
final). u also might not need to study as much for an easy class compared to a hard class"; your answer: "do each
exam however again this should keep in mind that other people that aren't students don't have exams").

Each exam can have its own days before it (or none); an exam without its own follows the rule in Rules, if there is
one; with neither, nothing waits, as for anyone without exams. Whole system, Monday 19 October 2026 9am."""

from pathlib import Path

import pytest

from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def exam(app: App, title: str, day: str) -> int:
    return app.do("add", title=title, preset="Exam", start=f"{day}T19:30", end=f"{day}T21:00")["item"]["id"]


def waits(app: App, item: int) -> bool:
    """Whether the task is held back until an exam is over."""
    found = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items[f"item:{item}"].release_utc
    return found is not None and found > app.now_utc


def own(app: App, exam_id: int, days: int | None) -> None:
    each = dict(app.do("settings")["exam_focus_each"])
    each.pop(str(exam_id), None)
    app.do("settings_set", key="exam_focus_each", value=each | ({str(exam_id): days} if days is not None else {}))


def focus_of(app: App, exam_id: int) -> tuple[str | None, int | None, bool]:
    shown = next(e for e in app.do("exams") if e["item"]["id"] == exam_id)
    return shown["focus_from"], shown["focus_days"], shown["focus_own"]


def test_without_a_rule_or_its_own_days_nothing_waits(app: App) -> None:
    quiz = exam(app, "CHEM 2090 Quiz", "2026-10-20")
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-26T12:00", duration_min=60)
    assert not waits(app, essay["item"]["id"])
    assert focus_of(app, quiz) == (None, None, False)


def test_each_exam_has_its_own_days(app: App) -> None:
    quiz = exam(app, "CHEM 2090 Quiz", "2026-10-23")
    final = exam(app, "MATH 2940 Final", "2026-10-23")
    own(app, quiz, 1)
    own(app, final, 5)
    assert focus_of(app, quiz) == ("2026-10-22T19:30", 1, True)
    assert focus_of(app, final) == ("2026-10-18T19:30", 5, True)
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-27T12:00", duration_min=60)
    assert waits(app, essay["item"]["id"])  # the final's five days have begun
    own(app, final, 0)  # off for the final alone
    assert focus_of(app, final) == (None, 0, True)
    assert not waits(app, essay["item"]["id"])  # the quiz's one day hasn't begun


def test_an_exam_without_its_own_follows_the_rule_and_one_of_its_own_wins(app: App) -> None:
    prelim = exam(app, "MATH 2940 Prelim 2", "2026-10-23")
    app.do("rule_add", text="focus on exams 2 days before")
    assert focus_of(app, prelim) == ("2026-10-21T19:30", 2, False)
    own(app, prelim, 5)
    assert focus_of(app, prelim) == ("2026-10-18T19:30", 5, True)
    own(app, prelim, None)  # back to the rule
    assert focus_of(app, prelim) == ("2026-10-21T19:30", 2, False)
