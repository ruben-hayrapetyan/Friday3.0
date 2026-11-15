"""A project's or an exam's tag changed takes its steps along (15 Nov, your choice on a client's notes: the project
page and the exam card got a tag, and a step that had the old tag or none takes the new one; one tagged otherwise
keeps its own). One command, so one Undo puts it all back."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def tags(app: App) -> dict[str, str | None]:
    """Every item's tag by its title, events too."""
    found = app.conn.execute("SELECT i.title, a.name FROM items i LEFT JOIN areas a ON a.id = i.area_id")
    return {title: name for title, name in found}


def essay(app: App) -> int:
    """An Essay in ENGL 1170: Outline still ENGL 1170, Draft tagged Rocketry, Revise with no tag."""
    project = app.do("template_apply", template="Essay", title="Essay", hours=4, due="2026-10-26T17:00",
                     area="ENGL 1170")["item"]["id"]  # fmt: skip
    kids = {i["title"]: i["id"] for i in app.do("items") if i["parent_id"] == project}
    app.do("edit", id=kids["Draft"], area="Rocketry")
    app.do("edit", id=kids["Revise"], area=None)
    return project


def test_a_project_s_new_tag_goes_to_the_steps_that_had_its_old_one_or_none(app: App) -> None:
    project = essay(app)
    app.do("edit", id=project, area="HIST 1500")
    got = tags(app)
    want = ("HIST 1500", "HIST 1500", "Rocketry", "HIST 1500")
    assert (got["Essay"], got["Outline"], got["Draft"], got["Revise"]) == want


def test_one_undo_puts_the_project_and_its_steps_back(app: App) -> None:
    project = essay(app)
    changed = app.full("edit", payload={"id": project, "area": "HIST 1500"})
    app.do("undo", command_id=changed.command_id)
    got = tags(app)
    assert (got["Essay"], got["Outline"], got["Draft"], got["Revise"]) == ("ENGL 1170", "ENGL 1170", "Rocketry", None)


def test_a_deleted_step_stays_as_it_was(app: App) -> None:
    project = essay(app)
    outline = next(i["id"] for i in app.do("items") if i["title"] == "Outline")
    app.do("drop", id=outline)
    app.do("edit", id=project, area="HIST 1500")
    assert tags(app)["Outline"] == "ENGL 1170"


def test_an_exam_s_new_tag_goes_to_its_prep_that_matched(app: App) -> None:
    exam = app.do("add", title="PHYS Prelim", preset="Exam", start="2026-10-23T19:30", end="2026-10-23T21:00",
                  area="PHYS 1112")["item"]["id"]  # fmt: skip
    app.do("add", title="Practice prelim", preset="Exam prep", due="2026-10-23T19:30", duration_min=120,
           area="PHYS 1112", before=[exam])  # fmt: skip
    app.do("add", title="Formula sheet", preset="Exam prep", due="2026-10-23T19:30", duration_min=30, before=[exam])
    app.do("add", title="Lab write-up", preset="Exam prep", due="2026-10-23T19:30", duration_min=60,
           area="CHEM 2090", before=[exam])  # fmt: skip
    changed = app.full("edit", payload={"id": exam, "area": "PHYS 2214"})
    got = tags(app)
    assert (got["PHYS Prelim"], got["Practice prelim"], got["Formula sheet"], got["Lab write-up"]) == (
        "PHYS 2214", "PHYS 2214", "PHYS 2214", "CHEM 2090",
    )  # fmt: skip
    app.do("undo", command_id=changed.command_id)
    got = tags(app)
    assert (got["PHYS Prelim"], got["Practice prelim"], got["Formula sheet"]) == ("PHYS 1112", "PHYS 1112", None)


def test_a_task_s_tag_changes_only_its_own(app: App) -> None:
    app.do("add", title="Read chapter 4", duration_min=60, area="HIST 1500")
    app.do("add", title="Read chapter 5", duration_min=60, area="HIST 1500")
    first = next(i["id"] for i in app.do("items") if i["title"] == "Read chapter 4")
    app.do("edit", id=first, area="ENGL 1170")
    assert tags(app)["Read chapter 5"] == "HIST 1500"
