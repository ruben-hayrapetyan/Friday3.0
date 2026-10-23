"""Calendars and mail shaped like a real student's (found in use, M13–M14): a yearly birthday among weekly lectures,
an assignment read after it was due, a mail thread answered back and forth, and mail proposing a meeting with no
time or homework with no due date. Each comes out as something you can accept as it is."""

from pathlib import Path
from typing import Any

import pytest

from friday.commands.fetching import sync
from friday.sim.fakes import FakeGmail, FakeGoogle, ScriptedClient, event, mail
from tests.commands.helpers import App, new_app

BIRTHDAY = {"id": "bday_20261021", "summary": "Mom's Birthday", "recurringEventId": "bday",
            "start": {"date": "2026-10-21"}, "end": {"date": "2026-10-22"}}  # fmt: skip
LECTURES = [
    event(f"chem_{d}", "CHEM 2090, Lecture", f"2026-10-{d}T12:20", f"2026-10-{d}T13:10", recurringEventId="chem")
    for d in (19, 21, 23)
]
CLUB = [event("club_1", "Robotics", "2026-10-20T19:00", "2026-10-20T20:00", recurringEventId="club")]
RULES = {"bday": "FREQ=YEARLY", "chem": "FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20261211T045959Z"}  # club's unreadable


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="gmail", value={"enabled": True, "keywords": ["due", "meet", "fafsa"]})
    return app


def read_calendars(app: App, calendars: dict[str, list[dict[str, Any]]]) -> None:
    app.do("settings_set", key="gcal", value={"read": list(calendars), "include_all_day": True})
    google = FakeGoogle({f"{n}@group": e for n, e in calendars.items()}, names={f"{n}@group": n for n in calendars},
                        rules=RULES)  # fmt: skip
    sync(app.conn, app.now_utc, google=google)


def answer(*items: dict[str, Any]) -> dict[str, Any]:
    empty = {"due": None, "start": None, "end": None, "area": None, "confidence": 0.9, "quotes": {}}
    return {"is_syllabus": False, "items": [empty | i for i in items]}


def pending(app: App) -> dict[str, dict[str, Any]]:
    return {s["input"]["title"]: s for s in app.do("inbox")["suggestions"]}


def test_a_repeating_events_own_rule_is_shown_and_kept_not_guessed_from_weekdays(app: App) -> None:
    read_calendars(app, {"Personal": [BIRTHDAY, *CLUB], "School": LECTURES})
    found = {r["title"]: r for r in app.do("calendar_repeats")}
    assert found["Mom's Birthday"]["pattern"] == "Yearly, all day"
    assert found["CHEM 2090, Lecture"]["pattern"] == "Every Mon, Wed and Fri until Dec 11, 12:20pm–1:10pm"
    assert found["Robotics"]["pattern"] == "Every Tuesday, 7pm–8pm"  # no rule from Google: its weekdays
    app.do("repeats_import", repeats=[{"batch": found["Mom's Birthday"]["batch"]}])
    birthday = next(s for s in app.do("series_list") if s["title"] == "Mom's Birthday")
    assert birthday["pattern"] == "Yearly, all day" and birthday["external"]
    assert next(r["rrule"] for r in app.table("series")) == "FREQ=YEARLY"


def test_an_assignment_already_due_when_read_isnt_suggested(app: App) -> None:
    canvas = [
        {"id": "a4", "summary": "A4 Partner Matching", "start": {"date": "2026-10-18"}, "end": {"date": "2026-10-19"}},
        {"id": "a5", "summary": "A5 Recursion", "start": {"date": "2026-10-22"}, "end": {"date": "2026-10-23"}},
    ]
    app.do("settings_set", key="gcal", value={"read": ["Canvas"], "include_all_day": True})
    sync(app.conn, app.now_utc - 24 * 60 * 3, google=FakeGoogle({"Canvas@group": []}, names={"Canvas@group": "Canvas"}))
    app.do("calendar_set", id="Canvas@group", kind="Assignment")
    read_calendars(app, {"Canvas": canvas})
    assert set(pending(app)) == {"A5 Recursion"}


def test_mail_says_things_once_per_thread(app: App) -> None:
    advisor = "Ms. Wickham <jfw@school.edu>"
    gmail = FakeGmail([
        mail("m2", "Me <me@gmail.com>", "Re: Financial aid", "<p>Following up: can we meet? FAFSA fixed by Fri.</p>",
             thread="t"),
        mail("m1", advisor, "Financial aid", "<p>Please fix your FAFSA. Happy to meet.</p>", thread="t"),
    ])  # fmt: skip
    client = ScriptedClient({"Following up": answer({"title": "Fix FAFSA", "preset": "Errand"})})
    sync(app.conn, app.now_utc, mail=gmail, client=client)
    assert [c["messages"][0]["content"][0]["text"].splitlines()[0] for c in client.calls] == ["From: Me <me@gmail.com>"]
    log = {m["id"]: m for m in app.do("mail_log")}
    assert sorted(m["status"] for m in log.values()) == ["read", "skipped"]
    assert any("newer message in its thread" in (m["why"] or "") for m in log.values())

    gmail.messages_by_id = {"m3": mail("m3", advisor, "Re: Financial aid", "<p>Sure, meet Thursday?</p>", thread="t")}
    sync(app.conn, app.now_utc + 60, mail=gmail, client=client)
    asked = client.calls[-1]["messages"][0]["content"][0]["text"]
    assert "Friday already has these from earlier in this thread" in asked and "Fix FAFSA" in asked


def test_mail_with_a_meeting_to_arrange_or_homework_without_a_date_can_be_accepted(app: App) -> None:
    gmail = FakeGmail(
        [
            mail(
                "m1",
                "Ms. Wickham <jfw@school.edu>",
                "Aid",
                "<p>Let's meet. Fix your FAFSA. The old form was due Oct 12.</p>",
            )
        ]
    )
    client = ScriptedClient({"Let's meet": answer(
        {"title": "Meet with Ms. Wickham", "preset": "Meeting"},
        {"title": "Fix FAFSA", "preset": "Assignment"},
        {"title": "Old form", "preset": "Errand", "due": "2026-10-12T23:59", "quotes": {"due": "due Oct 12"}},
    )})  # fmt: skip
    sync(app.conn, app.now_utc, mail=gmail, client=client)
    found = pending(app)
    assert set(found) == {"Meet with Ms. Wickham", "Fix FAFSA"}  # the form was due last week
    assert found["Meet with Ms. Wickham"]["input"]["preset"] == "Errand"
    assert found["Fix FAFSA"]["input"] | {} == {"title": "Fix FAFSA", "preset": "Assignment", "firmness": "none"}
    for s in found.values():
        app.do("suggestion_accept", id=s["id"])
    assert {i["title"] for i in app.do("items")} >= {"Meet with Ms. Wickham", "Fix FAFSA"}


def test_including_all_day_events_later_reads_the_ones_already_seen(app: App) -> None:
    google = FakeGoogle({"Personal@group": [BIRTHDAY]}, names={"Personal@group": "Personal"}, rules=RULES)
    app.do("settings_set", key="gcal", value={"read": ["Personal"]})
    sync(app.conn, app.now_utc, google=google)
    assert app.do("calendar_repeats") == []
    app.do("settings_set", key="gcal", value={"read": ["Personal"], "include_all_day": True})
    sync(app.conn, app.now_utc + 1, google=google)
    assert [r["pattern"] for r in app.do("calendar_repeats")] == ["Yearly, all day"]


def test_course_work_lands_under_its_course_tag_once_the_course_is_imported(app: App) -> None:
    read_calendars(app, {"School": LECTURES, "Canvas": [event("hw", "CHEM 2090 Problem Set 4", "2026-10-23T23:59",
                                                                 "2026-10-23T23:59")]})  # fmt: skip
    found = {r["title"]: r for r in app.do("calendar_repeats")}
    assert found["CHEM 2090, Lecture"]["tag"] == "CHEM 2090"
    app.do("repeats_import", repeats=[{"batch": found["CHEM 2090, Lecture"]["batch"], "area": "CHEM 2090"}])
    app.do("suggestion_accept", id=pending(app)["CHEM 2090 Problem Set 4"]["id"])
    assert next(i["area"] for i in app.do("items") if i["title"] == "CHEM 2090 Problem Set 4") == "CHEM 2090"
