"""A calendar hidden in Setup's walk, through the whole of Friday (14 Nov: a client hid calendars in the walk and their
invitations still came into the Inbox): a real `fridayd serve`, the Mac app's post over HTTP, the sync job reading it
into the Inbox, then the walk's answers saved. The invitation leaves the Inbox and its count in the same answer, the
plan as anything but the calendar reads it leaves the calendar's events out, and showing it again brings them back."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

MAC = {"X-Friday-Client": "mac"}


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("hidden_calendars"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def calendars() -> list[dict[str, Any]]:
    return [{"id": cid, "name": name, "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}
            for cid, name in (("home", "Home"), ("invites", "Work invites"))]  # fmt: skip


def mac_sync(friday: Friday, events: list[dict[str, Any]]) -> None:
    zone = ZoneInfo(TZ)
    now = datetime.now(zone)
    body = {"calendars": calendars(), "events": events, "since": (now - timedelta(days=7)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    answer = friday.http.post("/api/c/mac_sync", headers=MAC, json=body)
    assert answer.status_code == 200, answer.text


def waiting(friday: Friday) -> set[str]:
    return {s["input"].get("title") for s in friday.q("inbox")["suggestions"]}


def test_a_calendar_hidden_in_the_walk_keeps_its_invitations_out_of_the_inbox(friday: Friday) -> None:
    day = datetime.now(ZoneInfo(TZ)).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=3)
    at = lambda h: (day + timedelta(hours=h)).isoformat()  # noqa: E731
    events = [
        {"id": "i1", "calendar": "invites", "title": "Quarterly planning", "start": at(14), "end": at(15)},
        {"id": "h1", "calendar": "home", "title": "Book club", "start": at(19), "end": at(20)},
    ]
    mac_sync(friday, [])
    for cid in ("home", "invites"):
        friday.c("calendar_set", id=cid, mac=True, trusted=False)  # each event waits in the Inbox, an invitation
    mac_sync(friday, events)
    assert friday.until(lambda: {"Quarterly planning", "Book club"} <= waiting(friday))

    picked = [{"name": "Home", "shown": True, "busy": True}, {"name": "Work invites", "shown": False, "busy": False}]
    friday.c("setup_save", **(friday.q("setup")["answers"] | {"calendars": picked}))
    assert "Quarterly planning" not in waiting(friday) and "Book club" in waiting(friday)  # in the same answer
    assert friday.q("status")["suggestions"] == len(friday.q("inbox")["suggestions"])  # the Inbox's count agrees
    mac_sync(friday, events)  # read again, still out of sight
    assert "Quarterly planning" not in waiting(friday)

    look = friday.q("settings")["calendar_look"]
    friday.c("settings_set", key="calendar_look", value=look | {"toolbar": []})  # Settings → Calendars: shown
    assert "Quarterly planning" in waiting(friday)
    assert friday.q("status")["suggestions"] == len(friday.q("inbox")["suggestions"])


def test_its_accepted_events_reach_only_the_calendar_and_there_marked_for_show(friday: Friday) -> None:
    (invite,) = [s for s in friday.q("inbox")["suggestions"] if s["input"].get("title") == "Quarterly planning"]
    friday.c("suggestion_accept", id=invite["id"])
    start = invite["input"]["start"][:10]
    window = {"start": f"{start}T00:00", "end": f"{start}T23:59"}
    assert "Quarterly planning" in {f["title"] for f in friday.q("plan", **window)["fixed"]}
    look = friday.q("settings")["calendar_look"]
    friday.c("settings_set", key="calendar_look", value=look | {"toolbar": ["Work invites"]})
    assert "Quarterly planning" not in {f["title"] for f in friday.q("plan", **window)["fixed"]}
    marked = {f["title"]: f for f in friday.q("plan", **window, with_hidden="true")["fixed"]}
    assert marked["Quarterly planning"]["hidden_calendar"] == "Work invites"
    assert friday.q("events", text="quarterly") == []
