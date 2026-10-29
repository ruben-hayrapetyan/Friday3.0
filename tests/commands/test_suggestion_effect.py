"""What accepting a suggested event would do (29 Oct: "when i am looking at whether to accept or decline events, can
you provide an idea of the repercussions of accepting/declining the event?"): the events it clashes with, the work
planned in its time, and the work it makes later. Monday 19 Oct 2026, 9am."""

from pathlib import Path
from typing import Any

import pytest

from friday.commands.suggesting import suggest
from friday.core.items import FieldError
from friday.ingest.ics import Proposed
from friday.planner.service import replan
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def suggested(app: App, fields: dict[str, Any]) -> int:
    app.do("document_add", name="mail.txt", content="an invitation")
    raw = app.table("raw_inputs")[-1]["id"]
    proposals = [Proposed("add", fields, fixed="start" in fields)]
    suggest(app.conn, load_settings(app.conn, 1), app.now_utc, 1, raw, proposals, False, "Mail")
    return app.table("suggestions")[-1]["id"]


def screening(start: str = "2026-10-19T19:00", end: str = "2026-10-19T21:00") -> dict[str, Any]:
    return {"title": "Film screening", "preset": "Event", "start": start, "end": end}


def test_it_names_the_events_it_clashes_with_and_the_work_in_its_time(app: App) -> None:
    app.do("add", title="Chess Club", when="fixed", start="2026-10-19T18:00", end="2026-10-19T20:00")
    app.do("add", title="Essay", due="2026-10-19T23:00", duration_min=600, preset="Assignment")
    replan(app.conn, app.now_utc)
    out = app.do("suggestion_effect", id=suggested(app, screening()))
    assert out["event"] is True
    assert [(c["title"], c["start"], c["end"]) for c in out["clashes"]] == [
        ("Chess Club", "2026-10-19T18:00", "2026-10-19T20:00")
    ]
    planned = [b for b in app.do("plan")["blocks"] if b["start"] < "2026-10-19T21:00" and b["end"] > "2026-10-19T19:00"]
    assert [t["title"] for t in out["takes"]] == [b["title"] for b in planned]


def test_it_says_what_work_would_be_later_for_it(app: App) -> None:
    app.do("add", title="Essay", due="2026-10-19T21:00", duration_min=240, preset="Assignment")  # fits today
    replan(app.conn, app.now_utc)
    assert app.do("status")["late"] == {}
    out = app.do("suggestion_effect", id=suggested(app, screening("2026-10-19T09:30", "2026-10-19T20:30")))  # all day
    (essay,) = out["later"]
    assert essay["title"] == "Essay" and essay["hours"] >= 2 and essay["due"] == "2026-10-19T21:00"


def test_work_due_before_it_starts_is_never_said_to_be_later(app: App) -> None:
    app.do("add", title="Lab report", due="2026-10-19T15:00", duration_min=600, preset="Assignment")
    replan(app.conn, app.now_utc)
    out = app.do("suggestion_effect", id=suggested(app, screening()))
    assert out["later"] == []


def test_an_edited_time_is_the_one_weighed(app: App) -> None:
    app.do("add", title="Chess Club", when="fixed", start="2026-10-19T18:00", end="2026-10-19T20:00")
    sid = suggested(app, screening())
    out = app.do("suggestion_effect", id=sid, start="2026-10-19T21:00", end="2026-10-19T22:00")
    assert out["clashes"] == []


def test_a_task_or_an_answered_suggestion_says_nothing(app: App) -> None:
    sid = suggested(app, {"title": "PS 5", "preset": "Assignment", "due": "2026-10-23T23:59"})
    assert app.do("suggestion_effect", id=sid) == {"event": False, "clashes": [], "takes": [], "later": []}
    app.do("suggestion_reject", id=sid)
    with pytest.raises(FieldError, match="no pending suggestion"):
        app.do("suggestion_effect", id=sid)
