"""Steps waiting for one that has no room before its due (19 Nov, a user's notes: "'no room before it's due' - other
tasks in the project are dependent on it (steps 3, 4, 5). how does friday plan to handle that?"; your answer: "keep
them waiting, both ask in inbox and also say why. however, the asking should follow something similar to the asking
for stuff being late. things should not constantly be asked").

A step that's pointless once late (it expires at its due, as an exam's prep does) and has no room before its due isn't
planned; the steps that wait for it in its project's order wait, saying for what, and the Inbox's late question names
them, with "Let them go on without it" and "Drop it". Leaving it late stands a day, as any late work does.
Whole system, through the commands and the planner, Monday 19 Oct 2026 9am."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app
from tests.commands.test_project_planning import blocks, minutes, project


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=14)


def steps(app: App) -> tuple[int, list[int]]:
    """The notes' project: 1, 2 any time, 3 then, 4 then, 5 any time; step 2 due tomorrow 10am with no room."""
    app.do("add", title="busy", when="fixed", start="2026-10-19T09:00", end="2026-10-20T10:00")
    made, ids = project(app, "2026-10-30T17:00", [("Step 1", 180), ("Step 2", 300), ("Step 3", 240), ("Step 4", 60),
                                                  ("Step 5", 120)])  # fmt: skip
    app.do("edit", id=ids[1], due="2026-10-20T10:00", expires=True)
    app.do("step_any_time", id=ids[1], any_time=True)
    app.do("step_any_time", id=ids[4], any_time=True)
    replan(app.conn, app.now_utc)
    return made, ids


def late_decision(app: App) -> dict | None:
    return next((d for d in app.do("status")["decisions"] if d["kind"] == "late"), None)


def test_the_steps_that_wait_for_it_say_so_in_the_project(app: App) -> None:
    made, (s1, s2, s3, s4, s5) = steps(app)
    found = blocks(app)
    assert minutes(found.get(s2, [])) == 0 and minutes(found.get(s3, [])) == 0 and minutes(found.get(s4, [])) == 0
    (shown,) = [p for p in app.do("projects") if p["item"]["id"] == made]
    assert shown["waits_for"] == {str(s3): s2, str(s4): s2}  # step 5 doesn't wait; step 1 is above it


def test_the_inbox_asks_once_naming_what_waits(app: App) -> None:
    _, (s1, s2, s3, s4, s5) = steps(app)
    asked = late_decision(app)
    assert asked is not None
    (item,) = [i for i in asked["items"] if i["item_id"] == s2]
    assert [w["title"] for w in item["waiting"]] == ["Step 3", "Step 4"]
    assert not [i for i in asked["items"] if i["item_id"] in (s3, s4)], "the waiting steps aren't asked about apart"


def test_letting_them_go_on_without_it_plans_them(app: App) -> None:
    made, (s1, s2, s3, s4, s5) = steps(app)
    app.do("step_any_time", id=s3, any_time=True)  # "Let them go on without it"
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert minutes(found.get(s3, [])) == 240 and minutes(found.get(s4, [])) == 60
    (shown,) = [p for p in app.do("projects") if p["item"]["id"] == made]
    assert shown["waits_for"] == {}


def test_dropping_it_lets_the_rest_go_on(app: App) -> None:
    made, (s1, s2, s3, s4, s5) = steps(app)
    app.do("drop", id=s2)
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert minutes(found.get(s3, [])) == 240 and minutes(found.get(s4, [])) == 60
    assert late_decision(app) is None or not [i for i in late_decision(app)["items"] if i["item_id"] == s2]


def test_leaving_it_late_keeps_them_waiting_and_isnt_asked_again_that_day(app: App) -> None:
    made, (s1, s2, s3, s4, s5) = steps(app)
    app.do("late_accept", item_ids=[s2])
    assert late_decision(app) is None
    (shown,) = [p for p in app.do("projects") if p["item"]["id"] == made]
    assert shown["waits_for"] == {str(s3): s2, str(s4): s2}  # still waiting, still saying why
