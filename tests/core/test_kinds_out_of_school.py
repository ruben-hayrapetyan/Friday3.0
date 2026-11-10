"""Kinds that fit people who aren't in school (C97): a dated to-do whose title says nothing more is a Task (30
minutes, one sitting), not a 2-hour Assignment; schoolwork only when the title says so, and, out of school, never.
Found testing Todoist: "Book dentist", "Buy groceries", "Fix login bug" were all 2-hour Assignments."""

from pathlib import Path

import pytest

from friday.core.guess import fallback_kind
from friday.core.presets import DEFAULT_PRESETS, SCHOOL_KINDS, in_use
from tests.commands.helpers import new_app

KINDS = set(DEFAULT_PRESETS)


# Glass box


@pytest.mark.parametrize(("title", "dated", "school", "kind"), [
    ("Book dentist", True, True, "Task"),
    ("Buy groceries", False, True, "Errand"),
    ("CS 2110 A5", True, True, "Assignment"),  # a course code: schoolwork, for a student
    ("CS 2110 A5", True, False, "Task"),  # out of school, never
])  # fmt: skip
def test_the_fallback_is_a_task_unless_the_title_says_school(title: str, dated: bool, school: bool, kind: str) -> None:
    assert fallback_kind(title, dated, in_use(DEFAULT_PRESETS, school), school) == kind


def test_with_task_deleted_the_old_fallback_stands() -> None:
    assert fallback_kind("Book dentist", True, KINDS - {"Task"}) == "Assignment"


def test_out_of_school_the_school_kinds_are_left_out_and_the_rest_kept() -> None:
    assert set(in_use(DEFAULT_PRESETS, False)) == KINDS - SCHOOL_KINDS
    assert in_use(DEFAULT_PRESETS, True) is DEFAULT_PRESETS
    assert {"Task", "Work task", "Errand", "Meeting", "Event"} <= set(in_use(DEFAULT_PRESETS, False))


def test_a_task_is_half_an_hour_in_one_go_and_a_work_task_an_hour_in_sittings() -> None:
    task, work = DEFAULT_PRESETS["Task"], DEFAULT_PRESETS["Work task"]
    assert (task.duration_units, task.shape, task.firmness) == (2, "one_sitting", "hard")
    assert (work.duration_units, work.shape, work.firmness) == (4, "split", "hard")


# Black box: what you type


@pytest.mark.parametrize(("line", "kind", "minutes"), [
    ("Book dentist due fri", "Task", 30),
    ("Call the landlord due thu", "Task", 30),
    ("Essay draft due fri", "Assignment", 120),  # the title says school
    ("MATH 2940 PS 7 due fri", "Assignment", 120),
    ("Study guide for prelim 2 due fri", "Exam prep", 180),
])  # fmt: skip
def test_what_you_type_is_schoolwork_only_when_it_says_so(tmp_path: Path, line: str, kind: str, minutes: int) -> None:
    item = new_app(tmp_path).do("add", text=line)["item"]
    assert (item["preset"], item["duration_min"]) == (kind, minutes)


@pytest.mark.parametrize("line", ["MATH 2940 PS 7 due fri", "Essay draft due fri", "Read chapter 4 due fri"])
def test_out_of_school_nothing_is_schoolwork(tmp_path: Path, line: str) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="school", value=False)
    item = app.do("add", text=line)["item"]
    assert item["preset"] not in SCHOOL_KINDS, item["preset"]


def test_fields_without_a_kind_follow_the_same_rule(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert app.do("add", title="Renew passport", due="2026-10-23T17:00")["item"]["preset"] == "Task"
    assert app.do("add", title="Renew passport")["item"]["preset"] == "Errand"


def test_the_migration_gives_kinds_you_saved_task_and_work_task_once(tmp_path: Path) -> None:
    from friday.core.db import MIGRATIONS

    app = new_app(tmp_path)
    mine = {k: v.model_dump(exclude_none=True) for k, v in DEFAULT_PRESETS.items() if k not in ("Task", "Work task")}
    app.do("settings_set", key="presets", value=mine | {"Lab": mine["Assignment"]})  # kinds of your own, saved
    app.conn.executescript((MIGRATIONS / "031_task_kinds.sql").read_text())
    kinds = app.do("settings")["presets"]
    assert {"Task", "Work task", "Lab"} <= set(kinds)
    assert kinds["Task"]["duration_units"] == 2 and kinds["Work task"]["shape"] == "split"
    app.do("settings_set", key="presets", value={k: v for k, v in kinds.items() if k != "Task"})  # you delete Task
    assert "Task" not in app.do("settings")["presets"]  # and it stays gone: the migration ran once, at its version
