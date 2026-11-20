"""Work that's pointless once late, archived when its due passes (20 Nov, a user's notes: an exam's "brain dump study"
still "2h late" after the exam, "although the deadline was hard (hourglass icon → no point doing it after the exam is
over, right?)"; you: "pointless tasks (a) linger after their due date and also (b) that subtasks of exams/projects
don't clear"; your answer: "Archive it, say so", H232). Whole system, a scratch Friday, Monday 19 October 2026."""

from pathlib import Path
from typing import Any

import pytest

from friday.commands.pointless import archive_pointless
from friday.server.jobs import run_due
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-10-19T09:00")


def status(app: App, item: int) -> str:
    return app.do("item", id=item)["item"]["status"]


def noted(app: App) -> list[tuple[str, str]]:
    return [(a["title"], a["why"]) for a in app.do("inbox")["archived"]]


def exam_with_prep(app: App) -> tuple[int, int]:
    exam = app.do("add", title="CHEM 2090 Prelim 3", preset="Exam", start="2026-10-19T19:00", end="2026-10-19T20:30")
    prep = app.do("add", title="brain dump study", preset="Exam prep", due="2026-10-19T19:00", duration_min=120,
                  before=[exam["item"]["id"]])  # fmt: skip
    return exam["item"]["id"], prep["item"]["id"]


def test_the_notes_exam_prep_is_archived_once_its_exam_is_over_and_the_inbox_says_so(app: App) -> None:
    _, prep = exam_with_prep(app)
    assert archive_pointless(app.conn, app.now_utc) == 0  # before its exam: nothing
    assert status(app, prep) == "todo" and noted(app) == []
    app.at("2026-10-19T21:00")  # the exam is over, the prep not done
    assert archive_pointless(app.conn, app.now_utc) == 1
    assert status(app, prep) == "dropped"
    assert noted(app) == [("brain dump study", "Its exam is over")]
    assert archive_pointless(app.conn, app.now_utc) == 0  # once


def test_a_projects_step_marked_pointless_after_its_due_is_archived_and_the_rest_stays(app: App) -> None:
    project = app.do("add", title="LING Final Essay", preset="Project", due="2026-12-14T17:00", duration_min=600)
    pid = project["item"]["id"]
    quiz = app.do("add", title="Reading response 4", parent_id=pid, due="2026-10-19T17:00", duration_min=30)["item"][
        "id"
    ]
    app.do("edit", id=quiz, expires=True)  # After it's due: Pointless
    thesis = app.do("add", title="Preliminary Thesis", parent_id=pid, due="2026-10-19T17:00", duration_min=60)
    app.at("2026-10-20T09:00")
    assert archive_pointless(app.conn, app.now_utc) == 1
    assert status(app, quiz) == "dropped"
    assert status(app, thesis["item"]["id"]) == "todo"  # late, still worth doing: stays, asked about as late work
    assert status(app, pid) == "todo"
    assert noted(app) == [("Reading response 4", "Its due passed, and it's pointless after")]


def test_exam_prep_you_said_is_still_worth_doing_is_kept(app: App) -> None:
    _, prep = exam_with_prep(app)
    app.do("edit", id=prep, expires=False)  # After it's due: Still worth doing
    app.at("2026-10-20T09:00")
    assert archive_pointless(app.conn, app.now_utc) == 0
    assert status(app, prep) == "todo"


def test_bring_back_opens_it_again_as_still_worth_doing_and_it_isnt_archived_again(app: App) -> None:
    _, prep = exam_with_prep(app)
    app.at("2026-10-20T09:00")
    archive_pointless(app.conn, app.now_utc)
    out = app.do("archived_restore", id=prep)
    assert out["message"] == "Brought back brain dump study, still worth doing"
    item = app.do("item", id=prep)["item"]
    assert (item["status"], item["expires"]) == ("todo", False)
    assert noted(app) == []
    assert archive_pointless(app.conn, app.now_utc) == 0 and status(app, prep) == "todo"


def test_ok_lets_the_note_go_and_the_work_stays_archived(app: App) -> None:
    _, prep = exam_with_prep(app)
    app.at("2026-10-20T09:00")
    archive_pointless(app.conn, app.now_utc)
    app.do("archived_ok", id=prep)
    assert noted(app) == [] and status(app, prep) == "dropped"


def test_the_note_goes_after_two_weeks(app: App) -> None:
    exam_with_prep(app)
    app.at("2026-10-20T09:00")
    archive_pointless(app.conn, app.now_utc)
    app.at("2026-11-02T09:00")
    assert len(noted(app)) == 1
    app.at("2026-11-04T09:00")
    assert noted(app) == []


class Recorder:
    def __init__(self) -> None:
        self.events: list[str] = []

    def publish(self, event: str, data: Any = None) -> None:
        self.events.append(event)


def test_the_background_jobs_archive_it_within_a_minute_and_tell_the_app(app: App, tmp_path: Path) -> None:
    _, prep = exam_with_prep(app)
    app.at("2026-10-19T21:00")
    hub = Recorder()
    ran = run_due(app.conn, app.now_utc, hub, None, tmp_path / "backups")  # type: ignore[arg-type]
    assert "pointless" in ran
    assert status(app, prep) == "dropped"
    assert "items.changed" in hub.events
