"""An exam's own day as its focus, and an exam focus rule never replaced unsaid (19 Nov: you added "On the day of a
prelim, spend the time until the prelim studying for it"; the AI could only read it as "Focus on an exam's course the
day before it", it took the place of your "5 days before" rule while saying "Added", and you couldn't find it in Rules:
"also i added a rule but i cna't see it in my rules - is this a bug?"; your answer "yes fix").
Whole system, Monday 19 October 2026 9am in New York."""

from pathlib import Path

import pytest

from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app

SAID = "On the day of a prelim, spend the time until the prelim studying for it"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def waits(app: App, item: int) -> bool:
    found = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items[f"item:{item}"].release_utc
    return found is not None and found > app.now_utc


def test_the_sentence_reads_as_the_exams_own_day() -> None:
    from friday.core.rule_text import read_all

    (reading,), _ = read_all(SAID)
    assert reading.kind == "exam_focus" and reading.amount == 0


def test_it_says_its_day_not_the_day_before(app: App) -> None:
    read = app.do("rule_read", text=SAID)
    assert read["sentence"] == "Focus on an exam's course on its day, until it starts"


def test_on_the_exams_day_other_courses_wait_until_it_and_not_the_day_before(app: App) -> None:
    app.do("add", title="MATH 2940 Prelim 2", preset="Exam", start="2026-10-20T19:30", end="2026-10-20T21:00")
    app.do("rule_add", text=SAID, overrides={}, strength="Always")
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-26T12:00", duration_min=60)
    essay_id = essay["item"]["id"]
    assert not waits(app, essay_id)  # Monday, the day before the prelim: nothing waits
    app.at("2026-10-20T08:00")
    assert waits(app, essay_id)  # Tuesday, the prelim's day: other courses wait until it's over
    assert app.do("exams")[0]["focus_from"] == "2026-10-20T04:00"  # from the day's start (4am)


def test_a_new_exam_focus_rule_says_which_one_it_replaces(app: App) -> None:
    app.do("rule_add", text="focus on exams 5 days before", overrides={}, strength="Always")
    read = app.do("rule_read", text=SAID)
    assert read["replaces"] == "Focus on an exam's course 5 days before it"  # as Rules lists it
    out = app.do("rule_add", text=SAID, overrides={}, strength="Always")
    assert out["message"] == (
        "Replaced “Focus on an exam's course 5 days before it” with: "
        "Focus on an exam's course on its day, until it starts"
    )
    (rule,) = [r for r in app.do("rules") if r["type"] == "exam_focus"]
    assert rule["words"] == SAID  # your words, as you typed them, kept with it


def test_one_exam_can_be_set_to_its_day_and_another_off(app: App) -> None:
    made = app.do("add", title="CHEM Quiz", preset="Exam", start="2026-10-19T19:30", end="2026-10-19T20:00")
    quiz = made["item"]["id"]
    final = app.do("add", title="MATH Final", preset="Exam", start="2026-10-19T19:30", end="2026-10-19T21:00")
    app.do("rule_add", text="focus on exams 2 days before", overrides={}, strength="Always")
    app.do("settings_set", key="exam_focus_each", value={str(quiz): 0, str(final["item"]["id"]): None})
    shown = {e["item"]["id"]: e for e in app.do("exams")}
    assert (shown[quiz]["focus_days"], shown[quiz]["focus_from"]) == (0, "2026-10-19T04:00")
    assert (shown[final["item"]["id"]]["focus_days"], shown[final["item"]["id"]]["focus_from"]) == (None, None)
