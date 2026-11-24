"""An item's detail (To-do → open an item → Planned sessions) agrees with the plan (23 Nov, the agreement check,
web/scripts/agreement-check.mjs): a project whose steps had time said "Nothing planned. Friday will find time once it
has a due date or an estimate." though it had both. A project's sessions are its steps'; and where something has no
time, the detail says why in the plan's words (as the Projects page does), not a guess. Monday 19 Oct 2026, 9am."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def project(app: App) -> tuple[int, list[int]]:
    root = app.do("add", title="Robotics demo", preset="Project", due="2026-10-23T17:00", firmness="hard")["item"]["id"]
    steps = [app.do("add", title=t, parent_id=root, duration_min=m)["item"]["id"]
             for t, m in (("Design the arm", 120), ("Build the arm", 180))]  # fmt: skip
    app.do("depend", item_id=steps[1], depends_on_id=steps[0])
    app.do("replan")
    return root, steps


def test_a_projects_sessions_are_its_steps(app: App) -> None:
    root, steps = project(app)
    detail = app.do("item", id=root)
    planned = [b for b in app.do("plan")["blocks"] if b["item_id"] in steps]
    assert planned, "the steps have time"
    assert sorted(b["key"] for b in detail["blocks"]) == sorted(b["key"] for b in planned)
    assert {b["title"] for b in detail["blocks"]} == {"Design the arm", "Build the arm"}  # each named by its step


def test_a_step_waiting_behind_one_with_no_room_says_so_in_the_plans_words(tmp_path: Path) -> None:
    """The thesis can't all fit before its due tonight and is pointless late, so it keeps what fits; the draft after it
    waits (tests/commands/test_waits_one_graph.py's project)."""
    from tests.commands.test_waits_one_graph import project_with_no_room

    app = new_app(tmp_path, now="2026-10-19T09:00")
    app.do("add", title="Lab", when="fixed", start="2026-10-19T09:00", end="2026-10-19T18:00")
    ids = project_with_no_room(app)
    app.do("replan")
    detail = app.do("item", id=ids["draft"])
    assert detail["blocks"] == []
    assert detail["note"] == "Waits for “LING Final Essay thesis”, which has no room before its due"


def test_planned_work_has_no_note(app: App) -> None:
    _, steps = project(app)
    assert app.do("item", id=steps[0])["note"] is None
