"""Finished projects (commands/archive.py). Glass box: what archiving keeps to bring back, and the estimate the
Finished shelf compares against (leaf steps' lengths, dropped ones left out). Black box through the commands: archive,
unarchive, delete and the Finished list, with Undo; something that isn't a project refused."""

from pathlib import Path

import pytest

from friday.commands.archive import ARCHIVED
from friday.core.items import FieldError
from friday.planner.store import kv_get
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-09T09:00", horizon_days=14)


def essay(app: App) -> tuple[int, dict[str, int]]:
    project = app.do("add", title="Essay", preset="Project", due="2026-11-20T17:00", duration_min=300)["item"]["id"]
    steps = {
        name: app.do("add", title=name, parent_id=project, duration_min=minutes)["item"]["id"]
        for name, minutes in (("Outline", 60), ("Draft", 180), ("Revise", 60))
    }
    return project, steps


def status(app: App, item_id: int) -> str:
    return next(r["status"] for r in app.table("items") if r["id"] == item_id)


# Glass box


def test_archiving_keeps_the_open_steps_it_dropped(app: App) -> None:
    project, steps = essay(app)
    app.do("done", id=steps["Outline"])
    app.do("project_archive", id=project)
    kept = kv_get(app.conn, ARCHIVED, {})[str(project)]["steps"]
    assert sorted(kept) == sorted([steps["Draft"], steps["Revise"]])  # the done one wasn't dropped


def test_the_estimate_is_the_steps_lengths_without_the_dropped_ones(app: App) -> None:
    project, steps = essay(app)
    app.do("drop", id=steps["Revise"])  # you dropped it before archiving: not part of the plan any more
    app.at("2026-11-10T13:00").do("log", id=steps["Draft"], start="2026-11-10T09:00", end="2026-11-10T12:30")
    app.do("project_archive", id=project)
    [finished] = app.do("projects_finished")
    assert finished["estimate_min"] == 60 + 180 and finished["actual_min"] == 210 and finished["steps"] == 3


# Black box


def test_archived_it_leaves_the_open_projects_for_finished(app: App) -> None:
    project, steps = essay(app)
    app.do("project_archive", id=project)
    assert [p["item"]["id"] for p in app.do("projects")] == []
    [finished] = app.do("projects_finished")
    assert (finished["id"], finished["title"], finished["finished"]) == (project, "Essay", "2026-11-09T09:00")
    assert {status(app, s) for s in steps.values()} == {"dropped"}


def test_unarchived_it_comes_back_with_its_steps_but_not_ones_you_dropped(app: App) -> None:
    project, steps = essay(app)
    app.do("drop", id=steps["Revise"])
    app.do("project_archive", id=project)
    app.do("project_unarchive", id=project)
    assert [p["item"]["id"] for p in app.do("projects")] == [project]
    assert (status(app, steps["Outline"]), status(app, steps["Draft"]), status(app, steps["Revise"])) == (
        "todo", "todo", "dropped",
    )  # fmt: skip
    assert app.do("projects_finished") == []
    assert str(project) not in kv_get(app.conn, ARCHIVED, {})


def test_a_project_ticked_done_is_finished_too_and_can_open_again(app: App) -> None:
    project, _ = essay(app)
    app.do("done", id=project)
    assert [f["id"] for f in app.do("projects_finished")] == [project]
    app.do("project_unarchive", id=project)
    assert [p["item"]["id"] for p in app.do("projects")] == [project]


def test_deleted_it_leaves_finished_and_undo_brings_it_back(app: App) -> None:
    project, steps = essay(app)
    app.do("project_archive", id=project)
    deleted = app.full("project_delete", payload={"id": project}, provisional=False)
    assert app.do("projects_finished") == [] and status(app, project) == "dropped"
    app.do("undo", command_id=deleted.command_id)
    assert [f["id"] for f in app.do("projects_finished")] == [project]


def test_something_that_isnt_a_project_is_refused(app: App) -> None:
    task = app.do("add", title="Buy stamps", duration_min=15)["item"]["id"]
    with pytest.raises(FieldError, match="isn't a project"):
        app.do("project_archive", id=task)
    project, steps = essay(app)
    with pytest.raises(FieldError, match="isn't a project"):
        app.do("project_archive", id=steps["Draft"])  # a step isn't a project of its own
