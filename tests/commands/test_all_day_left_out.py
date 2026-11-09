"""An event made all-day in its calendar while you leave all-day events out (9 Nov, C68's open list: "an all-day
change in Google with all-day events off"). A 9-to-5 offsite made all-day in Google stayed 9 to 5 in Friday, busy;
it goes now, as an event deleted there does, and comes back made timed again. Google keeps it either way."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.commands.suggesting import all_day_left_out
from friday.ingest.ics import Event, Found
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def todo(app: App) -> dict[str, dict]:
    return {i["title"]: i for i in app.table("items") if i["status"] == "todo"}


def offsite_in_google(app: App, all_day_on: bool = False) -> tuple[FakeGoogle, dict[str, Any]]:
    offsite = event("e1", "Team offsite", "2026-10-22T09:00", "2026-10-22T17:00")
    google = FakeGoogle({"Work@group": [offsite]})
    app.do("settings_set", key="gcal", value={"read": ["Work"], "trusted": ["Work"], "include_all_day": all_day_on})
    sync(app.conn, app.now_utc, google=google)
    return google, offsite


def made_all_day(app: App, google: FakeGoogle, e: dict[str, Any], at: str = "2026-10-19T12:00") -> None:
    e["start"], e["end"] = {"date": "2026-10-22"}, {"date": "2026-10-23"}
    sync(app.conn, app.at(at).now_utc, google=google)


# Black box: through the sync, with a stand-in Google.


def test_made_all_day_it_leaves_your_plan(app: App) -> None:
    google, offsite = offsite_in_google(app)
    assert "Team offsite" in todo(app)
    made_all_day(app, google, offsite)
    assert "Team offsite" not in todo(app)


def test_google_keeps_it(app: App) -> None:
    google, offsite = offsite_in_google(app)
    made_all_day(app, google, offsite)
    write_events(app.conn, app.now_utc, google=google)
    assert app.table("event_writes") == [] and google.writes == []
    assert len(google.calendars_by_id["Work@group"]) == 1


def test_made_timed_again_it_comes_back(app: App) -> None:
    google, offsite = offsite_in_google(app)
    made_all_day(app, google, offsite)
    offsite["start"], offsite["end"] = (
        {"dateTime": "2026-10-22T10:00:00-04:00"},
        {"dateTime": "2026-10-22T11:00:00-04:00"},
    )
    sync(app.conn, app.at("2026-10-19T15:00").now_utc, google=google)
    shown = app.do("item", id=todo(app)["Team offsite"]["id"])["item"]
    assert (shown["start"], shown["end"]) == ("2026-10-22T10:00", "2026-10-22T11:00")


def test_with_all_day_events_on_it_becomes_one(app: App) -> None:
    google, offsite = offsite_in_google(app, all_day_on=True)
    made_all_day(app, google, offsite)
    shown = app.do("item", id=todo(app)["Team offsite"]["id"])["item"]
    assert (shown["start"], shown["end"]) == ("2026-10-22T00:00", "2026-10-23T00:00")


def test_one_already_past_is_left_as_it_was(app: App) -> None:
    google, offsite = offsite_in_google(app)
    made_all_day(app, google, offsite, at="2026-10-23T09:00")  # read again the day after
    assert "Team offsite" in todo(app)


# Glass box: all_day_left_out drops only an event it made, only for an all-day reading with all-day events off.

TIMED = Event("Offsite", "2026-10-22T09:00", "2026-10-22T17:00", None, None)
ALL_DAY = Event("Offsite", None, None, "2026-10-22", "2026-10-23")


def found(e: Event, all_day: bool) -> Found:
    f = Found("e1", "hash", e.summary, "{}", [])
    f.event, f.read = e, SimpleNamespace(all_day=all_day)  # type: ignore[assignment] - only this is read
    return f


@pytest.mark.parametrize(("e", "all_day"), [(TIMED, False), (ALL_DAY, True), (TIMED, True)])
def test_nothing_to_drop_unless_left_out(app: App, e: Event, all_day: bool) -> None:
    offsite_in_google(app)
    (raw,) = app.table("raw_inputs")
    assert all_day_left_out(app.conn, raw["id"], found(e, all_day), app.now_utc, None) == []


def test_the_event_it_made_is_dropped(app: App) -> None:
    offsite_in_google(app)
    (raw,) = app.table("raw_inputs")
    (drop,) = all_day_left_out(app.conn, raw["id"], found(ALL_DAY, False), app.now_utc, None)
    assert (drop.command, drop.input["title"], drop.fixed) == ("drop", "Team offsite", True)


def test_an_input_that_made_nothing_drops_nothing(app: App) -> None:
    assert all_day_left_out(app.conn, 999, found(ALL_DAY, False), app.now_utc, None) == []


# The whole system: the Mac's calendars, posted by the Mac app and read by the sync job.


def test_through_the_macs_calendars(app: App) -> None:
    home = {"id": "home", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}
    since, until = "2026-10-18T00:00:00-04:00", "2026-12-14T00:00:00-05:00"
    timed = {"id": "o1", "calendar": "home", "title": "Offsite", "start": "2026-10-22T09:00:00-04:00",
             "end": "2026-10-22T17:00:00-04:00"}  # fmt: skip
    app.do("mac_sync", calendars=[home], events=[timed], since=since, until=until)
    sync(app.conn, app.now_utc)
    assert "Offsite" in todo(app)
    whole = timed | {"start": "2026-10-22", "end": "2026-10-23", "all_day": True}
    app.at("2026-10-19T12:00").do("mac_sync", calendars=[home], events=[whole], since=since, until=until)
    sync(app.conn, app.now_utc)
    assert "Offsite" not in todo(app)
    assert app.do("mac_writes") == []  # nothing sent back to the Mac's calendar
