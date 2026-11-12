"""Reading sources (commands/fetching.py) at the edges: nothing is read before Friday knows your timezone, Google
failing as a whole shows on its sources, two calendars of one name are numbered, a Canvas feed hands its
assignments to the Canvas API, and a document the AI can't read is marked failed while the others go on."""

import json
from pathlib import Path
from typing import Any

import pytest

from friday.commands import fetching
from friday.commands.fetching import sync
from friday.core.db import connect
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_nothing_is_read_before_friday_knows_your_timezone(tmp_path: Path) -> None:
    conn = connect(tmp_path / "fresh.db")
    assert sync(conn, 0, fetch=lambda url: pytest.fail("read before the timezone was set")) == 0


def test_google_failing_as_a_whole_shows_on_its_sources_and_the_rest_goes_on(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    google = FakeGoogle({"Classes@group": [event("a1", "Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]})
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc, google=google)

    def down(*args: Any, **kwargs: Any) -> int:
        raise ConnectionError("Google is down")

    monkeypatch.setattr(fetching, "read_calendars", down)
    app.do("document_add", name="Note", content="PS5 is due Friday at 5pm.")
    answer = {"is_syllabus": False, "items": [{"title": "PS5", "due": "2026-10-23T17:00", "confidence": 0.9}]}
    sync(app.conn, app.now_utc + 24 * 60, google=google, client=FakeClient(answer))
    (calendar,) = [s for s in app.table("sources") if s["kind"] == "gcal"]
    assert calendar["last_error"].startswith("Google Calendar couldn't be reached") and calendar["failures"] == 1
    assert {r["status"] for r in app.table("raw_inputs") if r["title"] == "Note"} == {"extracted"}


def test_two_calendars_of_one_name_in_one_account_are_numbered(app: App) -> None:
    google = FakeGoogle(
        {"a@group": [], "b@group": []},
        names={"a@group": "Classes", "b@group": "Classes"},
    )
    app.do("settings_set", key="gcal", value={"read": ["a@group", "b@group"], "trusted": []})
    sync(app.conn, app.now_utc, google=google)
    assert sorted(s["name"] for s in app.table("sources") if s["kind"] == "gcal") == ["Classes", "Classes 2"]


CANVAS_FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:event-assignment-77
SUMMARY:Due: Lab report
DTSTART:20261023T035900Z
DTEND:20261023T035900Z
END:VEVENT
BEGIN:VEVENT
UID:event-calendar-event-5
SUMMARY:Review session
DTSTART:20261021T180000Z
DTEND:20261021T190000Z
END:VEVENT
END:VCALENDAR
"""


def test_a_canvas_feed_leaves_its_assignments_to_the_canvas_api_once_it_is_connected(app: App) -> None:
    url = "https://canvas.example.edu/feeds/calendars/user_abc.ics"
    app.do("source_add", name="Canvas feed", url=url, trusted=False)
    sync(app.conn, app.now_utc, fetch=lambda u: CANVAS_FEED)
    assert {r["external_id"] for r in app.table("raw_inputs")} == {"event-assignment-77", "event-calendar-event-5"}
    app.conn.execute(
        "INSERT INTO sources (user_id, kind, name, config) VALUES (1, 'canvas', 'Canvas', ?)",
        [json.dumps({"site": "https://canvas.example.edu"})],
    )
    sync(app.conn, app.now_utc + 24 * 60, fetch=lambda u: CANVAS_FEED)
    by_id = {r["external_id"]: r for r in app.table("raw_inputs")}
    assert by_id["event-assignment-77"]["status"] == "ignored"
    assert by_id["event-calendar-event-5"]["status"] != "ignored"
    (lab,) = [s for s in app.table("suggestions") if json.loads(s["input"]).get("title") == "Lab report"]
    assert lab["status"] == "superseded"


class Unreadable:
    """An AI that can't make sense of the input (not an outage: the next one is tried)."""

    def __init__(self) -> None:
        self.calls = 0

    @property
    def messages(self) -> "Unreadable":
        return self

    def create(self, **request: Any) -> Any:
        self.calls += 1
        raise ValueError("the answer wasn't JSON")


def test_a_document_the_ai_cant_read_is_failed_with_why_and_the_next_is_still_tried(app: App) -> None:
    app.do("document_add", name="One", content="PS5 is due Friday at 5pm.")
    app.do("document_add", name="Two", content="PS6 is due Monday.")
    ai = Unreadable()
    sync(app.conn, app.now_utc, client=ai)
    raw = app.table("raw_inputs")
    assert ai.calls >= 2 and {r["status"] for r in raw} == {"failed"}
    assert all("wasn't JSON" in r["error"] for r in raw)
