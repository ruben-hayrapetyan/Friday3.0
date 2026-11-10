"""Deleting a repeat from a time on ("this and later") undone after it reached the calendar (10 Nov, C68's open list:
the undo was refused, "event_writes changed since"). Each time comes back on its calendar as it was before: Friday
saves every time of a repeat made here as an event of its own. Monday 2026-10-19."""

from pathlib import Path

import pytest

from friday.commands.eventwrites import sent_delete, write_events
from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle
from tests.commands.helpers import App, new_app
from tests.sync.test_delete_repeat import birthday_on_the_mac
from tests.sync.test_mac_calendars import every_time


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def gym_on_google(app: App) -> tuple[FakeGoogle, int]:
    google = FakeGoogle({"Classes@group": []})
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"],
                                              "new_events_to": "Classes@group"})  # fmt: skip
    sync(app.conn, app.now_utc, google=google)
    series = app.do("add", title="Gym", when="fixed", start="2026-10-20T07:30", end="2026-10-20T09:00",
                    every="week")["series_id"]  # fmt: skip
    write_events(app.conn, app.now_utc, google=google)
    return google, series


def gyms(app: App) -> list[dict]:
    return [r for r in app.table("items") if r["title"] == "Gym" and r["status"] == "todo"]


# Black box: through the commands, the writes job and a stand-in Google.


def test_undone_after_it_went_every_time_comes_back(app: App) -> None:
    google, series = gym_on_google(app)
    had = len(google.calendars_by_id["Classes@group"])
    deleted = app.full("series_delete", payload={"id": series}, provisional=False).command_id
    write_events(app.conn, app.now_utc, google=google)
    assert google.calendars_by_id["Classes@group"] == []
    app.do("undo", command_id=deleted)
    write_events(app.conn, app.now_utc, google=google)
    assert len(google.calendars_by_id["Classes@group"]) == had and len(gyms(app)) == had


def test_the_next_read_of_the_calendar_finds_them_as_yours(app: App) -> None:
    google, series = gym_on_google(app)
    deleted = app.full("series_delete", payload={"id": series}, provisional=False).command_id
    write_events(app.conn, app.now_utc, google=google)
    app.do("undo", command_id=deleted)
    write_events(app.conn, app.now_utc, google=google)
    before = len(gyms(app))
    sync(app.conn, app.at("2026-10-19T12:00").now_utc, google=google)
    assert len(gyms(app)) == before and app.do("inbox")["suggestions"] == []


def test_undone_before_it_went_nothing_is_sent(app: App) -> None:
    google, series = gym_on_google(app)
    had = len(google.calendars_by_id["Classes@group"])
    deleted = app.full("series_delete", payload={"id": series}, provisional=False).command_id
    app.do("undo", command_id=deleted)
    write_events(app.conn, app.now_utc, google=google)
    assert len(google.calendars_by_id["Classes@group"]) == had
    assert [w for w in app.table("event_writes") if w["op"] in ("delete_from", "save") and w["done_utc"] is None] == []


# Glass box: which times the calendar no longer has.


def test_a_later_time_is_gone_once_an_earlier_one_went_with_this_and_later(app: App) -> None:
    google, series = gym_on_google(app)
    first, second = sorted(gyms(app), key=lambda r: r["occurrence_date"])[:2]
    assert not sent_delete(app.conn, second["id"], 1)
    app.do("series_delete", id=series)
    assert not sent_delete(app.conn, second["id"], 1)  # queued, not sent
    write_events(app.conn, app.now_utc, google=google)
    assert sent_delete(app.conn, first["id"], 1) and sent_delete(app.conn, second["id"], 1)


# The whole system, the Mac's way: the Mac app deletes, then makes each time again.


def test_on_the_macs_calendar_each_time_is_made_again(app: App) -> None:
    deleted = app.full("series_delete", payload={"id": birthday_on_the_mac(app)}, provisional=False).command_id
    (job,) = app.do("mac_writes")
    app.do("mac_written", id=job["id"], ok=True)
    app.do("undo", command_id=deleted)
    jobs = app.do("mac_writes")
    assert jobs and {j["op"] for j in jobs} == {"create"} and all(j["calendar"] == "gmail-cal" for j in jobs)
    assert len(jobs) == len(every_time(app, "Remy's Birthday"))
