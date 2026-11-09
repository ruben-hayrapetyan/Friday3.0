"""An event deleted, and the delete sent to its calendar, comes back there when you undo or open it again (9 Nov,
C68's open list: "an event deleted from Google can't be undone or reopened onto Google"). Undo was refused
("event_writes changed since"); now the event is made there again as a new one, as Friday has it."""

from pathlib import Path

import pytest

from friday.commands.eventwrites import sent_delete, write_events
from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def dentist(app: App) -> tuple[FakeGoogle, int]:
    google = FakeGoogle({"Work@group": [event("e1", "Dentist", "2026-10-22T09:00", "2026-10-22T10:00")]})
    app.do("settings_set", key="gcal", value={"read": ["Work"], "trusted": ["Work"]})
    sync(app.conn, app.now_utc, google=google)
    return google, next(r["id"] for r in app.table("items") if r["title"] == "Dentist")


def in_google(google: FakeGoogle) -> list[str]:
    return [e["summary"] for e in google.calendars_by_id["Work@group"]]


def dropped_and_sent(app: App) -> tuple[FakeGoogle, int, int]:
    google, item = dentist(app)
    command = app.full("drop", payload={"id": item}, provisional=False).command_id
    write_events(app.conn, app.now_utc, google=google)
    assert in_google(google) == []
    return google, item, command


# Black box: through the commands and the job that sends writes, with a stand-in Google.


def test_undo_after_the_delete_went_puts_it_back(app: App) -> None:
    google, item, dropped = dropped_and_sent(app)
    app.do("undo", command_id=dropped)
    assert app.do("item", id=item)["item"]["status"] == "todo"
    write_events(app.conn, app.now_utc, google=google)
    (back,) = google.calendars_by_id["Work@group"]
    assert back["summary"] == "Dentist" and back["start"]["dateTime"].startswith("2026-10-22T09:00")


def test_opening_it_again_puts_it_back(app: App) -> None:
    google, item, _ = dropped_and_sent(app)
    app.do("reopen", id=item)
    write_events(app.conn, app.now_utc, google=google)
    assert in_google(google) == ["Dentist"]


def test_the_next_read_of_the_calendar_finds_it_as_yours(app: App) -> None:
    google, item, dropped = dropped_and_sent(app)
    app.do("undo", command_id=dropped)
    write_events(app.conn, app.now_utc, google=google)
    sync(app.conn, app.at("2026-10-19T12:00").now_utc, google=google)
    assert [(r["id"], r["status"]) for r in app.table("items") if r["title"] == "Dentist"] == [(item, "todo")]
    assert app.do("inbox")["suggestions"] == []
    app.do("edit", id=item, title="Dentist (moved)")  # and a change here goes to the new one
    write_events(app.conn, app.now_utc, google=google)
    assert in_google(google) == ["Dentist (moved)"]


def test_undo_before_the_delete_went_takes_the_delete_back(app: App) -> None:
    google, item = dentist(app)
    dropped = app.full("drop", payload={"id": item}, provisional=False).command_id
    app.do("undo", command_id=dropped)
    assert app.table("event_writes") == []
    write_events(app.conn, app.now_utc, google=google)
    assert in_google(google) == ["Dentist"] and google.writes == []


# Glass box: sent_delete reads the event's last write; put_back queues only for an open event gone from its calendar.


def test_sent_delete_is_the_last_write(app: App) -> None:
    google, item = dentist(app)
    assert not sent_delete(app.conn, item, 1)
    app.do("drop", id=item)
    assert not sent_delete(app.conn, item, 1)  # queued, not sent
    write_events(app.conn, app.now_utc, google=google)
    assert sent_delete(app.conn, item, 1)


def test_reopening_an_event_still_on_its_calendar_sends_nothing(app: App) -> None:
    google, item = dentist(app)
    app.do("done", id=item)
    app.do("reopen", id=item)
    assert app.table("event_writes") == []


def test_reopening_a_task_sends_nothing(app: App) -> None:
    essay = app.do("add", text="essay 2h due fri")["item"]["id"]
    app.do("drop", id=essay)
    app.do("reopen", id=essay)
    assert app.table("event_writes") == []


def test_put_back_queues_once(app: App) -> None:
    google, item, _ = dropped_and_sent(app)
    app.do("reopen", id=item)
    app.do("drop", id=item)
    app.do("reopen", id=item)  # its last write is the save, not yet sent: nothing more
    saves = [w for w in app.table("event_writes") if w["op"] == "save"]
    assert [(w["calendar_id"], w["done_utc"]) for w in saves] == [("Work@group", None)]


# The whole system: the Mac's calendars, where the Mac app makes the changes (`mac_writes`, `mac_written`).


def test_through_the_macs_calendars(app: App) -> None:
    home = {"id": "home", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#3a5a8c", "writable": True}
    since, until = "2026-10-18T00:00:00-04:00", "2026-12-14T00:00:00-05:00"
    visit = {"id": "v1", "calendar": "home", "title": "Vet", "start": "2026-10-22T09:00:00-04:00",
             "end": "2026-10-22T10:00:00-04:00"}  # fmt: skip
    app.do("mac_sync", calendars=[home], events=[visit], since=since, until=until)
    sync(app.conn, app.now_utc)
    item = next(r["id"] for r in app.table("items") if r["title"] == "Vet")
    dropped = app.full("drop", payload={"id": item}, provisional=False).command_id
    (job,) = app.do("mac_writes")
    assert job["op"] == "delete"
    app.do("mac_written", id=job["id"], ok=True)
    app.do("undo", command_id=dropped)
    (again,) = app.do("mac_writes")
    assert (again["op"], again["calendar"], again["title"]) == ("create", "home", "Vet")
    assert (again["start"], again["end"]) == ("2026-10-22T13:00:00Z", "2026-10-22T14:00:00Z")  # 9 to 10am
