"""Your events, changed in Friday, saved back to Google Calendar (COMBINED.md 69): a change is queued by the command
and sent by the job, the next sync finds nothing new, and a new event lands in the calendar you named."""

from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def lecture() -> FakeGoogle:
    return FakeGoogle({"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]})


def read(app: App, google: FakeGoogle, minutes_later: int = 0) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc + minutes_later, google=google)


def the_lecture(app: App) -> dict:
    return next(i for i in app.table("items") if i["title"].startswith("CS 1110"))


def test_a_change_made_in_friday_is_saved_to_the_calendar_and_not_suggested_back(app: App) -> None:
    google = lecture()
    read(app, google)
    item = the_lecture(app)
    app.do("edit", id=item["id"], title="CS 1110 Lecture (Olin 155)", start="2026-10-20T10:10", end="2026-10-20T11:25")
    assert write_events(app.conn, app.now_utc, google=google) == 1
    saved = google.calendars_by_id["Classes@group"][0]
    assert saved["summary"] == "CS 1110 Lecture (Olin 155)"
    assert saved["start"]["dateTime"].startswith("2026-10-20T10:10")
    read(app, google, minutes_later=60)
    assert app.do("inbox")["suggestions"] == []
    assert [s["status"] for s in app.table("suggestions")] == ["accepted"]  # nothing new read back
    assert the_lecture(app)["title"] == "CS 1110 Lecture (Olin 155)"


def test_deleting_an_event_in_friday_deletes_it_in_the_calendar(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do("drop", id=the_lecture(app)["id"])
    write_events(app.conn, app.now_utc, google=google)
    assert google.calendars_by_id["Classes@group"] == []


def test_a_calendar_you_keep_read_only_is_never_written(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do("calendar_set", id="Classes@group", editable=False)
    app.do("edit", id=the_lecture(app)["id"], title="Renamed here only")
    assert app.table("event_writes") == []
    assert write_events(app.conn, app.now_utc, google=google) == 0


def test_a_new_event_goes_to_the_calendar_you_named_and_follows_it_from_then_on(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do(
        "settings_set",
        key="gcal",
        value={"read": ["Classes"], "trusted": ["Classes"], "new_events_to": "Classes@group"},
    )
    made = app.do("add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00")["item"]
    write_events(app.conn, app.now_utc, google=google)
    titles = [e["summary"] for e in google.calendars_by_id["Classes@group"]]
    assert titles == ["CS 1110 Lecture", "Chess club"]
    read(app, google, minutes_later=60)
    chess = [i for i in app.table("items") if i["title"] == "Chess club" and i["status"] == "todo"]
    assert [i["id"] for i in chess] == [made["id"]]  # read back as the same event, not a second one
    google.calendars_by_id["Classes@group"][1]["summary"] = "Chess club (finals)"
    read(app, google, minutes_later=120)
    assert next(i for i in app.table("items") if i["id"] == made["id"])["title"] == "Chess club (finals)"


def test_undoing_a_change_before_it_is_sent_takes_it_back(app: App) -> None:
    google = lecture()
    read(app, google)
    edit = app.full("edit", payload={"id": the_lecture(app)["id"], "title": "Oops"})
    app.do("undo", command_id=edit.command_id)
    assert write_events(app.conn, app.now_utc, google=google) == 0
    assert google.calendars_by_id["Classes@group"][0]["summary"] == "CS 1110 Lecture"
