"""The Mac's calendars (tests/features.toml: mac), the whole pipeline: a real `fridayd serve`, the Mac app's side
played over HTTP as it plays it (`mac_sync`, what EventKit sees), the sync job reading what's switched on into your
calendar, and `mac_calendars` read as Settings → Calendars reads it. A Google calendar of the same name is written
where a Google sync leaves it (kv, in this test server's own database)."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

MAC = {"X-Friday-Client": "mac"}
CALENDARS = [
    {"id": "home-icloud", "name": "Home", "account": "iCloud", "type": "caldav", "color": "#2a6c9c", "writable": True},
    {"id": "home-google", "name": "Home", "account": "me@gmail.com", "type": "caldav", "color": "#c2402d"},
    {"id": "holidays", "name": "US Holidays", "account": "Other", "type": "subscription"},
    {"id": "birthdays", "name": "Birthdays", "account": "Other", "type": "birthday"},
    {"id": "work", "name": "Work", "account": "Exchange", "type": "exchange", "color": "#777777"},
    {"id": "local", "name": "2. Errands", "account": "On My Mac", "type": "local"},
]  # fmt: skip


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("mac"))
    yield server
    server.stop()


def mac_sync(friday: Friday, calendars: list[dict[str, Any]], events: list[dict[str, Any]] | None = None) -> dict:
    now = datetime.now(ZoneInfo(TZ))
    body = {"calendars": calendars, "events": events or [], "since": (now - timedelta(days=1)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    answer = friday.http.post("/api/c/mac_sync", headers=MAC, json=body)
    assert answer.status_code == 200, answer.text
    return answer.json()["result"]


def by_id(friday: Friday) -> dict[str, dict]:
    return {c["id"]: c for c in friday.q("mac_calendars")}


def tomorrow(hour: int) -> str:
    day = datetime.now(ZoneInfo(TZ)).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return (day + timedelta(hours=hour)).isoformat()


def on_calendar(friday: Friday, title: str) -> dict | None:
    """The event of that title on tomorrow's calendar, as the Plan page reads it."""
    day = tomorrow(0)[:10]
    found = [f for f in friday.q("plan", start=f"{day}T00:00", end=f"{day}T23:59")["fixed"] if f["title"] == title]
    return found[0] if found else None


def test_no_mac_calendars_before_the_mac_app_sends_any(friday: Friday) -> None:
    assert friday.q("mac_calendars") == []


def test_each_calendar_the_mac_sees_is_listed_named_apart_and_on_unless_it_shouldnt_be(friday: Friday) -> None:
    db = sqlite3.connect(friday.folder / "data" / "friday.db")
    db.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'google_calendars', ?)",
               [json.dumps([{"id": "w@group", "name": "Work", "primary": False}])])  # fmt: skip
    db.commit()
    db.close()
    said = mac_sync(friday, CALENDARS)
    assert said["message"] == "Read 0 events on 6 Mac calendars"
    listed = friday.q("mac_calendars")
    assert [c["name"] for c in listed] == ["2. Errands", "Birthdays", "Home (iCloud)", "Home (me@gmail.com)",
                                           "US Holidays", "Work"]  # fmt: skip
    on = {c["id"]: c["on"] for c in listed}
    assert on == {"home-icloud": True, "home-google": True, "local": True,
                  "holidays": False, "birthdays": False,  # a subscription and birthdays start off
                  "work": False}  # read from Google already, under the same name  # fmt: skip
    found = {c["id"]: c for c in listed}
    assert found["work"]["also_google"] is True and found["home-icloud"]["also_google"] is False
    assert all(c["trusted"] for c in listed)  # the Mac's events skip the inbox
    assert all(not c["primary"] and c["kind"] == "auto" for c in listed)


def test_its_color_account_and_whether_it_can_be_changed_are_shown(friday: Friday) -> None:
    found = by_id(friday)
    assert (found["home-icloud"]["color"], found["home-google"]["color"], found["work"]["color"]) == (
        "blue", "orange", "graphite")  # fmt: skip
    assert found["holidays"]["color"] is None
    assert found["home-icloud"]["account"] == "iCloud"
    assert (found["home-icloud"]["writable"], found["home-icloud"]["editable"]) == (True, True)
    assert (found["local"]["writable"], found["local"]["editable"]) == (False, False)


def test_an_event_on_a_calendar_that_is_on_reaches_your_calendar_and_is_put_away_when_its_off(friday: Friday) -> None:
    events = [
        {"id": "e1", "calendar": "home-icloud", "title": "Dentist", "start": tomorrow(14), "end": tomorrow(15)},
        {"id": "e2", "calendar": "holidays", "title": "Arbor Day", "start": tomorrow(0)[:10],
         "end": (datetime.fromisoformat(tomorrow(0)) + timedelta(days=1)).date().isoformat(), "all_day": True},
    ]  # fmt: skip
    assert mac_sync(friday, CALENDARS, events)["message"] == "Read 2 events on 6 Mac calendars"
    dentist = friday.until(lambda: on_calendar(friday, "Dentist"), timeout=180)  # the sync job, within the minute
    assert dentist["start"] == tomorrow(14)[:16] and dentist["end"] == tomorrow(15)[:16]
    assert on_calendar(friday, "Arbor Day") is None  # its calendar is off
    assert by_id(friday)["home-icloud"]["last_sync"] is not None  # read
    friday.c("calendar_set", id="home-icloud", mac=True, on=False)
    assert by_id(friday)["home-icloud"]["on"] is False
    assert on_calendar(friday, "Dentist") is None  # put away with its calendar
    assert friday.q("item", id=dentist["id"])["item"]["status"] == "dropped"
    friday.c("calendar_set", id="home-icloud", mac=True, on=True)
    assert by_id(friday)["home-icloud"]["on"] is True  # and back
    assert on_calendar(friday, "Dentist")["id"] == dentist["id"]


def test_a_calendar_renamed_on_the_mac_keeps_its_settings_under_the_new_name(friday: Friday) -> None:
    friday.c("calendar_set", id="local", mac=True, on=False, kind="Task")
    renamed = [c | {"name": "Chores"} if c["id"] == "local" else c for c in CALENDARS]
    mac_sync(friday, renamed)
    found = by_id(friday)["local"]
    assert (found["name"], found["on"], found["kind"]) == ("Chores", False, "Task")
    assert len(friday.q("mac_calendars")) == len(CALENDARS)  # the same one, not a second


def test_a_calendar_gone_from_the_mac_leaves_the_list(friday: Friday) -> None:
    mac_sync(friday, [c for c in CALENDARS if c["id"] != "birthdays"])
    assert "birthdays" not in by_id(friday)
    assert len(friday.q("mac_calendars")) == len(CALENDARS) - 1


def test_switching_a_calendar_the_mac_didnt_list_or_making_a_read_only_one_editable_is_refused(
    friday: Friday,
) -> None:
    answer = friday.http.post("/api/c/calendar_set", json={"id": "nope", "mac": True, "on": True})
    assert answer.status_code == 422
    assert answer.json()["message"] == "id: no such calendar on the Mac (as the Mac app last saw them)"
    answer = friday.http.post("/api/c/calendar_set", json={"id": "local", "mac": True, "editable": True})
    assert answer.json() == {"field": "editable", "message": "editable: The Mac doesn't let you change this "
                             "calendar's events"}  # fmt: skip
    assert "nope" not in by_id(friday) and by_id(friday)["local"]["editable"] is False


def test_a_sync_with_events_on_calendars_it_didnt_list_or_backwards_times_is_refused(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ))
    stray = {"calendars": CALENDARS[:1], "since": now.isoformat(), "until": (now + timedelta(days=1)).isoformat(),
             "events": [{"id": "x", "calendar": "elsewhere", "start": tomorrow(9), "end": tomorrow(10)}]}  # fmt: skip
    answer = friday.http.post("/api/c/mac_sync", headers=MAC, json=stray)
    assert answer.status_code == 422 and answer.json()["field"] == "events"
    backwards = stray | {"events": [], "until": (now - timedelta(days=1)).isoformat()}
    answer = friday.http.post("/api/c/mac_sync", headers=MAC, json=backwards)
    assert answer.json() == {"field": "until", "message": "until: until comes before since"}
    assert len(friday.q("mac_calendars")) == len(CALENDARS) - 1  # the list as the last good sync left it
