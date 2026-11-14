"""How Friday knows a hidden calendar's things (planner/hidden.py), glass box: hiding none reads nothing; an event is
its calendar's by the latest suggestion accepted for it, whatever kind of calendar (a calendar link too), or by the
calendar it's being saved to; every time of a repeat goes with it; a suggestion is the calendar's when it came from
it, changes one of its events, or is the mailed twin of one of its own; and the plan's notes and skip offers never
name its events."""

import json
from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.planner.assemble import clashes, notices
from friday.planner.build import build_problem
from friday.planner.hidden import NOTHING, event_calendars, hidden_of
from friday.planner.prepare import build_input
from friday.planner.snapshot import take_snapshot
from friday.planner.store import load_settings
from tests.commands.helpers import TZ, App, new_app
from tests.commands.test_hidden_calendars import CALENDARS, EVENTS, hide, show
from tests.sync.test_mac_calendars import mac_event, post

FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:hours-1
SUMMARY:Office hours
DTSTART:20261021T180000Z
DTEND:20261021T190000Z
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    post(app, CALENDARS, [])
    for c in ("friends", "invites"):
        app.do("calendar_set", id=c, mac=True, trusted=False)
    post(app, CALENDARS, EVENTS, minutes_later=1)
    return app


def hidden(app: App):  # noqa: ANN201
    return hidden_of(app.conn, load_settings(app.conn), 1)


def item_id(app: App, title: str) -> int:
    return next(i["id"] for i in app.table("items") if i["title"] == title)


def test_nothing_hidden_reads_nothing(app: App) -> None:
    assert hidden(app) is NOTHING and not hidden(app)
    assert NOTHING.calendar(1) is None and NOTHING.calendar(None) is None


def test_an_event_is_its_calendars_by_the_suggestion_accepted_for_it(app: App) -> None:
    calendars = event_calendars(app.conn, 1)
    assert calendars[item_id(app, "Rocketry meeting")] == "Clubs" and calendars[item_id(app, "Dentist")] == "Home"
    assert all(app.conn.execute("SELECT when_kind FROM items WHERE id = ?", [k]).fetchone()[0] == "fixed"
               for k in calendars)  # fmt: skip
    hide(app)
    found = hidden(app)
    assert found.names == {"Clubs", "Invites"}
    assert set(found.events.values()) == {"Clubs"} and found.calendar(item_id(app, "Rocketry meeting")) == "Clubs"
    assert found.calendar(item_id(app, "Dentist")) is None


def test_a_calendar_links_events_and_suggestions_are_hidden_by_its_name(app: App) -> None:
    app.do("source_add", name="Canvas", url="https://example.edu/feed.ics", trusted=True)
    app.do("source_add", name="Club feed", url="https://example.edu/club.ics", trusted=False)
    sync(app.conn, app.now_utc + 2, fetch=lambda url: FEED)
    hours = item_id(app, "Office hours")
    look = app.do("settings")["calendar_look"]
    app.do("settings_set", key="calendar_look", value=look | {"toolbar": ["Canvas", "Club feed"]})
    assert hidden(app).calendar(hours) == "Canvas"
    shown = {
        f["id"]: f for f in app.do("plan", start="2026-10-21T00:00", end="2026-10-22T00:00", with_hidden=True)["fixed"]
    }
    assert shown[hours]["hidden_calendar"] == "Canvas" and shown[hours]["calendar"] is None  # Show still finds it
    assert hours not in {f["id"] for f in app.do("plan", start="2026-10-21T00:00", end="2026-10-22T00:00")["fixed"]}
    assert "Club feed" not in {s["source"] for s in app.do("inbox")["suggestions"]}


def test_an_event_made_here_is_the_calendar_its_saved_to(app: App) -> None:
    made = app.do("add", title="Rocketry dinner", when="fixed", start="2026-10-23T18:00", end="2026-10-23T19:00")
    made_id = made["item"]["id"]
    app.conn.execute(
        "INSERT INTO event_writes (user_id, item_id, op, calendar_id, queued_utc) VALUES (1, ?, 'save', 'clubs', ?)",
        [made_id, "2026-10-19T13:00Z"],
    )
    hide(app)
    assert hidden(app).calendar(made_id) == "Clubs"
    assert app.do("item", id=made_id)["item"]["hidden_calendar"] == "Clubs"


def test_every_time_of_a_hidden_repeat_goes_with_it(app: App) -> None:
    gym = next(i for i in app.table("items") if i["title"] == "Gym")
    later_times = {"start_utc": "2026-11-04T12:30Z", "end_utc": "2026-11-04T13:30Z", "occurrence_date": "2026-11-04"}
    copy = {k: v for k, v in gym.items() if k != "id"} | later_times
    app.conn.execute(
        f"INSERT INTO items ({', '.join(copy)}) VALUES ({', '.join('?' * len(copy))})", list(copy.values())
    )
    later = app.conn.execute("SELECT max(id) FROM items").fetchone()[0]
    assert later not in event_calendars(app.conn, 1)  # made from the repeat, no suggestion of its own
    hide(app)
    assert hidden(app).calendar(later) == "Clubs"


def suggestion(app: App, source: str, kind: str, command: str, fields: dict, status: str = "pending") -> int:
    found = app.conn.execute("SELECT id FROM sources WHERE kind = ? AND name = ?", [kind, source]).fetchone()
    source_id = found[0] if found else app.conn.execute(
        "INSERT INTO sources (kind, name) VALUES (?, ?)", [kind, source]).lastrowid  # fmt: skip
    raw = app.conn.execute(
        "INSERT INTO raw_inputs (source_id, external_id, received_utc, content_hash, content) VALUES (?, ?, ?, ?, '')",
        [source_id, f"{source}-{fields}", "2026-10-19T13:00Z", str(fields)],
    ).lastrowid
    return app.conn.execute(
        "INSERT INTO suggestions (raw_input_id, command, input, status, created_utc) VALUES (?, ?, ?, ?, ?)",
        [raw, command, json.dumps(fields), status, "2026-10-19T13:00Z"],
    ).lastrowid


def test_a_mailed_invitation_on_a_hidden_calendar_too_and_a_change_to_its_event_are_its(app: App) -> None:
    sync_ = {"title": "Team sync", "preset": "Meeting", "start": "2026-10-21T10:00", "end": "2026-10-21T11:00"}
    mailed = suggestion(app, "me@example.com", "gmail", "add", sync_)
    there = suggestion(app, "Invites", "mac", "add", sync_, status="superseded")  # read after the mail: its twin
    app.conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (1, 'set_aside_twins', ?)", [json.dumps({there: mailed})]
    )
    moved = suggestion(
        app, "me@example.com", "gmail", "edit", {"id": item_id(app, "Rocketry social"), "start": "2026-10-22T19:30"}
    )
    other = suggestion(app, "me@example.com", "gmail", "add", {"title": "Lunch with Sam", "start": "2026-10-23T12:00"})
    hide(app)
    away = hidden(app).suggestions
    assert {mailed, there, moved} <= away and other not in away
    out = app.do("inbox")
    assert {s["id"] for s in out["suggestions"]} & {mailed, moved, there} == set() and other in {
        s["id"] for s in out["suggestions"]
    }
    assert there not in {s["id"] for s in out["set_aside"]}
    show(app)
    assert {mailed, moved} <= {s["id"] for s in app.do("inbox")["suggestions"]}


def test_the_plans_notes_never_name_a_hidden_event(app: App) -> None:
    app.do("add", title="Club call", when="fixed", start="2026-10-22T19:30", end="2026-10-22T20:30")  # over the social
    essay = app.do("add", title="Essay", preset="Assignment", duration_min=60, due="2026-10-23T23:00")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T09:30", end="2026-10-19T10:00")  # locked over the meeting

    def said() -> list[str]:
        problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
        return notices(problem, []) + clashes(problem, TZ)

    assert any("Rocketry social" in n for n in said()) and any("during Rocketry meeting" in n for n in said())
    hide(app)
    assert not any("Rocketry" in n for n in said())
    assert any(
        "during an event on a calendar you hid, so Friday planned it elsewhere: move the lock" in n for n in said()
    )


def test_a_hidden_events_kind_and_name_stay_on_it_for_the_calendar(app: App) -> None:
    app.at("2026-10-19T09:00")
    post(
        app, CALENDARS, [*EVENTS, mac_event("x", "clubs", "Rocketry dinner", "2026-10-24T18:00", "2026-10-24T19:00")], 2
    )
    hide(app)
    dinner = app.do("item", id=item_id(app, "Rocketry dinner"))["item"]
    assert (dinner["calendar"], dinner["hidden_calendar"]) == ("Clubs", "Clubs")
