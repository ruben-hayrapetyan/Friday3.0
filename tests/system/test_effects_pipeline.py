"""What answering an invitation would do, the whole pipeline (tests/features.toml: effects; 24 Nov, the user: "build an
extensive test suite ... i want to make sure that absolutely nothing can break without our tests flagging it"): a real
`fridayd serve`; a Mac calendar's invitations come into the Inbox (the Mac app's post over HTTP, read by the sync job),
and `suggestion_effect` asked of one as the Inbox asks it: the events it clashes with, the work planned in its time
(read against the plan), the work it would make later; at its own time and at one you've edited it to."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

MAC = {"X-Friday-Client": "mac"}
DAY = (datetime.now(ZoneInfo(TZ)) + timedelta(days=3)).date()


def at(clock: str, day: date = DAY) -> str:
    return f"{day}T{clock}"


def zoned(clock: str) -> str:
    return datetime.fromisoformat(at(clock)).replace(tzinfo=ZoneInfo(TZ)).isoformat()


def mac_sync(friday: Friday, events: list[dict[str, Any]]) -> None:
    now = datetime.now(ZoneInfo(TZ))
    calendars = [{"id": "invites", "name": "Invites", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}]
    body = {"calendars": calendars, "events": events, "since": (now - timedelta(days=7)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    answer = friday.http.post("/api/c/mac_sync", headers=MAC, json=body)
    assert answer.status_code == 200, answer.text


def waiting(friday: Friday) -> dict[str, dict]:
    return {s["input"].get("title"): s for s in friday.q("inbox")["suggestions"]}


def effect(friday: Friday, **params: Any) -> dict:
    return friday.q("suggestion_effect", **params)


def refused(friday: Friday, **params: Any) -> str:
    answer = friday.http.get("/api/q/suggestion_effect", params=params)
    assert answer.status_code == 422, answer.text
    return answer.json()["message"]


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("effects"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


@pytest.fixture(scope="module")
def invited(friday: Friday) -> dict[str, dict]:
    """A seminar of yours from 2 to 3pm, three hours of problem set that must be done 11am to 2pm, planned; and two
    invitations waiting: planning from 1 to 2:30pm, and coffee in the evening."""
    friday.c("add", title="Seminar", when="fixed", start=at("14:00"), end=at("15:00"))
    friday.c("add", title="Problem set", duration_min=180, firmness="hard", release=at("11:00"), due=at("14:00"))
    mac_sync(friday, [])
    friday.c("calendar_set", id="invites", mac=True, on=True, trusted=False)  # each event waits in the Inbox
    events = [
        {"id": "e1", "calendar": "invites", "title": "Quarterly planning", "start": zoned("13:00"),
         "end": zoned("14:30")},
        {"id": "e2", "calendar": "invites", "title": "Coffee with Sam", "start": zoned("19:00"), "end": zoned("19:30")},
    ]  # fmt: skip
    mac_sync(friday, events)
    found = friday.until(lambda: (w := waiting(friday)) and {"Quarterly planning", "Coffee with Sam"} <= set(w) and w)

    def planned() -> bool:
        status = friday.q("status")
        return status["plan_generation"] is not None and status["plan_generation"] >= status["generation"]

    friday.until(planned)
    return found


def problem_set_blocks(friday: Friday) -> list[tuple[str, str]]:
    plan = friday.q("plan", start=at("00:00"), end=at("23:59"))
    return [(b["start"], b["end"]) for b in plan["blocks"] if b["title"] == "Problem set"]


def test_an_invitation_names_the_event_it_clashes_with_the_work_it_takes_and_makes_late(
    friday: Friday, invited: dict[str, dict]
) -> None:
    out = effect(friday, id=invited["Quarterly planning"]["id"])
    assert out["event"] is True
    assert [(c["title"], c["start"], c["end"]) for c in out["clashes"]] == [("Seminar", at("14:00"), at("15:00"))]
    blocks = problem_set_blocks(friday)
    assert blocks == [(at("11:00"), at("14:00"))]  # the only three hours it has
    assert [(t["title"], t["start"], t["end"]) for t in out["takes"]] == [("Problem set", *blocks[0])]
    (late,) = out["later"]
    assert late["title"] == "Problem set" and late["due"] == at("14:00") and late["hours"] >= 0.5


def test_an_invitation_at_a_free_time_changes_nothing(friday: Friday, invited: dict[str, dict]) -> None:
    out = effect(friday, id=invited["Coffee with Sam"]["id"])
    assert out == {"event": True, "clashes": [], "takes": [], "later": []}


def test_an_edited_time_is_what_is_weighed(friday: Friday, invited: dict[str, dict]) -> None:
    planning = invited["Quarterly planning"]["id"]
    out = effect(friday, id=planning, start=at("16:00"), end=at("17:00"))  # moved after it all: nothing
    assert out == {"event": True, "clashes": [], "takes": [], "later": []}
    out = effect(friday, id=planning, start=at("14:30"), end=at("15:30"))  # over the seminar's end only
    assert [c["title"] for c in out["clashes"]] == ["Seminar"] and out["takes"] == [] and out["later"] == []
    coffee = effect(friday, id=invited["Coffee with Sam"]["id"], start=at("12:00"), end=at("12:30"))
    assert [t["title"] for t in coffee["takes"]] == ["Problem set"] and coffee["clashes"] == []


def test_an_event_ending_before_it_starts_is_refused(friday: Friday, invited: dict[str, dict]) -> None:
    planning = invited["Quarterly planning"]["id"]
    assert refused(friday, id=planning, start=at("15:00"), end=at("14:00")) == "end: the event ends before it starts"
    assert refused(friday, id=planning, start=at("15:00"), end=at("15:00")) == "end: the event ends before it starts"


def test_only_a_suggestion_still_waiting_is_weighed(friday: Friday, invited: dict[str, dict]) -> None:
    assert refused(friday, id=999_999) == "id: no pending suggestion 999999"
    coffee = invited["Coffee with Sam"]["id"]
    friday.c("suggestion_reject", id=coffee)
    assert refused(friday, id=coffee) == f"id: no pending suggestion {coffee}"
    # accepted, the other is in the plan: its effect has happened and isn't asked again
    planning = invited["Quarterly planning"]["id"]
    friday.c("suggestion_accept", id=planning)
    assert "Quarterly planning" in {f["title"] for f in friday.q("plan", start=at("00:00"), end=at("23:59"))["fixed"]}
    assert refused(friday, id=planning) == f"id: no pending suggestion {planning}"


def test_a_suggested_task_is_no_event_so_nothing_is_said(friday: Friday, invited: dict[str, dict]) -> None:
    calendars = [{"id": "courses", "name": "Courses", "account": "iCloud", "type": "caldav", "color": "#3a5a8c"}]
    now = datetime.now(ZoneInfo(TZ))
    body = {"calendars": calendars, "events": [], "since": (now - timedelta(days=7)).isoformat(),
            "until": (now + timedelta(days=30)).isoformat()}  # fmt: skip
    assert friday.http.post("/api/c/mac_sync", headers=MAC, json=body).status_code == 200
    friday.c("calendar_set", id="courses", mac=True, on=True, trusted=False, kind="Assignment")
    body["events"] = [
        {"id": "c1", "calendar": "courses", "title": "HW 5", "start": zoned("23:59"), "end": zoned("23:59")}
    ]
    assert friday.http.post("/api/c/mac_sync", headers=MAC, json=body).status_code == 200
    homework = friday.until(lambda: waiting(friday).get("HW 5"))
    assert "start" not in homework["input"] and homework["input"]["due"] == at("23:59")  # a task due then
    out = effect(friday, id=homework["id"])
    assert out == {"event": False, "clashes": [], "takes": [], "later": []}
