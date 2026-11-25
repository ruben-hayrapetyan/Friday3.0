"""Google calendars in Settings (tests/features.toml: calendars), the whole pipeline: a real `fridayd serve`, the list
the last Google sync saw written where the sync writes it (kv `google_calendars`, in this test server's own database;
nothing here talks to Google), `google_calendars` read over HTTP as Settings → Calendars reads it, and each switch
(`calendar_set`) read back through it."""

import json
import sqlite3
from collections.abc import Iterator

import pytest

from tests.system.test_beat_plan_system import Friday

SEEN = [
    {"id": "later@group", "name": "10. Later", "primary": False, "writable": True, "account": "me@gmail.com",
     "color": "#c2402d"},
    {"id": "me@gmail.com", "name": "me@gmail.com", "primary": True, "writable": True, "account": "me@gmail.com",
     "color": "#2a6c9c"},
    {"id": "todo@group", "name": "2. To-Do", "primary": False, "writable": False, "account": "me@gmail.com",
     "color": "#888888"},
    {"id": "holidays@group", "name": "Holidays", "source_name": "Holidays in United States", "primary": False,
     "account": "school@uni.edu", "color": "teal"},
]  # fmt: skip


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("calendars"))
    yield server
    server.stop()


def synced(friday: Friday, calendars: list[dict]) -> None:
    """What a Google sync leaves: the calendars it saw, in kv."""
    db = sqlite3.connect(friday.folder / "data" / "friday.db")
    db.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'google_calendars', ?) ON CONFLICT (user_id, key) "
               "DO UPDATE SET value = excluded.value", [json.dumps(calendars)])  # fmt: skip
    db.commit()
    db.close()


def by_id(friday: Friday) -> dict[str, dict]:
    return {c["id"]: c for c in friday.q("google_calendars")}


def refused(friday: Friday, **body: object) -> dict:
    answer = friday.http.post("/api/c/calendar_set", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_no_google_calendars_before_a_sync(friday: Friday) -> None:
    assert friday.q("google_calendars") == []


def test_the_calendars_a_sync_saw_are_listed_in_natural_order_none_read_yet(friday: Friday) -> None:
    synced(friday, SEEN)
    listed = friday.q("google_calendars")
    assert [c["name"] for c in listed] == ["2. To-Do", "10. Later", "Holidays in United States", "me@gmail.com"]
    found = {c["id"]: c for c in listed}
    assert all(not c["on"] and c["kind"] == "auto" and not c["trusted"] and c["last_sync"] is None for c in listed)
    assert found["me@gmail.com"]["primary"] is True and found["later@group"]["primary"] is False
    assert (found["later@group"]["writable"], found["later@group"]["editable"]) == (True, True)
    assert (found["todo@group"]["writable"], found["todo@group"]["editable"]) == (False, False)
    assert found["holidays@group"]["account"] == "school@uni.edu"


def test_each_calendar_wears_the_paint_nearest_its_color_never_one_that_means_something(friday: Friday) -> None:
    found = by_id(friday)
    assert found["me@gmail.com"]["color"] == "blue"
    assert found["todo@group"]["color"] == "graphite"  # a gray one
    assert found["later@group"]["color"] == "orange"  # red is kept for now and overdue
    assert found["holidays@group"]["color"] is None  # not a color


def test_switching_one_on_reads_it_as_the_kind_chosen(friday: Friday) -> None:
    said = friday.c("calendar_set", id="later@group", on=True, kind="Task")
    assert said["message"] == "Reading 10. Later"
    found = by_id(friday)
    assert (found["later@group"]["on"], found["later@group"]["kind"]) == (True, "Task")
    assert not any(c["on"] for k, c in found.items() if k != "later@group")  # only that one


def test_trusting_one_and_back_to_auto_are_saved(friday: Friday) -> None:
    assert friday.c("calendar_set", id="later@group", trusted=True)["message"] == "Saved 10. Later"
    assert by_id(friday)["later@group"]["trusted"] is True
    friday.c("calendar_set", id="later@group", kind="auto")
    found = by_id(friday)["later@group"]
    assert (found["kind"], found["on"], found["trusted"]) == ("auto", True, True)  # the rest as it was


def test_changes_made_here_stop_going_back_to_a_calendar_when_you_say(friday: Friday) -> None:
    friday.c("calendar_set", id="me@gmail.com", editable=False)
    assert by_id(friday)["me@gmail.com"]["editable"] is False
    friday.c("calendar_set", id="me@gmail.com", editable=True)
    assert by_id(friday)["me@gmail.com"]["editable"] is True


def test_a_calendar_google_wont_let_you_change_cant_be_made_editable(friday: Friday) -> None:
    said = refused(friday, id="todo@group", editable=True)
    assert said == {"field": "editable", "message": "editable: Google doesn't let you change this calendar's events"}
    assert by_id(friday)["todo@group"]["editable"] is False


def test_switching_it_off_stops_reading_it(friday: Friday) -> None:
    assert friday.c("calendar_set", id="later@group", on=False)["message"] == "Stopped reading 10. Later"
    assert by_id(friday)["later@group"]["on"] is False


def test_a_calendar_the_sync_didnt_see_or_a_kind_that_isnt_one_is_refused(friday: Friday) -> None:
    said = refused(friday, id="gone@group", on=True)
    assert said["field"] == "id" and "no such calendar in your Google account (as of the last sync)" in said["message"]
    said = refused(friday, id="todo@group", kind="Nonsense")
    assert said == {"field": "kind", "message": "kind: no kind called Nonsense"}
    assert by_id(friday)["todo@group"]["kind"] == "auto"
    assert "gone@group" not in by_id(friday)


def test_a_calendar_gone_from_the_next_sync_leaves_the_list(friday: Friday) -> None:
    synced(friday, [c for c in SEEN if c["id"] != "todo@group"])
    assert [c["name"] for c in friday.q("google_calendars")] == ["10. Later", "Holidays in United States",
                                                                  "me@gmail.com"]  # fmt: skip
