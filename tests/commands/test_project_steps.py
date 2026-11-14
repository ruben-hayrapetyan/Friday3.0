"""A project is judged by its steps (13 Nov: "I can see the steps of the project in the calendar plan — doesn't that
mean that it is planned before it's due?"). A project's own item only holds its steps: the planner plans the steps,
never the project, so the project has no blocks of its own. The plan's warnings called "CDJ Article" not planned
before its due though all three steps were planned days before it; and once the steps were all done, the planner
planned the project's own 6h15 as work."""

from pathlib import Path

import pytest

from friday.commands.queries import slipping
from friday.commands.registry import Ctx
from friday.commands.writer import Writer
from friday.planner.snapshot import snapshot_items, with_steps
from friday.planner.store import current_plan, load_settings
from tests.commands.helpers import App, new_app

DUE = "2026-10-23T17:00"  # Friday 5pm; the tests' clock is Monday 9am


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def article(app: App, due: str = DUE, draft_min: int = 180) -> dict[str, int]:
    """The client's project: three steps, each waiting on the one before, none with a due of its own."""
    project = app.do("add", title="CDJ Article", preset="Project", due=due, duration_min=375)["item"]["id"]
    ids = {"project": project}
    for title, minutes in (("Outline", 60), ("Draft", draft_min), ("Revise", 135)):
        ids[title] = app.do("add", title=title, parent_id=project, duration_min=minutes)["item"]["id"]
    app.do("depend", item_id=ids["Draft"], depends_on_id=ids["Outline"])
    app.do("depend", item_id=ids["Revise"], depends_on_id=ids["Draft"])
    return ids


def named(app: App) -> set[str]:
    """What the plan's warnings name: late work and slipping work, as the header's pill and the To-do lists read."""
    status = app.do("status")
    return {i["title"] for i in status["late_items"] + status["slipping"]}


def project_blocks(app: App, item_id: int) -> list[dict]:
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-26T00:00")
    return [b for b in plan["blocks"] if b["item_id"] == item_id]


# What it should do, from outside


def test_a_project_whose_steps_are_all_planned_before_its_due_isnt_called_unplanned(app: App) -> None:
    ids = article(app)
    app.do("replan")
    (project,) = app.do("projects")
    assert project["status"] == "on_track" and project["planned_finish"] < DUE
    assert all(project_blocks(app, ids[s]) for s in ("Outline", "Draft", "Revise"))
    assert "CDJ Article" not in named(app)  # it said "CDJ Article isn't planned before it's due"
    assert named(app) == set()


def test_a_step_that_doesnt_fit_before_its_projects_due_is_named_not_the_project(app: App) -> None:
    # Due tomorrow at 5pm with a 30-hour draft: the step is what doesn't fit, and it's due when its project is.
    ids = article(app, due="2026-10-20T17:00", draft_min=30 * 60)
    app.do("replan")
    status = app.do("status")
    warned = {i["title"]: i for i in status["late_items"] + status["slipping"]}
    assert "CDJ Article" not in warned
    # Revise, after the draft, can't be done in time: it's named, due when its project is
    assert warned["Revise"]["item_id"] == ids["Revise"]
    assert {i["due"] for i in warned.values()} == {"2026-10-20T17:00"}


def test_a_project_whose_steps_are_all_done_isnt_planned_as_work_of_its_own(app: App) -> None:
    ids = article(app)
    for step in ("Outline", "Draft", "Revise"):
        app.do("done", id=ids[step])
    app.do("replan")
    assert project_blocks(app, ids["project"]) == []  # it planned the project's own 6h15 on Wednesday
    assert app.do("projects")[0]["status"] == "done"
    assert named(app) == set()


def test_a_project_without_steps_is_still_planned_as_itself(app: App) -> None:
    project = app.do("add", title="Move house", preset="Project", due=DUE, duration_min=120)["item"]["id"]
    app.do("replan")
    assert project_blocks(app, project)
    assert "Move house" not in named(app)


def test_a_project_whose_only_step_was_deleted_is_planned_as_itself_again(app: App) -> None:
    project = app.do("add", title="Move house", preset="Project", due=DUE, duration_min=120)["item"]["id"]
    step = app.do("add", title="Pack", parent_id=project, duration_min=60)["item"]["id"]
    app.do("drop", id=step)
    app.do("replan")
    assert project_blocks(app, project)


# How it works inside


def test_with_steps_counts_steps_done_or_open_but_not_deleted(app: App) -> None:
    ids = article(app)
    lone = app.do("add", title="Move house", preset="Project", due=DUE, duration_min=120)["item"]["id"]
    gone = app.do("add", title="Pack", parent_id=lone, duration_min=60)["item"]["id"]
    app.do("drop", id=gone)
    assert with_steps(app.conn, 1) == {ids["project"]}
    app.do("done", id=ids["Outline"])
    assert with_steps(app.conn, 1) == {ids["project"]}


def test_the_snapshot_leaves_out_a_project_with_nothing_left_in_it_nested_or_not(app: App) -> None:
    ids = article(app)
    inner = app.do("add", title="Figures", parent_id=ids["project"], duration_min=60)["item"]["id"]
    chart = app.do("add", title="Chart", parent_id=inner, duration_min=30)["item"]["id"]
    settings = load_settings(app.conn, 1)

    def kept() -> set[int]:
        return {i.id for i in snapshot_items(app.conn, app.now_utc, settings, 1)}  # type: ignore[misc]

    assert {ids["project"], inner, chart} <= kept()
    app.do("done", id=chart)
    assert inner not in kept() and ids["project"] in kept()  # Figures is finished; the article still has steps
    for step in ("Outline", "Draft", "Revise"):
        app.do("done", id=ids[step])
    assert ids["project"] not in kept()  # left with only finished Figures: nothing of its own to plan


def test_slipping_skips_a_project_and_gives_a_step_its_projects_due(app: App) -> None:
    ids = article(app, due="2026-10-20T17:00", draft_min=30 * 60)
    app.do("replan")
    ctx = Ctx(app.conn, Writer(app.conn, 1), app.now_utc, "you", 1, load_settings(app.conn, 1))
    saved = current_plan(app.conn, 1)
    found = {i.title: i for i in slipping(ctx, saved, set())}  # nothing called late by the planner: all checked here
    assert "CDJ Article" not in found
    assert found["Revise"].due == "2026-10-20T17:00" and found["Revise"].item_id == ids["Revise"]


def test_the_morning_brief_lists_a_projects_steps_not_the_project(app: App) -> None:
    # Due tomorrow (hard, the Project kind): the brief named "CDJ Article", "not today", beside its steps planned today.
    ids = article(app, due="2026-10-20T17:00")
    app.do("replan")
    rocks = {r["title"]: r for r in app.do("brief")["rocks"]}
    assert "CDJ Article" not in rocks
    assert "Outline" in rocks and rocks["Outline"]["due"] == "2026-10-20T17:00"
    assert rocks["Outline"]["planned_min"] > 0
    assert ids["Outline"] == rocks["Outline"]["item_id"]


def test_a_step_with_no_due_of_its_own_keeps_its_projects_deadline() -> None:
    # The planner gave a step its project's due but not its firmness: "none" never held it to the project's due.
    from friday.core.items import Item
    from friday.planner.build import firmness_of

    project = Item(title="CDJ Article", id=1, due_utc="2026-10-23T21:00", firmness="hard")
    loose = Item(title="Errands", id=2, firmness="soft")
    by_id = {1: project, 2: loose}
    assert firmness_of(Item(title="Draft", id=3, parent_id=1, firmness="none"), by_id) == "hard"
    # its own due keeps its own firmness (a template's soft Outline due early in the project)
    assert (
        firmness_of(Item(title="Outline", id=4, parent_id=1, due_utc="2026-10-20T03:59", firmness="soft"), by_id)
        == "soft"
    )
    assert firmness_of(Item(title="Milk", id=5, parent_id=2, firmness="none"), by_id) == "none"  # no due to keep
    assert firmness_of(Item(title="Alone", id=6, firmness="none"), by_id) == "none"


def test_a_step_that_cant_make_its_projects_hard_due_is_late_work(app: App) -> None:
    # With no deadline of its own, Revise was only "not planned" (soft, in the warning color); its project's due is
    # hard, so the planner plans it as late work and says how late, with the options to make room.
    ids = article(app, due="2026-10-20T17:00", draft_min=30 * 60)
    app.do("replan")
    late = {i["item_id"]: i for i in app.do("status")["late_items"]}
    assert ids["Revise"] in late and late[ids["Revise"]]["hours"] > 0
    assert late[ids["Revise"]]["due"] == "2026-10-20T17:00"
    assert ids["project"] not in late
