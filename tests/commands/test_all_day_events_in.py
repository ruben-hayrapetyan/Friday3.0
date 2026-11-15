"""All-day events come in for everyone (15 Nov: a client's Thanksgiving and own all-day events never showed, as
`gcal.include_all_day` was off unless you knew to turn it on, and the app never offered it). From Google, the Mac
and calendar links alike, one is a fixed event from the top of its day to the next, never busy, so work is planned
over it; a hidden calendar's stays hidden as its other events do. Migration 039 turns a saved "off" you never chose
on and reads every calendar again."""

import json
import sqlite3
from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.db import MIGRATIONS, connect, one
from friday.planner.service import replan
from friday.sim.fakes import FakeGoogle
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import calendar, post

THANKSGIVING = {"id": "t", "summary": "Thanksgiving", "start": {"date": "2026-11-26"}, "end": {"date": "2026-11-27"}}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-23T09:00")  # the Monday of Thanksgiving week


def whole_days(app: App) -> list[dict]:
    return [i for i in app.table("items") if i["title"] == "Thanksgiving" and i["status"] == "todo"]


def the_one(app: App) -> dict:
    (item,) = whole_days(app)
    assert item["when_kind"] == "fixed" and item["blocks_time"] == 0  # never time taken from planning
    shown = app.do("item", id=item["id"])["item"]
    assert (shown["start"], shown["end"]) == ("2026-11-26T00:00", "2026-11-27T00:00")
    return item


def test_a_google_calendars_all_day_event_comes_in_and_takes_no_time(app: App) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Holidays"], "trusted": ["Holidays"]})  # no all-day setting
    sync(app.conn, app.now_utc, google=FakeGoogle({"Holidays@group": [THANKSGIVING]}))
    the_one(app)


def test_an_all_day_entry_that_says_its_due_is_a_to_do_due_that_day_and_the_rest_are_days(app: App) -> None:
    # 15 Nov: "Strip, unless it says due", as the AI would sort them when there's none to ask
    entries = [THANKSGIVING] + [
        {"id": eid, "summary": title, "start": {"date": "2026-11-25"}, "end": {"date": "2026-11-26"}}
        for eid, title in (("a", "Assignment 4"), ("h", "MATH 1920 HW 7"), ("p", "Problem Set 3"), ("q", "Quiz 2"))
    ]
    app.do("settings_set", key="gcal", value={"read": ["School"], "trusted": ["School"]})
    sync(app.conn, app.now_utc, google=FakeGoogle({"School@group": entries}))
    waiting = {s["input"]["title"]: s["input"] for s in app.do("inbox")["suggestions"]}
    for title in ("Assignment 4", "MATH 1920 HW 7", "Problem Set 3"):
        assert waiting[title] == {"title": title, "preset": "Assignment", "due": "2026-11-25T23:59"}  # a to-do
    assert waiting["Prep: Quiz 2"]["preset"] == "Exam prep"  # an exam as before: a whole day, with its prep
    fixed = {i["title"] for i in app.table("items") if i["when_kind"] == "fixed"}
    assert fixed == {"Thanksgiving", "Quiz 2"}
    the_one(app)


def test_a_mac_calendars_all_day_event_comes_in_and_takes_no_time(app: App) -> None:
    whole = {"id": "t", "calendar": "home", "title": "Thanksgiving", "start": "2026-11-26", "end": "2026-11-27"}
    post(app, [calendar("home", "Home")], [whole | {"all_day": True}])
    the_one(app)


FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:thanksgiving
SUMMARY:Thanksgiving
DTSTART;VALUE=DATE:20261126
DTEND;VALUE=DATE:20261127
END:VEVENT
END:VCALENDAR
"""


def test_a_calendar_links_all_day_event_comes_in_and_takes_no_time(app: App) -> None:
    app.do("source_add", name="Holidays link", url="https://example.com/holidays.ics", trusted=True)
    sync(app.conn, app.now_utc, fetch=lambda url: FEED)
    the_one(app)


def test_switching_them_back_on_reads_a_calendar_link_again(app: App) -> None:
    app.do("settings_set", key="gcal", value={"include_all_day": False})
    app.do("source_add", name="Holidays link", url="https://example.com/holidays.ics", trusted=True)
    sync(app.conn, app.now_utc, fetch=lambda url: FEED)
    assert whole_days(app) == []
    app.do("settings_set", key="gcal", value={"include_all_day": True})
    sync(app.conn, app.now_utc + 1, fetch=lambda url: FEED)  # the link as it was: read again all the same
    the_one(app)


def test_work_is_planned_over_it(app: App) -> None:
    post(app, [calendar("home", "Home")], [{"id": "t", "calendar": "home", "title": "Thanksgiving",
                                            "start": "2026-11-26", "end": "2026-11-27", "all_day": True}])  # fmt: skip
    app.do("add", title="Essay", duration_min=120, release="2026-11-26T00:00", due="2026-11-26T23:00")
    replan(app.conn, app.now_utc)
    plan = app.do("plan", start="2026-11-26T00:00", end="2026-11-27T00:00")
    assert any(b["title"] == "Essay" and b["start"].startswith("2026-11-26") for b in plan["blocks"])


def test_a_hidden_calendars_all_day_event_stays_hidden(app: App) -> None:
    whole = {"id": "t", "calendar": "home", "title": "Thanksgiving", "start": "2026-11-26", "end": "2026-11-27"}
    post(app, [calendar("home", "Home")], [whole | {"all_day": True}])
    look = app.do("settings")["calendar_look"]
    app.do("settings_set", key="calendar_look", value=look | {"toolbar": ["Home"]})
    plan = app.do("plan", start="2026-11-23T00:00", end="2026-11-30T00:00")
    assert "Thanksgiving" not in {f["title"] for f in plan["fixed"]}
    shown = app.do("plan", start="2026-11-23T00:00", end="2026-11-30T00:00", with_hidden=True)
    assert {f["title"]: f["hidden_calendar"] for f in shown["fixed"]}["Thanksgiving"] == "Home"  # for Show


# Migration 039, on a database as it stood before it.


def at_version(path: Path, version: int) -> sqlite3.Connection:
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("0[0-9][0-9]_*.sql") if int(p.name[:3]) <= version):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute(f"PRAGMA user_version = {version}")
    return old


def gcal_write(before: dict | None, after: dict) -> str:
    row = lambda value: {"user_id": 1, "key": "gcal", "value": json.dumps(value)}  # noqa: E731
    change = {"op": "update" if before else "insert", "table": "settings", "key": {"user_id": 1, "key": "gcal"},
              "before": row(before) if before else None, "after": row(after)}  # fmt: skip
    return json.dumps([change])


def migrated(tmp_path: Path, saved: dict | None, logged: list[tuple[dict | None, dict]] = ()) -> sqlite3.Connection:  # type: ignore[assignment]
    """A database at 38 with a Google calendar read, an all-day event it brought that made nothing, an event you
    accepted, `gcal` saved as given and its writes logged."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    old = at_version(tmp_path / "old.db", 38)
    if saved is not None:
        old.execute("INSERT INTO settings (key, value, version, updated_utc) VALUES ('gcal', ?, 1, 'x')",
                    [json.dumps(saved)])  # fmt: skip
    old.execute("INSERT INTO sources (id, kind, name, config) VALUES (1, 'gcal', 'Home', '{}')")
    for n, ext in ((1, "thanksgiving"), (2, "dentist")):
        old.execute("INSERT INTO raw_inputs (id, source_id, external_id, received_utc, content_hash, content) "
                    "VALUES (?, 1, ?, 'x', 'hash', '{}')", [n, ext])  # fmt: skip
    old.execute("INSERT INTO suggestions (raw_input_id, status, command, input, created_utc) "
                "VALUES (2, 'accepted', 'add', '{}', 'x')")  # fmt: skip
    for before, after in logged:
        old.execute("INSERT INTO command_log (at_utc, actor, command, input, result, undo) "
                    "VALUES ('x', 'you', 'settings_set', '{}', '{}', ?)", [gcal_write(before, after)])  # fmt: skip
    old.close()
    return connect(tmp_path / "old.db")


OFF = {"read": ["primary"], "trusted": [], "include_all_day": False, "publish": False}


def all_day(conn: sqlite3.Connection) -> bool | None:
    found = one(conn, "SELECT value FROM settings WHERE key = 'gcal'")
    return json.loads(found["value"])["include_all_day"] if found else None


def read_again(conn: sqlite3.Connection) -> bool:
    asked = one(conn, "SELECT 1 FROM kv WHERE key = 'sync_now'") is not None
    hashes = {r[0]: r[1] for r in conn.execute("SELECT external_id, content_hash FROM raw_inputs")}
    assert hashes["dentist"] == "hash"  # what you answered stays as it was
    return asked and hashes["thanksgiving"] == ""


def test_migration_39_turns_on_an_off_you_never_chose_and_reads_the_calendars_again(tmp_path: Path) -> None:
    conn = migrated(tmp_path, OFF, logged=[(None, OFF), (OFF, OFF | {"publish": True})])  # saved whole, off as it was
    assert all_day(conn) is True
    assert read_again(conn)


def test_migration_39_keeps_an_off_you_chose(tmp_path: Path) -> None:
    on = OFF | {"include_all_day": True}
    conn = migrated(tmp_path, OFF, logged=[(None, on), (on, OFF)])  # turned on, then off again
    assert all_day(conn) is False
    assert not read_again(conn)


def test_migration_39_reads_again_for_the_new_default_when_nothing_is_saved(tmp_path: Path) -> None:
    conn = migrated(tmp_path, None)
    assert all_day(conn) is None  # the default, on now
    assert read_again(conn)
