"""Canvas by its API (C107), glass box against its stand-in: your school's Canvas as its address, what in the planner
has a due date and isn't submitted or ticked (assignments, quizzes, graded discussions; not calendar events or
undated items), with its course and points, pages followed by the Link header; done here ticks Canvas's own To Do
(a new override, then the same one), opened again unticks it. And the handover from the Canvas calendar feed: once
the API is connected, an assignment the feed brought stays the same to-do, now kept in step by the API, the feed
stops bringing assignments without anything being dropped, and keeps bringing its events."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync as read_feeds
from friday.integrations import canvas, sync
from friday.integrations.base import ConnectorError
from tests.commands.helpers import App, new_app
from tests.integrations.contract import World
from tests.integrations.fake_canvas import HARNESS, SITE, FakeCanvas


def connector(fake: FakeCanvas) -> canvas.Canvas:
    return canvas.Canvas(HARNESS.token, HARNESS.fields, fake.transport)


@pytest.mark.parametrize(("given", "site"), [
    ("canvas.cornell.edu", "https://canvas.cornell.edu"), ("https://Canvas.Cornell.edu/courses/301", "https://canvas.cornell.edu"),
    ("school.instructure.com", "https://school.instructure.com"),
])  # fmt: skip
def test_your_schools_canvas_becomes_its_address(given: str, site: str) -> None:
    assert canvas.site_of(given) == site


@pytest.mark.parametrize("given", ["", "canvas", "not a site"])
def test_an_address_that_isnt_one_is_refused_in_words(given: str) -> None:
    with pytest.raises(ConnectorError, match="canvas.yourschool.edu"):
        canvas.site_of(given)


def test_whats_due_and_not_yet_handed_in() -> None:
    fake = FakeCanvas(HARNESS.token)
    fake.add("Problem set 5", "2026-10-22", points=20)
    fake.add("Prelim 2", "2026-10-29T19:30", kind="quiz", course="CS 2110", points=None)
    fake.add("Reading response", "2026-10-23", kind="discussion_topic", course="ENGL 1105", points=5)
    fake.add("Office hours", "2026-10-21T15:00", kind="calendar_event")
    fake.add("Undated reading", None)
    handed_in = fake.add("Lab 4", "2026-10-20")
    fake.items[handed_in]["submissions"]["submitted"] = True
    ticked = fake.add("Lab 5", "2026-10-21")
    fake.mark(ticked, True)
    excused = fake.add("Lab 6", "2026-10-21")
    fake.items[excused]["submissions"]["excused"] = True
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Problem set 5", "Prelim 2", "Reading response"}
    ps5 = found["Problem set 5"]
    assert (ps5.due, ps5.notes) == ("2026-10-23T03:59:00Z", "In Canvas: CS 2110 · 20 points")  # 11:59pm, in UTC
    assert ps5.url == f"https://{SITE}/courses/301/assignments/51001"
    assert found["Prelim 2"].notes == "In Canvas: CS 2110"


def test_every_page_is_followed_by_the_link_header() -> None:
    fake = FakeCanvas(HARNESS.token, page_size=7)
    for n in range(30):
        fake.add(f"Homework {n}", "2026-11-02")
    assert len(connector(fake).read()) == 30


def test_done_ticks_canvass_to_do_and_reopen_unticks_the_same_one() -> None:
    fake = FakeCanvas(HARNESS.token)
    key = fake.add("Problem set 5", "2026-10-22")
    connector(fake).write(key, "done")
    assert fake.items[key]["planner_override"]["marked_complete"] is True
    connector(fake).write(key, "reopen")
    assert fake.items[key]["planner_override"]["marked_complete"] is False
    assert fake.writes() == ["POST /planner/overrides", "PUT /planner/overrides/1"]  # one override, not two


FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Instructure//Canvas Calendar//EN
BEGIN:VEVENT
UID:event-assignment-951001
DTSTART:20261023T035900Z
DTEND:20261023T035900Z
SUMMARY:Problem set 5 [CS 2110]
URL:https://canvas.cornell.edu/courses/301/assignments/951001
END:VEVENT
BEGIN:VEVENT
UID:event-calendar-event-77
DTSTART:20261021T190000Z
DTEND:20261021T200000Z
SUMMARY:Review session [CS 2110]
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    fake = FakeCanvas(HARNESS.token)
    monkeypatch.setitem(sync.TRANSPORTS, "canvas", fake.transport)
    return World(HARNESS, new_app(tmp_path), fake)


def accept_all(app: App) -> None:
    for s in app.table("suggestions"):
        if s["status"] == "pending":
            app.do("suggestion_accept", id=s["id"])


def test_the_api_takes_over_the_feeds_assignments_and_the_feed_keeps_its_events(world: World) -> None:
    app = world.app
    app.do("source_add", name="Canvas", url=f"https://{SITE}/feeds/calendars/user_abc123.ics")
    read_feeds(app.conn, app.now_utc, fetch=lambda url: FEED)
    accept_all(app)
    before = {i["title"]: i["id"] for i in app.table("items")}
    assert any("Problem set 5" in t for t in before), before

    # the API's planner has the same assignment (as a quiz would: by its assignment id)
    key = world.fake.add("Problem set 5", "2026-10-23T17:00", assignment=951001, kind="quiz")
    world.connect()
    world.sync()
    read_feeds(app.conn, app.now_utc, fetch=lambda url: FEED)
    read_feeds(app.conn, app.now_utc, fetch=lambda url: FEED)

    items = [i for i in app.table("items") if "Problem set 5" in i["title"]]
    assert len(items) == 1, f"the assignment came in twice: {items}"
    (ps5,) = items
    assert ps5["id"] in before.values(), "a new to-do, not the same one"
    assert ps5["title"] == "Problem set 5", "not kept in step by the API"
    assert ps5["status"] == "todo" and ps5["due_utc"] is not None
    pending = [s for s in app.table("suggestions") if s["status"] == "pending"]
    assert [s["command"] for s in pending if s["command"] == "drop"] == [], "the feed's assignment was taken as gone"
    assert any("Review session" in i["title"] for i in app.table("items")), "the feed stopped bringing its events"

    # kept in step by the API now: done in Friday ticks Canvas's To Do
    app.do("done", id=ps5["id"])
    world.send()
    assert world.fake.items[key]["planner_override"]["marked_complete"] is True


def test_a_feed_from_another_school_or_a_plain_link_keeps_its_assignments(world: World) -> None:
    app = world.app
    world.connect()
    app.do("source_add", name="Other school", url="https://canvas.otherschool.edu/feeds/calendars/user_x.ics")
    read_feeds(app.conn, app.now_utc, fetch=lambda url: FEED)
    assert any("Problem set 5" in (s["title"] or "") for s in app.table("raw_inputs")), "another school's was taken"


def test_the_assignment_behind_an_item_is_its_own_a_quizs_or_none() -> None:
    assert canvas.assignment_of({"plannable_type": "assignment", "plannable_id": 51001, "plannable": {}}) == "51001"
    assert canvas.assignment_of({"plannable_type": "quiz", "plannable": {"assignment_id": 951001}}) == "951001"
    assert canvas.assignment_of({"plannable_type": "discussion_topic", "plannable": {"assignment": {"id": 7}}}) == "7"
    assert canvas.assignment_of({"plannable_type": "discussion_topic", "plannable_id": 8, "plannable": {}}) is None


def test_syncing_again_after_the_handover_keeps_the_one_to_do(world: World) -> None:
    app = world.app
    app.do("source_add", name="Canvas", url=f"https://{SITE}/feeds/calendars/user_abc123.ics")
    read_feeds(app.conn, app.now_utc, fetch=lambda url: FEED)
    accept_all(app)
    world.fake.add("Problem set 5", "2026-10-23T17:00", assignment=951001, kind="quiz")
    world.fake.add("Reading response", "2026-10-23", kind="discussion_topic")  # no assignment behind it to adopt
    world.connect()
    world.sync()
    world.sync()  # what it adopted is its own now: not adopted again
    titles = [i["title"] for i in app.table("items") if i["status"] == "todo"]
    assert titles.count("Problem set 5") == 1 and "Reading response" in titles, titles


def test_a_feeds_assignment_the_api_doesnt_bring_is_let_go_without_being_dropped(world: World) -> None:
    app = world.app
    app.do("source_add", name="Canvas", url=f"https://{SITE}/feeds/calendars/user_abc123.ics")
    read_feeds(app.conn, app.now_utc, fetch=lambda url: FEED)  # its suggestions wait in the Inbox
    world.connect()
    world.sync()  # the API's planner doesn't have Problem set 5 (handed in, or in another course)
    read_feeds(app.conn, app.now_utc + 24 * 60, fetch=lambda url: FEED)  # the feed's next read, a day on
    (feed_id,) = [s["id"] for s in app.table("sources") if s["kind"] == "ics"]
    raws = {r["external_id"]: r for r in app.table("raw_inputs") if r["source_id"] == feed_id}
    (assignment,) = [r for e, r in raws.items() if e.startswith("event-assignment-")]
    assert assignment["status"] == "ignored", "the feed still brings the assignment the API took over"
    asked = [s for s in app.table("suggestions") if s["raw_input_id"] == assignment["id"]]
    assert asked and {s["status"] for s in asked} == {"superseded"}, asked
    assert [s for s in app.table("suggestions") if s["command"] == "drop"] == [], "it was taken as gone"
    events = [r for e, r in raws.items() if e.startswith("event-calendar-event-")]
    assert events and events[0]["status"] != "ignored", "the feed stopped bringing its events"
