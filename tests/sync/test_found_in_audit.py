"""Bugs an audit found in getting data in and out (2026-10-25), each kept fixed: an exam whose prep you'd accepted
staying after the calendar dropped it, a change saved before an event was ticked done deleting it from Google, a new
event sent to a calendar Friday doesn't read copied on every change, a new Mac calendar taking a renamed one's name,
a mail's PDF lost when Google failed it once, and a feed's cancelled week (EXDATE) planned anyway."""

from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.sim.fakes import Attachments, FakeGmail, FakeGoogle, event, mail
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import SINCE, UNTIL, calendar


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def read(app: App, google: FakeGoogle, minutes_later: int = 0) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc + minutes_later, google=google)


def titled(app: App, title: str) -> dict:
    return next(i for i in app.table("items") if i["title"] == title)


def test_an_exam_gone_from_the_calendar_goes_with_the_prep_you_accepted(app: App) -> None:
    google = FakeGoogle({"Classes@group": [event("x1", "MATH Prelim 2", "2026-10-22T19:30", "2026-10-22T21:00")]})
    read(app, google)
    for s in app.do("inbox")["suggestions"]:
        app.do("suggestion_accept", id=s["id"])
    google.calendars_by_id["Classes@group"] = []
    read(app, google, minutes_later=60)
    assert titled(app, "MATH Prelim 2")["status"] == "dropped"
    assert all(i["status"] == "dropped" for i in app.table("items"))  # its prep too


def test_a_change_saved_before_ticking_an_event_done_doesnt_delete_it(app: App) -> None:
    google = FakeGoogle({"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]})
    read(app, google)
    lecture = titled(app, "CS 1110 Lecture")
    app.do("edit", id=lecture["id"], start="2026-10-20T10:10", end="2026-10-20T11:25")
    app.do("done", id=lecture["id"])
    write_events(app.conn, app.now_utc, google=google)
    assert google.calendars_by_id["Classes@group"] != []  # still on the calendar
    assert all(w[0] != "delete" for w in google.writes)


def test_a_new_event_on_a_calendar_friday_doesnt_read_is_changed_and_deleted_there(app: App) -> None:
    google = FakeGoogle({"Classes@group": [], "family@group": []}, names={"family@group": "Family"})
    read(app, google)
    app.do(
        "settings_set",
        key="gcal",
        value={"read": ["Classes"], "trusted": ["Classes"], "new_events_to": "family@group"},
    )
    made = app.do("add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00")["item"]
    write_events(app.conn, app.now_utc, google=google)
    app.do("edit", id=made["id"], start="2026-10-21T19:30", end="2026-10-21T21:30")
    write_events(app.conn, app.now_utc + 1, google=google)
    family = google.calendars_by_id["family@group"]
    assert len(family) == 1 and family[0]["start"]["dateTime"].startswith("2026-10-21T19:30")  # one, moved
    app.do("drop", id=made["id"])
    write_events(app.conn, app.now_utc + 2, google=google)
    assert google.calendars_by_id["family@group"] == []


def test_a_new_mac_calendar_can_take_a_renamed_ones_name(app: App) -> None:
    app.do("mac_sync", calendars=[calendar("A", "Work")], events=[], since=SINCE, until=UNTIL)
    app.do("mac_sync", calendars=[calendar("C", "Work"), calendar("A", "Office")], events=[], since=SINCE, until=UNTIL)
    app.do("mac_sync", calendars=[calendar("C", "Work"), calendar("A", "Office")], events=[], since=SINCE, until=UNTIL)
    names = {s["config"]: s["name"] for s in app.table("sources") if s["kind"] == "mac"}
    assert names == {'{"calendar": "A"}': "Office", '{"calendar": "C"}': "Work"}


def test_a_mails_pdf_is_read_again_when_google_fails_it_once(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    app.do("settings_set", key="gmail", value={"enabled": True, "sender_domains": ["cornell.edu"]})
    gm = FakeGmail([mail("m1", "prof@cornell.edu", "PS5", "<p>See attached, due Friday</p>", pdf=b"%PDF-1.4 x")])
    real_get, calls = Attachments.get, {"n": 0}

    def flaky(self: Attachments, userId: str, messageId: str, id: str) -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("HTTP 503")
        return real_get(self, userId, messageId, id)

    monkeypatch.setattr(Attachments, "get", flaky)
    sync(app.conn, app.now_utc, mail=gm, client=None)
    sync(app.conn, app.now_utc + 60, mail=gm, client=None)
    assert any(r["media_type"] == "application/pdf" for r in app.table("raw_inputs"))


FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//t//t//EN
BEGIN:VEVENT
UID:lec
SUMMARY:CS 1110 Lecture
DTSTART;TZID=America/New_York:20261020T100000
DTEND;TZID=America/New_York:20261020T111500
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=America/New_York:20261027T100000
END:VEVENT
END:VCALENDAR
"""


def test_a_feeds_cancelled_week_isnt_planned(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=28)
    app.conn.execute(
        "INSERT INTO sources (user_id, kind, name, config, trusted) VALUES (1, 'ics', 'Feed', ?, 1)", ['{"url": "x"}']
    )
    sync(app.conn, app.now_utc, fetch=lambda url: FEED)
    app.do("materialize")
    starts = sorted(i["start_utc"] for i in app.table("items") if i["title"] == "CS 1110 Lecture")
    assert starts == ["2026-10-20T14:00Z", "2026-11-03T15:00Z", "2026-11-10T15:00Z"]  # not 27 October
