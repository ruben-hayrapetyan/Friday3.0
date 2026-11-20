"""A step with no room before its due holds the steps after it (20 Nov, a user's notes, carried over from 0.5.3: "'no
room before it's due' however other sub-tasks that are dependent on it are scheduled, which makes no sense"; your
answer: "Later steps wait"). Whole system, a scratch Friday, Monday 19 October 2026 9am, a lab until 6pm."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-10-19T09:00")
    app.do("add", title="Lab", when="fixed", start="2026-10-19T09:00", end="2026-10-19T18:00")
    return app


def essay(app: App, thesis_pointless: bool = True) -> dict[str, int]:
    """LING Final Essay: Share, then Preliminary Thesis (5h, due tonight at 9: no room), then a draft due Thursday."""
    made = app.do("add", title="LING Final Essay", preset="Project", due="2026-11-14T17:00", duration_min=60)
    pid = made["item"]["id"]
    out = {"project": pid}
    for name, due, minutes in (
        ("Share the representation", "2026-10-19T23:00", 60),
        ("Preliminary Thesis", "2026-10-19T21:00", 300),
        ("Partial first draft", "2026-10-22T17:00", 240),
        ("Rubric", "2026-10-24T17:00", 60),
    ):
        step = app.do("add", title=name, parent_id=pid, due=due, duration_min=minutes, firmness="hard")
        out[name] = step["item"]["id"]
    if thesis_pointless:
        app.do("edit", id=out["Preliminary Thesis"], expires=True)
    replan(app.conn, app.now_utc)
    return out


def planned(app: App, item: int) -> bool:
    return any(b["item_id"] == item for b in app.table("blocks") if b["plan_id"] == app.table("plans")[-1]["id"])


def shown(app: App, ids: dict[str, int]) -> dict[str, tuple[bool, str | None, int | None]]:
    """Each step as the project's page reads it: planned, its later finish, what it waits for."""
    [project] = [p for p in app.do("projects") if p["item"]["id"] == ids["project"]]
    return {
        name: (planned(app, i), project["step_finish"].get(str(i)), (project.get("waits_for") or {}).get(str(i)))
        for name, i in ids.items()
        if name != "project"
    }


def test_the_notes_case_the_steps_after_one_with_no_room_wait_for_it_and_arent_planned(app: App) -> None:
    ids = essay(app)
    steps = shown(app, ids)
    assert steps["Share the representation"][0]
    assert steps["Preliminary Thesis"] == (False, None, None)  # "No room before its due": no later day either
    thesis = ids["Preliminary Thesis"]
    assert steps["Partial first draft"] == (False, None, thesis)  # "Waits for Preliminary Thesis, which has no room"
    assert steps["Rubric"] == (False, None, thesis)


def test_a_step_made_any_time_doesnt_wait(app: App) -> None:
    ids = essay(app)
    app.do("step_any_time", id=ids["Partial first draft"], any_time=True)
    replan(app.conn, app.now_utc)
    steps = shown(app, ids)
    assert steps["Partial first draft"][0] and steps["Partial first draft"][2] is None
    assert steps["Rubric"][0]  # it waits for the draft, which is planned


def test_a_step_still_worth_doing_late_is_planned_late_and_the_rest_follow(app: App) -> None:
    ids = essay(app, thesis_pointless=False)
    steps = shown(app, ids)
    assert steps["Preliminary Thesis"][0]  # after its due, as late work
    assert steps["Partial first draft"][0] and steps["Partial first draft"][2] is None


def test_once_the_stuck_step_is_done_the_rest_are_planned(app: App) -> None:
    ids = essay(app)
    app.do("done", id=ids["Preliminary Thesis"])
    replan(app.conn, app.now_utc)
    steps = shown(app, ids)
    assert steps["Partial first draft"][0] and steps["Partial first draft"][2] is None
