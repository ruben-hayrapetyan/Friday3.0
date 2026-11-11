"""Services connected by the calendar link they publish (C96): a shift app's link brings your shifts straight in as
fixed work time; a school system's is read as the Canvas feed is, its due dates waiting in your Inbox. The link
remembers which box it was added from, so the gallery shows it there."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.integrations.links import LINKS
from tests.commands.helpers import App, new_app

SHIFTS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Stand-in shift app//EN
BEGIN:VEVENT
UID:shift-1@example.com
DTSTART:20261020T130000Z
DTEND:20261020T210000Z
SUMMARY:Barista at Collegetown Bagels
LOCATION:415 College Ave
END:VEVENT
BEGIN:VEVENT
UID:shift-2@example.com
DTSTART:20261022T220000Z
DTEND:20261023T030000Z
SUMMARY:Closing shift
END:VEVENT
END:VCALENDAR
"""

SCHOOL = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Stand-in school system//EN
BEGIN:VEVENT
UID:assign-7@lms.example.edu
DTSTART:20261023T035900Z
DTEND:20261023T035900Z
SUMMARY:Lab report 3 is due
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def add(app: App, service: str, text: str) -> None:
    app.do("source_add", name=LINKS[service].name, url="https://example.com/feed.ics", service=service)
    sync(app.conn, app.now_utc, fetch=lambda url: text)


@pytest.mark.parametrize("service", [k for k, v in LINKS.items() if v.kind == "Event"])
def test_a_shift_apps_shifts_go_straight_in_as_fixed_work_time(app: App, service: str) -> None:
    add(app, service, SHIFTS)
    shifts = {i["title"]: i for i in app.table("items")}  # events: the `items` query lists to-dos
    assert set(shifts) == {"Barista at Collegetown Bagels", "Closing shift"}
    assert all(i["preset"] == "Event" and i["start_utc"] for i in shifts.values())
    assert app.do("inbox")["suggestions"] == []  # your schedule, not a suggestion


@pytest.mark.parametrize("service", [k for k, v in LINKS.items() if v.kind is None])
def test_a_school_systems_due_dates_wait_in_the_inbox(app: App, service: str) -> None:
    add(app, service, SCHOOL)
    assert app.table("items") == []
    waiting = [s["input"].get("title") for s in app.do("inbox")["suggestions"]]
    assert any("Lab report 3" in (t or "") for t in waiting), waiting


def test_a_link_remembers_its_service_and_a_plain_one_has_none(app: App) -> None:
    add(app, "moodle", SCHOOL)
    app.do("source_add", name="Team calendar", url="https://example.com/team.ics")
    by_name = {s["name"]: s for s in app.do("inbox")["sources"]}
    assert by_name["Moodle"]["service"] == "moodle" and not by_name["Moodle"]["trusted"]
    assert by_name["Team calendar"]["service"] is None


def test_a_service_friday_doesnt_know_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="doesn't know"):
        app.do("source_add", name="X", url="https://example.com/x.ics", service="myspace")


def test_every_link_service_has_a_name_and_says_how_its_events_are_read() -> None:
    assert set(LINKS) == {"blackboard", "moodle", "brightspace", "schoology", "wheniwork", "deputy", "7shifts", "sling"}
    assert all(v.name and (v.kind is None) != v.trusted for v in LINKS.values())


def test_a_link_removed_can_be_added_again_at_a_new_address(app: App) -> None:
    """Found in Chrome, 10 Nov: Remove switches a link off and keeps it, so adding it again took its name and failed."""
    add(app, "wheniwork", SHIFTS)
    first = next(s for s in app.do("inbox")["sources"] if s["service"] == "wheniwork")
    app.do("source_remove", id=first["id"])
    app.do("source_add", name="When I Work", url="https://example.com/new.ics", service="wheniwork")
    again = [s for s in app.do("inbox")["sources"] if s["service"] == "wheniwork"]
    assert len(again) == 1 and again[0]["enabled"] and again[0]["last_error"] is None and again[0]["last_sync"] is None
    assert "new.ics" in next(r["config"] for r in app.table("sources") if r["id"] == again[0]["id"])


def test_a_second_link_with_the_name_of_one_still_read_is_refused_in_words(app: App) -> None:
    add(app, "moodle", SCHOOL)
    with pytest.raises(FieldError, match="already read a link called Moodle"):
        app.do("source_add", name="Moodle", url="https://example.com/other.ics", service="moodle")
