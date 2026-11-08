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


def test_an_event_timed_over_its_whole_day_is_a_whole_day_event_and_not_busy(app: App) -> None:
    # 3 Nov: a birthday the Mac gave as 12:00 AM to 11:59 PM filled its day on the calendar and counted as busy.
    post(app, [HOME], [mac_event("b", "home", "Jasper's Birthday", "2026-10-21T00:00", "2026-10-21T23:59")])
    item = shown(app, "Jasper's Birthday")  # in, though whole-day events from a calendar wait for `include_all_day`
    assert item["start"] == "2026-10-21T00:00" and item["end"] == "2026-10-22T00:00"
    assert events(app)["Jasper's Birthday"]["blocks_time"] == 0
    post(app, [HOME], [mac_event("b", "home", "Jasper's Birthday", "2026-10-21T00:00", "2026-10-21T23:59")])
    assert len([i for i in app.table("items") if i["title"] == "Jasper's Birthday"]) == 1  # read again: the same one


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
    with pytest.raises(FieldError, match="The Mac doesn't let you"):
        app.do("calendar_set", id="home", mac=True, editable=True)  # EventKit says it can't be changed
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
    assert source["last_error"] == "No longer on your Mac"


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


# Changes made here to a Mac calendar's events, made on the Mac by the Mac app (`mac_writes`, then `mac_written`).
WRITABLE = calendar("home", "Home", writable=True)


def written(app: App, job: dict, **event: Any) -> None:
    """The Mac app's answer: done, with the event as EventKit now has it."""
    answer = {"id": job["id"], "ok": True}
    app.do("mac_written", **answer, **({"event": mac_event(**event)} if event else {}))


def test_an_event_changed_here_waits_for_the_mac_app_and_comes_back_as_the_same_event(app: App) -> None:
    post(app, [WRITABLE], [LECTURE])
    dentist = events(app)["Dentist"]
    assert shown(app, "Dentist")["saves_to_calendar"] is True
    assert app.do("mac_calendars")[0]["editable"] is True
    app.do("edit", id=dentist["id"], start="2026-10-20T12:00", end="2026-10-20T13:00")
    (job,) = app.do("mac_writes")
    assert {k: job[k] for k in ("op", "calendar", "event", "title", "start", "end", "all_day")} == {
        "op": "save",
        "calendar": "home",
        "event": "l1@1792504800",  # the Mac app finds a one-off by its identifier and its start on the calendar
        "title": None,  # a move leaves the calendar's title alone
        "start": "2026-10-20T16:00:00Z",
        "end": "2026-10-20T17:00:00Z",
        "all_day": False,
    }
    google = FakeGoogle({"Classes@group": []})
    assert write_events(app.conn, app.now_utc, google=google) == 0 and google.writes == []  # the Mac app's to make
    assert len(app.do("mac_writes")) == 1
    # A one-off event's id carries its start, so the move gives it a new one.
    written(app, job, eid="l1@moved", cid="home", title="Dentist", start="2026-10-20T12:00", end="2026-10-20T13:00")
    assert app.do("mac_writes") == []
    log = len(app.table("command_log"))
    moved = mac_event("l1@moved", "home", "Dentist", "2026-10-20T12:00", "2026-10-20T13:00")
    post(app, [WRITABLE], [moved], minutes_later=1)
    assert [i["id"] for i in events(app).values()] == [dentist["id"]]  # not dropped and made again
    assert shown(app, "Dentist")["start"] == "2026-10-20T12:00"
    assert len(app.table("command_log")) == log and app.do("inbox")["suggestions"] == []  # nothing new to read
    assert app.table("event_writes")[-1]["done_utc"] is not None and len(app.table("event_writes")) == 1


def test_the_answer_also_corrects_what_the_mac_last_posted(app: App) -> None:
    post(app, [WRITABLE], [LECTURE])
    dentist = events(app)["Dentist"]
    app.do("edit", id=dentist["id"], start="2026-10-20T12:00", end="2026-10-20T13:00")
    (job,) = app.do("mac_writes")
    written(app, job, eid="l1@moved", cid="home", title="Dentist", start="2026-10-20T12:00", end="2026-10-20T13:00")
    # The job reads the last posting again before the Mac app posts anew: the event isn't taken for gone.
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'mac_sync_now', '\"now\"')")
    sync(app.conn, app.now_utc + 1)
    assert [i["id"] for i in events(app).values()] == [dentist["id"]]


def test_a_title_goes_back_only_when_you_renamed_it_here(app: App) -> None:
    post(app, [WRITABLE], [mac_event("c1", "home", "Chem 2090 Lec (room 200)", "2026-10-20T10:00", "2026-10-20T11:00")])
    chem = next(iter(events(app).values()))
    # As the small model tidies a title it reads: the item and the suggestion it accepted say "Chem 2090 Lecture".
    app.conn.execute("UPDATE items SET title = 'Chem 2090 Lecture' WHERE id = ?", [chem["id"]])
    app.conn.execute(
        "UPDATE suggestions SET input = json_set(input, '$.title', 'Chem 2090 Lecture') WHERE item_id = ?", [chem["id"]]
    )
    app.do("edit", id=chem["id"], start="2026-10-20T10:30", end="2026-10-20T11:30")
    assert app.do("mac_writes")[0]["title"] is None  # the room stays in the calendar's title
    app.do("edit", id=chem["id"], title="Chem 2090 Lecture (moved to 120)")
    assert app.do("mac_writes")[-1]["title"] == "Chem 2090 Lecture (moved to 120)"


def test_an_event_deleted_here_is_deleted_on_the_mac(app: App) -> None:
    post(app, [WRITABLE], [LECTURE])
    dentist = events(app)["Dentist"]
    app.do("drop", id=dentist["id"])
    (job,) = app.do("mac_writes")
    assert (job["op"], job["calendar"], job["event"]) == ("delete", "home", "l1@1792504800")
    assert app.do("mac_written", id=job["id"], ok=True)["message"] == "Deleted from your calendar"
    post(app, [WRITABLE], [], minutes_later=1)
    assert events(app) == {} and app.do("inbox")["suggestions"] == []


def test_undoing_a_change_before_the_mac_app_asks_takes_it_back(app: App) -> None:
    post(app, [WRITABLE], [LECTURE])
    edit = app.full("edit", payload={"id": events(app)["Dentist"]["id"], "title": "Oops"}, provisional=False)
    app.do("undo", command_id=edit.command_id)
    assert app.do("mac_writes") == []


def test_a_change_the_mac_cant_make_is_tried_again_then_reported(app: App) -> None:
    from friday.commands.eventwrites import MAX_TRIES, failed_writes

    post(app, [WRITABLE], [LECTURE])
    app.do("edit", id=events(app)["Dentist"]["id"], title="Dentist at noon")
    for _ in range(MAX_TRIES):
        (job,) = app.do("mac_writes")
        assert app.do("mac_written", id=job["id"], ok=False, error="The event isn't on the calendar any more")
    assert app.do("mac_writes") == []
    assert failed_writes(app.conn) == [
        "Couldn't save Dentist at noon to your calendar (The event isn't on the calendar any more)"
    ]


def test_an_event_gone_from_the_mac_is_made_again_when_changed_here(app: App) -> None:
    # 31 Oct: one Saturday's Salsa, made here, had gone from Google; "Couldn't save Salsa to your calendar (The event
    # isn't on that calendar any more)" after five tries, for good.
    from friday.commands.eventwrites import failed_writes

    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    salsa = app.do("add", title="Salsa", when="fixed", start="2026-10-24T13:35", end="2026-10-24T14:40")["item"]
    (made,) = app.do("mac_writes")
    written(app, made, eid="s1", cid="gmail-cal", title="Salsa", start="2026-10-24T13:35", end="2026-10-24T14:40")
    app.do("edit", id=salsa["id"], start="2026-10-24T13:25", end="2026-10-24T14:30")
    (save,) = app.do("mac_writes")
    said = app.do("mac_written", id=save["id"], ok=False, gone=True, error="The event isn't on that calendar any more")
    assert said["message"] == "Not on your calendar any more: made again"
    (again,) = app.do("mac_writes")
    assert (again["id"], again["op"], again["calendar"], again["start"]) == (
        save["id"], "create", "gmail-cal", "2026-10-24T17:25:00Z"
    )  # fmt: skip
    written(app, again, eid="s2", cid="gmail-cal", title="Salsa", start="2026-10-24T13:25", end="2026-10-24T14:30")
    assert app.do("mac_writes") == [] and failed_writes(app.conn) == []
    log = len(app.table("command_log"))
    post(app, [GMAIL], [mac_event("s2", "gmail-cal", "Salsa", "2026-10-24T13:25", "2026-10-24T14:30")], 1)
    assert [i["id"] for i in events(app).values()] == [salsa["id"]]  # the same event: not dropped with s1, nor twice
    assert len(app.table("command_log")) == log and app.do("inbox")["suggestions"] == []
    app.do("edit", id=salsa["id"], location="Willard Straight Hall")
    assert app.do("mac_writes")[0]["event"].startswith("s2")  # and changes go to the new one


def test_a_change_given_up_on_stops_being_reported_once_a_later_one_is_saved(app: App) -> None:
    from friday.commands.eventwrites import MAX_TRIES, failed_writes

    post(app, [WRITABLE], [LECTURE])
    dentist = events(app)["Dentist"]["id"]
    app.do("edit", id=dentist, title="Dentist at noon")
    for _ in range(MAX_TRIES):
        (job,) = app.do("mac_writes")
        app.do("mac_written", id=job["id"], ok=False, error="Calendar was busy")
    assert failed_writes(app.conn) != []
    app.do("edit", id=dentist, title="Dentist at one")
    written(app, app.do("mac_writes")[0], eid="l1", cid="home", title="Dentist at one", start="2026-10-20T10:00",
            end="2026-10-20T11:00")  # fmt: skip
    assert failed_writes(app.conn) == []


def test_a_mac_calendar_you_said_not_to_edit_gets_nothing(app: App) -> None:
    post(app, [WRITABLE], [LECTURE])
    app.do("calendar_set", id="home", mac=True, editable=False)
    app.do("edit", id=events(app)["Dentist"]["id"], start="2026-10-20T12:00", end="2026-10-20T13:00")
    assert app.do("mac_writes") == [] and shown(app, "Dentist")["saves_to_calendar"] is False


# The Mac app's ids: "<EventKit identifier>@<occurrence start, Unix seconds>"; a one-off's start moves with it.
TEN_AM, ELEVEN_NEXT_DAY = 1792504800, 1792594800  # Tue 20 Oct 10am, Wed 21 Oct 11am (New York)


def test_a_one_off_event_moved_in_calendar_stays_the_same_event(app: App) -> None:
    post(app, [HOME], [mac_event(f"CAL:UID1@{TEN_AM}", "home", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00")])
    dentist = events(app)["Dentist"]
    app.do("edit", id=dentist["id"], notes="bring insurance card")
    moved = mac_event(f"CAL:UID1@{ELEVEN_NEXT_DAY}", "home", "Dentist", "2026-10-21T11:00", "2026-10-21T12:00")
    post(app, [HOME], [moved], minutes_later=5)
    (item,) = [i for i in app.table("items") if i["title"] == "Dentist"]
    assert (item["id"], item["status"], item["notes"]) == (dentist["id"], "todo", "bring insurance card")
    assert shown(app, "Dentist")["start"] == "2026-10-21T11:00"


def test_a_repeats_occurrences_keep_their_starts_apart(app: App) -> None:
    one = mac_event(f"GYM@{TEN_AM}", "home", "Gym", "2026-10-20T10:00", "2026-10-20T11:00", series="GYM")
    two = mac_event(f"GYM@{TEN_AM + 7 * 86400}", "home", "Gym", "2026-10-27T10:00", "2026-10-27T11:00", series="GYM")
    post(app, [HOME], [one, two])
    assert len([i for i in app.table("items") if i["title"] == "Gym"]) == 2


def test_one_off_events_read_before_take_their_new_ids(app: App) -> None:
    post(app, [HOME], [LECTURE])  # read once under the old ids
    app.conn.execute("UPDATE raw_inputs SET external_id = ? WHERE external_id = 'l1'", [f"CAL:UID1@{TEN_AM}"])
    dentist = events(app)["Dentist"]
    moved = mac_event(f"CAL:UID1@{ELEVEN_NEXT_DAY}", "home", "Dentist", "2026-10-21T11:00", "2026-10-21T12:00")
    post(app, [HOME], [moved], minutes_later=5)
    assert [i["id"] for i in events(app).values()] == [dentist["id"]] and app.do("inbox")["suggestions"] == []


# New events made here for one of the Mac's calendars (27 Oct: "i want new events to go to
# you@gmail.com", a Google calendar Friday reads through the Mac): made by the Mac app, and tied to
# the event here, so the next reading finds it, not a second one.
GMAIL = calendar("gmail-cal", "you@gmail.com", account="Google", writable=True)


def test_a_new_event_for_a_mac_calendar_is_made_by_the_mac_app_and_comes_back_as_itself(app: App) -> None:
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    made = app.do(
        "add",
        title="CUAI meeting",
        when="fixed",
        start="2026-10-24T16:00",
        end="2026-10-24T17:00",
        location="Gates 122",
    )["item"]
    (job,) = app.do("mac_writes")
    assert {k: job[k] for k in ("op", "calendar", "title", "start", "end", "all_day", "location")} == {
        "op": "create",
        "calendar": "gmail-cal",
        "title": "CUAI meeting",
        "start": "2026-10-24T20:00:00Z",
        "end": "2026-10-24T21:00:00Z",
        "all_day": False,
        "location": "Gates 122",
    }
    google = FakeGoogle({"Classes@group": []})
    assert write_events(app.conn, app.now_utc, google=google) == 0 and google.writes == []  # the Mac app's to make
    the_one = dict(eid="new1", cid="gmail-cal", title="CUAI meeting", start="2026-10-24T16:00", end="2026-10-24T17:00")
    written(app, job, **the_one, location="Gates 122")
    assert app.do("mac_writes") == []
    assert shown(app, "CUAI meeting")["calendar"] == "you@gmail.com"
    log = len(app.table("command_log"))
    post(app, [GMAIL], [mac_event(**the_one, location="Gates 122")], minutes_later=1)
    assert [i["id"] for i in events(app).values()] == [made["id"]]  # the same event, not a second
    assert len(app.table("command_log")) == log and app.do("inbox")["suggestions"] == []
    # From then on it's that calendar's event: a change here goes back to it as a change, not another new one.
    app.do("edit", id=made["id"], start="2026-10-24T18:00", end="2026-10-24T19:00")
    (moved,) = app.do("mac_writes")
    assert moved["op"] == "save" and moved["event"].startswith("new1") and moved["location"] is None


def test_a_new_event_for_a_mac_calendar_wears_its_colour_before_the_mac_app_makes_it(app: App) -> None:
    # 28 Oct: "Bike Inspection" came in grey: the calendar it was going to was looked up among Google's only, and the
    # Gmail calendar is the Mac's, so it had no calendar, and no colour, until the Mac read it back.
    post(app, [GMAIL | {"color": "#0088ff"}], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    made = app.do("add", title="Bike Inspection", when="fixed", start="2026-10-30T13:30", end="2026-10-30T14:30")
    assert app.do("mac_writes")  # not made on the Mac yet
    shown_now = app.do("item", id=made["item"]["id"])["item"]
    assert (shown_now["calendar"], shown_now["calendar_color"]) == ("you@gmail.com", "blue")
    plan = app.do("plan", start="2026-10-26T00:00", end="2026-11-02T00:00")
    (bike,) = [f for f in plan["fixed"] if f["title"] == "Bike Inspection"]
    assert bike["calendar_color"] == "blue"


def test_a_new_event_changed_before_the_mac_app_makes_it_is_made_once_as_it_is_then(app: App) -> None:
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    made = app.do("add", title="Salsa", when="fixed", start="2026-10-23T18:15", end="2026-10-23T19:15")["item"]
    app.do("edit", id=made["id"], start="2026-10-23T18:30", end="2026-10-23T19:30", location="Barton Hall")
    (job,) = app.do("mac_writes")
    assert (job["op"], job["start"], job["location"]) == ("create", "2026-10-23T22:30:00Z", "Barton Hall")


def test_a_new_event_goes_only_to_a_mac_calendar_that_may_be_changed(app: App) -> None:
    post(app, [calendar("ro", "Holidays", account="Google")], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "ro"})
    app.do("add", title="Party", when="fixed", start="2026-10-23T18:00", end="2026-10-23T19:00")
    assert app.do("mac_writes") == [] and app.table("event_writes") == []


def test_a_new_event_the_mac_couldnt_make_is_tried_again(app: App) -> None:
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    app.do("add", title="Salsa", when="fixed", start="2026-10-23T18:15", end="2026-10-23T19:15")
    (job,) = app.do("mac_writes")
    app.do("mac_written", id=job["id"], ok=False, error="That calendar isn't on this Mac any more")
    assert [j["op"] for j in app.do("mac_writes")] == ["create"]


# Where events are (27 Oct: "add support for adding locations to events").
def test_a_mac_events_place_comes_with_it_and_a_place_changed_here_goes_back(app: App) -> None:
    post(
        app,
        [WRITABLE],
        [mac_event("l1", "home", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00", location="Main St 5")],
    )
    dentist = events(app)["Dentist"]
    assert shown(app, "Dentist")["location"] == "Main St 5"
    app.do("edit", id=dentist["id"], start="2026-10-20T12:00", end="2026-10-20T13:00")
    assert app.do("mac_writes")[-1]["location"] is None  # a move leaves the calendar's place alone
    app.do("edit", id=dentist["id"], location="Main St 7")
    assert app.do("mac_writes")[-1]["location"] == "Main St 7"


def test_a_place_changed_on_the_mac_is_changed_here_and_one_taken_off_goes(app: App) -> None:
    def dentist(**place: str) -> dict[str, Any]:
        return mac_event("l1", "home", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00", **place)

    post(app, [HOME], [dentist(location="Main St 5")])
    post(app, [HOME], [dentist(location="Elm St 2")], minutes_later=5)  # the job reads a calendar every few minutes
    assert shown(app, "Dentist")["location"] == "Elm St 2"
    post(app, [HOME], [dentist()], minutes_later=10)
    assert shown(app, "Dentist")["location"] is None


def test_events_read_before_places_were_are_not_read_as_changed(app: App) -> None:
    post(app, [HOME], [LECTURE])
    log = len(app.table("command_log"))
    post(app, [HOME], [LECTURE], minutes_later=1)
    assert len(app.table("command_log")) == log


# 28 Oct: "put all new events that are in friday also on google". Repeating events made here (Gym, CUAI, Salsa) never
# went to a calendar: only one-off events were sent. Each time of a repeat now goes as an event of its own.


def gym(app: App, **extra: Any) -> dict:
    return app.do(
        "add", title="Gym", when="fixed", start="2026-10-20T07:30", end="2026-10-20T09:00", every="week", **extra
    )


def every_time(app: App, title: str) -> list[dict]:
    return [i for i in app.table("items") if i["title"] == title and i["status"] == "todo"]


def creates(app: App) -> list[dict]:
    return [j for j in app.do("mac_writes") if j["op"] == "create"]


def test_each_time_of_a_repeating_event_made_here_goes_to_the_calendar(app: App) -> None:
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    made = gym(app)
    times = every_time(app, "Gym")
    assert made["occurrences"] == len(times) > 4
    jobs = creates(app)
    assert len(jobs) == len(times) and {j["calendar"] for j in jobs} == {"gmail-cal"}
    assert sorted(j["start"] for j in jobs)[0] == "2026-10-20T11:30:00Z"
    # The Mac app makes each; from then on each is that calendar's event, tied to its time here.
    for job in jobs:
        start = job["start"].replace(":00Z", "")
        written(app, job, eid=f"gym{job['id']}", cid="gmail-cal", title="Gym",
                start=local(start), end=local(job["end"].replace(":00Z", "")))  # fmt: skip
    assert app.do("mac_writes") == []
    # A change to the repeat from a date on goes to each of those times there.
    first = min(times, key=lambda i: i["start_utc"])
    app.do("edit", id=first["id"], from_date="2026-10-27", location="Teagle Hall")
    saves = [j for j in app.do("mac_writes") if j["op"] == "save"]
    assert saves and all(j["location"] == "Teagle Hall" for j in saves)
    assert len(saves) == len([i for i in times if i["occurrence_date"] >= "2026-10-27"])


def local(utc: str) -> str:
    """A UTC time from a write as New York's wall time, the way `mac_event` takes it (before 1 November)."""
    from datetime import datetime, timedelta

    return (datetime.fromisoformat(utc) - timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M")


def test_deleting_a_repeat_on_a_calendar_takes_each_time_off_it(app: App) -> None:
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    series = gym(app)["series_id"]
    (job, *_) = sorted(creates(app), key=lambda j: j["start"])
    written(app, job, eid="gym1", cid="gmail-cal", title="Gym", start="2026-10-20T07:30", end="2026-10-20T09:00")
    linked = next(i for i in every_time(app, "Gym") if i["start_utc"] == "2026-10-20T11:30Z")
    app.do("series_delete", id=series)
    # The one on the calendar is taken off it with every later time (and kept here, dropped, so its copy there stays
    # tied to it); the times still waiting to be made are never made.
    (gone,) = [j for j in app.do("mac_writes") if j["op"] == "delete_from"]
    assert gone["event"].startswith("gym1")
    assert creates(app) == []
    assert app.do("item", id=linked["id"])["item"]["status"] == "dropped"
    assert every_time(app, "Gym") == []


def test_a_repeat_kept_only_in_friday_stays_there(app: App) -> None:
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    gym(app, calendar="")
    assert creates(app) == []
    app.do("materialize")
    assert creates(app) == []
    assert "Every event" in app.do("events_to_calendar")["message"]


def test_events_made_before_a_calendar_was_chosen_are_put_on_it_once_asked(app: App) -> None:
    post(app, [GMAIL], [])
    gym(app)
    one = app.do("add", title="Options Pricing Group Meeting", when="fixed", start="2026-10-21T19:00",
                 end="2026-10-21T20:00")["item"]  # fmt: skip
    mine = app.do("add", title="Therapy", when="fixed", start="2026-10-22T10:00", end="2026-10-22T11:00",
                  calendar="")["item"]  # fmt: skip
    assert app.do("mac_writes") == []  # nowhere to go yet
    assert "Choose where new events go" in app.do("events_to_calendar")["message"]
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    gyms = every_time(app, "Gym")
    said = app.do("events_to_calendar")["message"]
    assert said == f"{len(gyms) + 1} events on the way to your calendar"
    titles = sorted(j["title"] for j in creates(app))
    assert titles == sorted(["Gym"] * len(gyms) + ["Options Pricing Group Meeting"])
    assert mine["id"] not in {j.get("item_id") for j in app.table("event_writes")}
    assert one["id"] in {w["item_id"] for w in app.table("event_writes")}
    # Asked again before the Mac app has made them, nothing is sent twice.
    assert "Every event" in app.do("events_to_calendar")["message"]
    assert len(creates(app)) == len(gyms) + 1


def test_an_event_made_to_repeat_here_repeats_on_the_mac_and_comes_back_as_one_series(app: App) -> None:
    # 30 Oct: "the friday night salsa that's on this week should be a weekly event" failed with "Salsa comes from
    # ruben...@gmail.com: make it repeat there"; that calendar comes in through the Mac. The Mac app makes it repeat
    # there, and its occurrences come back as this one series, this week's the same event.
    from datetime import datetime

    def secs(day: str) -> int:
        return int(datetime.fromisoformat(f"2026-{day}T18:15:00-04:00").timestamp())

    one_off = mac_event(f"s1@{secs('10-23')}", "home", "Salsa", "2026-10-23T18:15", "2026-10-23T19:30")
    post(app, [WRITABLE], [one_off])
    salsa = events(app)["Salsa"]
    app.do("repeat", id=salsa["id"], every="fri")
    (job,) = app.do("mac_writes")
    assert (job["op"], job["rule"], job["event"]) == ("repeat", "FREQ=WEEKLY;BYDAY=FR", f"s1@{secs('10-23')}")
    weekly = [
        mac_event(f"s1@{secs(d)}", "home", "Salsa", f"2026-{d}T18:15", f"2026-{d}T19:30", series="s1")
        for d in ("10-23", "10-30", "11-06", "11-13")
    ]
    app.do("mac_written", id=job["id"], ok=True, event=weekly[0])
    assert app.do("mac_writes") == []
    post(app, [WRITABLE], weekly, minutes_later=1)
    assert app.do("inbox")["suggestions"] == []
    salsas = [i for i in app.table("items") if i["title"] == "Salsa" and i["status"] == "todo"]
    assert len(salsas) == 4 and salsa["id"] in {i["id"] for i in salsas}  # this week's kept, the rest come in
    assert len({i["series_id"] for i in salsas}) == 1 and salsas[0]["series_id"] is not None
