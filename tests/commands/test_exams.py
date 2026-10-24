"""Exams ahead with their prep, for the Projects & exams page."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def prelim(app: App, title: str = "MATH 2940 Prelim 2", day: str = "2026-10-23") -> int:
    exam = app.do("add", title=title, preset="Exam", start=f"{day}T19:30", end=f"{day}T21:00")
    return exam["item"]["id"]


def test_an_exam_lists_the_prep_made_before_it_and_its_courses_exam_prep_due_at_it(app: App) -> None:
    exam = prelim(app)
    guide = app.do("add", title="Study guide", preset="Exam prep", due="2026-10-22T23:59", duration_min=120,
                   before=[exam])["item"]  # fmt: skip
    practice = app.do("add", title="MATH 2940 practice prelim", preset="Exam prep", due="2026-10-23T19:30",
                      duration_min=90)["item"]  # fmt: skip
    app.do("add", title="CS 2800 practice prelim", preset="Exam prep", due="2026-10-23T19:30", duration_min=60)
    app.do("add", title="Laundry", duration_min=60)
    [found] = app.do("exams")
    assert found["item"]["id"] == exam and found["item"]["event_kind"] == "exam"
    assert [p["item"]["id"] for p in found["prep"]] == [guide["id"], practice["id"]]
    assert (found["remaining_min"], found["status"]) == (210, "unplanned")
    app.do("replan")
    planned = app.do("exams")[0]
    assert planned["status"] == "on_track" and planned["planned_finish"] <= "2026-10-23T19:30"


def test_ticked_off_prep_counts_its_length_and_the_exam_is_ready(app: App) -> None:
    exam = prelim(app)
    guide = app.do("add", title="Study guide", preset="Exam prep", due="2026-10-23T19:30", duration_min=120,
                   before=[exam])["item"]  # fmt: skip
    app.do("done", id=guide["id"])
    found = app.do("exams")[0]
    assert (found["status"], found["done_min"], found["remaining_min"]) == ("ready", 120, 0)


def test_an_exam_without_prep_shows_and_other_events_dont(app: App) -> None:
    prelim(app, "CS 2800 Prelim 2", "2026-10-28")
    app.do("add", title="CS 2800 Lecture", preset="Class", start="2026-10-20T10:00", end="2026-10-20T11:00")
    app.do("add", title="Gone exam", preset="Exam", start="2026-10-18T10:00", end="2026-10-18T11:00")
    assert [(e["item"]["title"], e["status"], e["prep"]) for e in app.do("exams")] == [
        ("CS 2800 Prelim 2", "no_prep", [])
    ]


def test_exam_focus_says_when_other_courses_start_waiting(app: App) -> None:
    prelim(app)
    assert app.do("exams")[0]["focus_from"] is None
    app.do("settings_set", key="exam_focus", value={"on": True, "days_before": 2})
    assert app.do("exams")[0]["focus_from"] == "2026-10-21T19:30"
