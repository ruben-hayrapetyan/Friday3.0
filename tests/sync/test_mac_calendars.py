"""The Mac's calendars, fed in by the Mac app (COMBINED.md 4): `mac_sync` keeps what EventKit sees, and the sync job
reads each calendar you switched on from it as it reads Google's. A calendar starts on unless it's a copy of one read
from Google, a subscription or birthdays; its events skip the inbox; one gone from the Mac is suggested dropped."""

import json
from pathlib import Path
from typing import Any

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app

SINCE, UNTIL = "2026-10-18T00:00:00-04:00", "2026-12-14T00:00:00-05:00"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def calendar(cid: str, name: str, **extra: Any) -> dict[str, Any]:
    return {"id": cid, "name": name, "account": "iCloud", "type": "caldav", "color": "#3a5a8c"} | extra


def mac_event(eid: str, cid: str, title: str, start: str, end: str, **extra: Any) -> dict[str, Any]:
    """An event at local New York times like `2026-10-20T14:00` (before the clocks change on 1 November)."""
    return {"id": eid, "calendar": cid, "title": title, "start": f"{start}:00-04:00", "end": f"{end}:00-04:00"} | extra


HOME = calendar("home", "Home")
LECTURE = mac_event("l1", "home", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00")


def post(app: App, calendars: list[dict], events: list[dict], minutes_later: int = 0) -> None:
    """The Mac app posting, then the job's next minute."""
    app.do("mac_sync", calendars=calendars, events=events, since=SINCE, until=UNTIL)
    sync(app.conn, app.now_utc + minutes_later)


def shown(app: App, title: str) -> dict:
    """An event as the app shows it."""
    return app.do("item", id=events(app)[title]["id"])["item"]


def events(app: App) -> dict[str, dict]:
    return {i["title"]: i for i in app.table("items") if i["when_kind"] == "fixed" and i["status"] == "todo"}


def test_a_mac_calendars_events_go_straight_onto_the_plan(app: App) -> None:
    post(app, [HOME], [LECTURE])
    assert set(events(app)) == {"Dentist"}
    assert app.do("inbox")["suggestions"] == []  # trusted: nothing to answer
    item = shown(app, "Dentist")
    assert item["start"] == "2026-10-20T10:00" and item["end"] == "2026-10-20T11:00"
    assert item["calendar"] == "Home"
    assert item["saves_to_calendar"] is False


def test_which_calendars_start_on(app: App) -> None:
    app.conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (1, 'google_calendars', ?)",
        ['[{"id": "s@group", "name": "School", "primary": false}]'],
    )
    calendars = [
        HOME,
        calendar("school", "School"),  # Google's School, also on the Mac
        calendar("hol", "US Holidays", type="subscription"),
        calendar("bday", "Birthdays", type="birthday", account="Other"),
        calendar("local", "On My Mac", type="local", account="On My Mac"),
    ]
    post(app, calendars, [])
    listed = {c["name"]: c for c in app.do("mac_calendars")}
    assert [n for n, c in listed.items() if c["on"]] == ["Home", "On My Mac"]
    assert listed["School"]["also_google"] and not listed["Home"]["also_google"]
    assert all(c["trusted"] for c in listed.values())
    assert listed["Home"]["account"] == "iCloud" and listed["Home"]["editable"] is False
    assert list(listed) == sorted(listed, key=str.lower)


def test_calendars_that_share_a_name_are_told_apart_by_account(app: App) -> None:
    calendars = [
        calendar("a", "Calendar"),
        calendar("b", "Calendar", account="me@gmail.com"),
        calendar("c", "Calendar", account="me@gmail.com"),
        calendar("d", "Work", account=""),
    ]
    post(app, calendars, [])
    names = sorted(c["name"] for c in app.do("mac_calendars"))
    assert names == ["Calendar (iCloud)", "Calendar (me@gmail.com)", "Calendar (me@gmail.com) 2", "Work"]
    assert len(app.table("sources")) == 4


def test_an_event_moved_on_the_mac_moves_and_one_deleted_is_dropped(app: App) -> None:
    post(app, [HOME], [LECTURE])
    moved = mac_event("l1", "home", "Dentist", "2026-10-21T15:00", "2026-10-21T16:00")
    post(app, [HOME], [moved], minutes_later=5)
    item = shown(app, "Dentist")
    assert item["start"] == "2026-10-21T15:00"
    post(app, [HOME], [], minutes_later=10)
    assert events(app) == {}


def test_posting_the_same_again_changes_nothing(app: App) -> None:
    post(app, [HOME], [LECTURE])
    before = (len(app.table("suggestions")), len(app.table("items")), len(app.table("command_log")))
    post(app, [HOME], [LECTURE], minutes_later=5)
    assert (len(app.table("suggestions")), len(app.table("items")), len(app.table("command_log"))) == before


def test_declined_free_and_all_day_events(app: App) -> None:
    post(
        app,
        [HOME],
        [
            mac_event("x", "home", "Declined meeting", "2026-10-20T12:00", "2026-10-20T13:00", declined=True),
            mac_event("y", "home", "Maybe drinks", "2026-10-20T18:00", "2026-10-20T19:00", free=True),
            {
                "id": "z",
                "calendar": "home",
                "title": "Fall break",
                "start": "2026-10-22",
                "end": "2026-10-24",
                "all_day": True,
            },
        ],
    )
    found = events(app)
    assert "Declined meeting" not in found
    assert found["Maybe drinks"]["free"] == 1
    assert "Fall break" not in found  # whole-day events wait for `gcal.include_all_day`, as Google's do


def test_whole_day_events_when_you_count_them(app: App) -> None:
    app.do("settings_set", key="gcal", value={"include_all_day": True})
    whole = {
        "id": "z",
        "calendar": "home",
        "title": "Fall break",
        "start": "2026-10-22",
        "end": "2026-10-24",
        "all_day": True,
    }
    post(app, [HOME], [whole])
    item = shown(app, "Fall break")
    assert item["start"] == "2026-10-22T00:00" and item["end"] == "2026-10-24T00:00"


def test_a_repeating_events_occurrences_each_come_in(app: App) -> None:
    weekly = [
        mac_event(f"gym@{day}", "home", "Gym", f"2026-10-{day}T07:30", f"2026-10-{day}T08:30", series="gym")
        for day in (20, 27)
    ]
    post(app, [HOME], weekly)
    assert sorted(i["start_utc"] for i in app.table("items") if i["title"] == "Gym") == [
        "2026-10-20T11:30Z",
        "2026-10-27T11:30Z",
    ]


def test_switching_a_mac_calendar_off_and_on(app: App) -> None:
    post(app, [HOME], [LECTURE])
    app.do("calendar_set", id="home", mac=True, on=False)
    assert not app.do("mac_calendars")[0]["on"]
    post(app, [HOME], [LECTURE, mac_event("l2", "home", "Haircut", "2026-10-22T10:00", "2026-10-22T10:30")], 5)
    assert "Haircut" not in events(app)
    app.do("calendar_set", id="home", mac=True, on=True)
    sync(app.conn, app.now_utc + 10)  # switching on reads it on the next minute, without the Mac posting again
    assert "Haircut" in events(app)


def test_a_calendar_switched_off_leaves_your_calendar_and_comes_back_when_on(app: App) -> None:
    gym = [
        mac_event(f"gym@{day}", "home", "Gym", f"2026-10-{day}T18:00", f"2026-10-{day}T19:00", series="gym")
        for day in (22, 29)
    ]
    post(app, [HOME], [mac_event("h", "home", "Haircut", "2026-10-23T10:00", "2026-10-23T10:30"), *gym])

    def out() -> set[str]:
        return {f["title"] for f in app.do("plan", start="2026-10-19T00:00", end="2026-11-01T00:00")["fixed"]}

    assert out() == {"Haircut", "Gym"}
    said = app.full("calendar_set", payload={"id": "home", "mac": True, "on": False}, provisional=False)
    assert out() == set() and not any(i["active"] for i in app.table("series"))
    app.do("undo", command_id=said.command_id)
    assert out() == {"Haircut", "Gym"}
    app.do("calendar_set", id="home", mac=True, on=False)
    app.do("calendar_set", id="home", mac=True, on=False)  # again: nothing more to put away, nothing forgotten
    app.do("calendar_set", id="home", mac=True, on=True)
    assert out() == {"Haircut", "Gym"} and all(i["active"] for i in app.table("series"))
    sync(app.conn, app.now_utc + 10)
    assert sorted(i["title"] for i in app.table("items") if i["status"] == "todo").count("Gym") == 2  # no copies


def test_chromas_colours_come_with_their_events(app: App, tmp_path: Path) -> None:
    colors = {
        "CHROMA-CAL:l1": "blue",  # the dentist, by its event however Chroma named its calendar
        "CHROMA-CAL:gym/RID=800000000": "red",  # one occurrence of a repeat
        "CHROMA-CAL:gym": "green",  # and the whole repeat, which wins
        "CHROMA-CAL:nope": "default",  # Unmarked: nothing
    }
    (tmp_path / "colors.json").write_text(json.dumps(colors))
    gym = mac_event("gym", "home", "Gym", "2026-10-22T18:00", "2026-10-22T19:00")
    post(app, [HOME], [LECTURE, gym])
    out = app.do("import_chroma_colors", colors_path=str(tmp_path / "colors.json"))
    assert out["message"] == "Brought in Chroma's colours for 2 events"
    assert shown(app, "Dentist")["chroma_color"] == "blue" and shown(app, "Gym")["chroma_color"] == "green"
    with pytest.raises(FieldError, match="found no"):
        app.do("import_chroma_colors", colors_path=str(tmp_path / "gone.json"))


def test_a_mac_calendar_read_as_one_kind(app: App) -> None:
    post(app, [HOME], [])
    app.do("calendar_set", id="home", mac=True, kind="Class")
    post(app, [HOME], [LECTURE], minutes_later=5)
    assert events(app)["Dentist"]["preset"] == "Class"
    assert app.do("mac_calendars")[0]["kind"] == "Class"


def test_calendar_set_refuses_what_it_cant_do(app: App) -> None:
    post(app, [HOME], [])
    with pytest.raises(FieldError, match="on the Mac"):
        app.do("calendar_set", id="nope", mac=True, on=True)
    with pytest.raises(FieldError, match="Mac's calendars"):
        app.do("calendar_set", id="home", mac=True, editable=True)
    with pytest.raises(FieldError, match="Google account"):
        app.do("calendar_set", id="home", on=True)  # without `mac` it's a Google calendar's id


def test_a_mac_event_changed_in_friday_is_never_sent_to_google(app: App) -> None:
    app.do("settings_set", key="gcal", value={"new_events_to": "Classes@group"})
    post(app, [HOME], [LECTURE])
    dentist = events(app)["Dentist"]
    app.do("edit", id=dentist["id"], title="Dentist (moved here)")
    app.do("drop", id=dentist["id"])
    assert app.table("event_writes") == []
    google = FakeGoogle({"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]})
    assert write_events(app.conn, app.now_utc, google=google) == 0


def test_a_calendar_gone_from_the_mac_keeps_its_events_and_says_why(app: App) -> None:
    post(app, [HOME], [LECTURE])
    post(app, [], [], minutes_later=5)
    assert "Dentist" in events(app)  # not dropped: the calendar may be back
    source = next(s for s in app.table("sources") if s["kind"] == "mac")
    assert source["last_error"] == "LookupError: no longer on your Mac"


def test_a_renamed_calendar_keeps_its_source_and_one_made_again_takes_the_old_ones(app: App) -> None:
    post(app, [HOME], [])
    app.do("calendar_set", id="home", mac=True, on=False)
    post(app, [calendar("home", "Home & Family")], [], minutes_later=1)
    assert [(s["name"], s["enabled"]) for s in app.table("sources")] == [("Home & Family", 0)]
    post(app, [calendar("home2", "Home & Family")], [], minutes_later=2)  # deleted and made again
    assert [(s["name"], s["enabled"]) for s in app.table("sources")] == [("Home & Family", 0)]
    assert app.do("mac_calendars")[0]["on"] is False


def test_removing_a_kind_stops_a_mac_calendar_reading_into_it(app: App) -> None:
    app.do("kind_add", name="Checkup", like="Class")
    post(app, [HOME], [])
    app.do("calendar_set", id="home", mac=True, kind="Checkup")
    app.do("kind_remove", name="Checkup", move_to="Class")
    assert app.do("mac_calendars")[0]["kind"] == "auto"


def test_what_the_mac_app_posts_is_checked(app: App) -> None:
    with pytest.raises(FieldError, match="not listed"):
        app.do(
            "mac_sync",
            calendars=[HOME],
            events=[mac_event("x", "work", "X", "2026-10-20T10:00", "2026-10-20T11:00")],
            since=SINCE,
            until=UNTIL,
        )
    with pytest.raises(FieldError, match="offset"):
        app.do("mac_sync", calendars=[HOME], events=[], since="2026-10-18T00:00", until=UNTIL)
    with pytest.raises(FieldError, match="before"):
        app.do("mac_sync", calendars=[HOME], events=[], since=UNTIL, until=SINCE)
    assert app.table("sources") == []
    assert not app.do("mac_calendars")


def test_nothing_is_read_before_the_mac_app_posts(app: App) -> None:
    sync(app.conn, app.now_utc)
    assert app.table("sources") == [] and app.table("items") == []
