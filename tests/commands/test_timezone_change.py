"""A new timezone keeps whole-day events on their dates (9 Nov, C68's open list: "changing your timezone shifts
all-day events"). A birthday midnight to midnight in New York was 9pm the evening before to 9pm in Los Angeles; a
timed event stays the moment it was, as a call across timezones should."""

from pathlib import Path

import pytest

from friday.core.time import parse_utc, to_local
from tests.commands.helpers import TZ, App, new_app

LA = "America/Los_Angeles"
PLAIN = dict(when="fixed", color=None, notes="", location=None)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, New York


def move_to(app: App, zone: str) -> int:
    return app.full("settings_set", payload={"key": "time", "value": {"timezone": zone, "horizon_days": 7}},
                    provisional=False).command_id  # fmt: skip


def birthday(app: App) -> int:
    return app.do("add", title="Mira's birthday", start="2026-10-22T00:00", end="2026-10-23T00:00", **PLAIN)["item"][
        "id"
    ]


def stored(app: App, item: int, zone: str) -> tuple[str, str]:
    row = app.conn.execute("SELECT start_utc, end_utc FROM items WHERE id = ?", [item]).fetchone()
    return tuple(to_local(parse_utc(t), zone).strftime("%Y-%m-%dT%H:%M") for t in row)  # type: ignore[return-value]


# Black box: what you see after moving.


def test_a_birthday_stays_on_its_day(app: App) -> None:
    item = birthday(app)
    move_to(app, LA)
    shown = app.do("item", id=item)["item"]
    assert (shown["start"], shown["end"]) == ("2026-10-22T00:00", "2026-10-23T00:00")


def test_a_trip_of_several_days_keeps_its_days(app: App) -> None:
    trip = app.do("add", title="Trip", start="2026-10-23T00:00", end="2026-10-26T00:00", **PLAIN)["item"]["id"]
    move_to(app, "Europe/London")
    assert stored(app, trip, "Europe/London") == ("2026-10-23T00:00", "2026-10-26T00:00")


def test_a_timed_event_stays_the_moment_it_was(app: App) -> None:
    call = app.do("add", title="Call", start="2026-10-22T15:00", end="2026-10-22T16:00", **PLAIN)["item"]["id"]
    move_to(app, LA)
    assert stored(app, call, LA) == ("2026-10-22T12:00", "2026-10-22T13:00")  # 3pm in New York is noon here


def test_undo_puts_the_timezone_and_the_days_back(app: App) -> None:
    item = birthday(app)
    app.do("undo", command_id=move_to(app, LA))
    assert stored(app, item, TZ) == ("2026-10-22T00:00", "2026-10-23T00:00")


def test_moving_there_and_back_leaves_it_where_it_was(app: App) -> None:
    item = birthday(app)
    move_to(app, "Asia/Tokyo")
    move_to(app, TZ)
    assert stored(app, item, TZ) == ("2026-10-22T00:00", "2026-10-23T00:00")


# Glass box: only events at midnight at both ends in the old zone are rewritten; the same zone rewrites nothing.


def test_an_event_from_midnight_to_noon_is_timed(app: App) -> None:
    shift = app.do("add", title="Shift", start="2026-10-22T00:00", end="2026-10-22T12:00", **PLAIN)["item"]["id"]
    move_to(app, LA)
    assert stored(app, shift, LA) == ("2026-10-21T21:00", "2026-10-22T09:00")


def test_saving_the_same_zone_changes_no_event(app: App) -> None:
    birthday(app)
    before = app.table("items")
    move_to(app, TZ)
    assert app.table("items") == before


def test_a_task_with_a_due_time_is_left_alone(app: App) -> None:
    essay = app.do("add", text="essay 2h due thu 5pm")["item"]["id"]
    due = app.table("items")[-1]["due_utc"]
    move_to(app, LA)
    assert next(r["due_utc"] for r in app.table("items") if r["id"] == essay) == due


# The whole system: settings saved through the server, the calendar read back through it.


def test_through_the_server(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path)
    item = birthday(app)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as web:
        saved = web.post("/api/c/settings_set", json={"key": "time", "value": {"timezone": LA, "horizon_days": 7}})
        assert saved.status_code == 200, saved.text
        shown = web.get("/api/q/item", params={"id": item}).json()["item"]
        assert (shown["start"], shown["end"]) == ("2026-10-22T00:00", "2026-10-23T00:00")
