"""Changes to events sent to Google (commands/eventwrites.py), at the edges: what Events to calendar leaves alone,
a feed's events kept in Friday, and a change that can't be sent kept with why, to be tried again."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from friday.commands import eventwrites
from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


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


def lecture(**extra: dict) -> FakeGoogle:
    return FakeGoogle(
        {"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]}, **extra
    )


def read(app: App, google: FakeGoogle, new_events_to: str | None = None) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc, google=google)
    if new_events_to:
        app.do(
            "settings_set",
            key="gcal",
            value={"read": ["Classes"], "trusted": ["Classes"], "new_events_to": new_events_to},
        )


def the_lecture(app: App) -> dict:
    return next(i for i in app.table("items") if i["title"].startswith("CS 1110"))


def moved(app: App) -> None:
    app.do("edit", id=the_lecture(app)["id"], start="2026-10-20T10:10", end="2026-10-20T11:25")


def test_events_to_calendar_leaves_a_calendars_and_a_feeds_events_where_they_are(app: App) -> None:
    google = lecture()
    read(app, google, new_events_to="Classes@group")
    app.do("source_add", name="Canvas", url="https://example.edu/feed.ics", trusted=True)
    sync(app.conn, app.now_utc, fetch=lambda url: FEED)
    assert len([i for i in app.table("items") if i["when_kind"] == "fixed"]) > 1
    out = app.do("events_to_calendar")
    assert out["message"] == "Every event of yours is on a calendar already" and app.table("event_writes") == []


def test_a_feeds_event_changed_here_is_changed_only_in_friday(app: App) -> None:
    app.do("source_add", name="Canvas", url="https://example.edu/feed.ics", trusted=True)
    sync(app.conn, app.now_utc, fetch=lambda url: FEED)
    feed_event = next(i for i in app.table("items") if i["when_kind"] == "fixed")
    app.do("edit", id=feed_event["id"], title="Lecture, moved")
    assert app.table("event_writes") == []


def test_without_a_google_account_nothing_is_sent_and_the_change_waits(app: App) -> None:
    read(app, lecture())
    moved(app)
    assert write_events(app.conn, app.now_utc) == 0
    (job,) = app.table("event_writes")
    assert (job["done_utc"], job["tries"]) == (None, 0)


def failed(app: App) -> dict:
    (job,) = app.table("event_writes")
    assert job["done_utc"] is None and job["tries"] == 1
    return job


def test_a_change_to_a_calendar_gone_from_your_accounts_is_kept_with_why(app: App) -> None:
    google = lecture()
    read(app, google)
    moved(app)
    app.conn.execute("UPDATE kv SET value = '[]' WHERE key = 'google_calendars'")
    assert write_events(app.conn, app.now_utc, google=google) == 0
    assert "isn't in your Google accounts any more" in failed(app)["error"]


def test_a_change_to_a_calendar_of_an_account_not_connected_is_kept_with_why(app: App) -> None:
    google = lecture()
    read(app, google)
    moved(app)
    (kv,) = [r for r in app.table("kv") if r["key"] == "google_calendars"]
    listed = [c | {"account": "b@example.com"} for c in json.loads(kv["value"])]
    app.conn.execute("UPDATE kv SET value = ? WHERE key = 'google_calendars'", [json.dumps(listed)])
    assert write_events(app.conn, app.now_utc, google={"a@example.com": google}) == 0
    assert "B@example.com isn't connected any more" in failed(app)["error"]  # said as a sentence


def test_an_account_whose_calendar_cant_be_opened_is_said_not_connected(app: App) -> None:
    google = lecture()
    read(app, google)
    moved(app)
    assert write_events(app.conn, app.now_utc, google={"": None}) == 0
    assert "isn't connected any more" in failed(app)["error"]


def test_google_refusing_a_change_keeps_it_to_try_again(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    google = lecture()
    read(app, google)
    moved(app)

    def refuse(*args: object) -> None:
        raise HttpError(SimpleNamespace(status=500, reason="Backend Error"), b"Backend Error")

    monkeypatch.setattr(eventwrites.gcal, "save_event", refuse)
    assert write_events(app.conn, app.now_utc, google=google) == 0
    assert failed(app)["error"]


def test_a_repeat_made_in_google_ends_at_its_local_end_said_in_utc(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do("repeat", id=the_lecture(app)["id"], every="rrule:FREQ=WEEKLY;UNTIL=20261201T120000")
    write_events(app.conn, app.now_utc, google=google)
    (rule,) = next(p for p in google.patches if p.get("recurrence"))["recurrence"]
    assert "UNTIL=20261201T170000Z" in rule  # noon in New York, after the clocks went back


def test_a_new_event_on_a_calendar_friday_doesnt_read_gets_a_source_of_its_own_name(app: App) -> None:
    google = FakeGoogle(
        {"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")], "Other@group": []},
        names={"Other@group": "Classes"},
    )
    read(app, google, new_events_to="Other@group")
    other = next(s for s in app.table("sources") if json.loads(s["config"]).get("calendar") == "Other@group")
    app.do("source_remove", id=other["id"], forget=True)
    # listed before Friday kept each calendar's source name: both are called Classes
    (kv,) = [r for r in app.table("kv") if r["key"] == "google_calendars"]
    listed = [{k: v for k, v in c.items() if k != "source_name"} for c in json.loads(kv["value"])]
    app.conn.execute("UPDATE kv SET value = ? WHERE key = 'google_calendars'", [json.dumps(listed)])
    app.do("add", title="Chess", when="fixed", start="2026-10-21T19:00", end="2026-10-21T20:00")
    assert write_events(app.conn, app.now_utc, google=google) == 1
    made = next(s for s in app.table("sources") if json.loads(s["config"]).get("calendar") == "Other@group")
    assert (made["name"], made["enabled"]) == ("Classes 2", 0)
