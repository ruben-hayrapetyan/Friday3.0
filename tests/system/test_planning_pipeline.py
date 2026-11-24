"""Letting a lock move (tests/features.toml: planning), the whole pipeline: a real `fridayd serve` and its worker
replanning. Something locked where hard work has to go makes that work late; the Inbox asks; "Let it move" sends
`resolve`, the lock becomes a pin that only prefers its place, and the plan that follows has the work on time, the
question gone. Refusals change nothing."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("planning"))
    now = datetime.now(ZoneInfo(TZ))
    awake = {"bedtime": f"{now + timedelta(hours=8):%H:%M}", "wake": f"{now + timedelta(hours=15):%H:%M}"}
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, awake | {"margin_min": 0}))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def locked(friday: Friday) -> dict[str, Any]:
    """An errand locked for the next two hours, and a problem set that needs those two hours, due when they end."""
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    start = now + timedelta(minutes=30 - now.minute % 15)  # on a quarter hour, 15–30 min from now
    end = start + timedelta(hours=2)
    errand = friday.c("add", title="Errand run", duration_min=120, due=local(now + timedelta(days=4)))["item"]
    friday.c("pin", id=errand["id"], start=local(start), end=local(end), kind="locked")
    work = friday.c("add", title="Problem set", duration_min=120, firmness="hard", due=local(end))["item"]
    friday.c("replan")
    asked = friday.until(lambda: lock_decisions(friday))
    return {"errand": errand["id"], "work": work["id"], "start": local(start), "end": local(end), "asked": asked}


def lock_decisions(friday: Friday) -> list[dict[str, Any]]:
    return [d for d in friday.q("status")["decisions"] if d["kind"] == "lock"]


def late(friday: Friday) -> set[int]:
    return {i["item_id"] for i in friday.q("status")["late_items"]}


def errand_blocks(friday: Friday, locked: dict[str, Any]) -> list[dict[str, Any]]:
    end = local(datetime.now(ZoneInfo(TZ)) + timedelta(days=5))
    return [b for b in friday.q("plan", start=locked["start"], end=end)["blocks"] if b["item_id"] == locked["errand"]]


def refused(friday: Friday, **body: Any) -> dict[str, Any]:
    answer = friday.http.post("/api/c/resolve", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_1_the_lock_makes_the_work_late_and_the_inbox_asks(friday: Friday, locked: dict[str, Any]) -> None:
    (asked,) = locked["asked"]
    assert asked["item_id"] == locked["errand"] and asked["title"] == "Keep Errand run where you locked it?"
    assert "Problem set" in asked["detail"]
    assert locked["work"] in late(friday)
    (block,) = [b for b in errand_blocks(friday, locked) if b["start"] == locked["start"]]
    assert block["pinned"] == "locked" and block["end"] == locked["end"]


def test_2_refusals_name_what_is_wrong_and_leave_the_lock(friday: Friday, locked: dict[str, Any]) -> None:
    pin = locked["asked"][0]["pin_id"]
    none = refused(friday, unlock_pin_ids=[])
    assert none["field"] == "unlock_pin_ids" and "name the locks to let move" in none["message"]
    unknown = refused(friday, unlock_pin_ids=[pin + 1000])
    assert unknown["field"] == "unlock_pin_ids" and f"no locked pin {pin + 1000}" in unknown["message"]
    # one good and one unknown: the whole answer is refused, the good one isn't let go either
    refused(friday, unlock_pin_ids=[pin, pin + 1000])
    answer = friday.http.post("/api/c/resolve", json={"unlock_pin_ids": "all"})
    assert answer.status_code == 422
    assert [d["pin_id"] for d in lock_decisions(friday)] == [pin]
    assert all(b["pinned"] == "locked" for b in errand_blocks(friday, locked))


def test_3_let_it_move_puts_the_work_on_time_and_the_question_away(friday: Friday, locked: dict[str, Any]) -> None:
    pin = locked["asked"][0]["pin_id"]
    said = friday.c("resolve", unlock_pin_ids=[pin])
    assert said["status"] == "replanning" and said["message"] == "Unlocked; replanning"
    assert friday.until(lambda: locked["work"] not in late(friday) and not lock_decisions(friday))
    blocks = errand_blocks(friday, locked)
    assert blocks and all(b["pinned"] != "locked" for b in blocks)  # still planned, no longer held
    assert sum(minutes(b) for b in blocks) == 120  # all of it, elsewhere
    work = [
        b
        for b in friday.q("plan", start=locked["start"], end=locked["end"])["blocks"]
        if b["item_id"] == locked["work"]
    ]
    assert sum(minutes(b) for b in work) == 120  # the problem set has the two hours the lock held


def minutes(block: dict[str, Any]) -> int:
    return int((datetime.fromisoformat(block["end"]) - datetime.fromisoformat(block["start"])).total_seconds() // 60)


def test_4_a_lock_let_go_is_no_longer_a_lock_to_let_go(friday: Friday, locked: dict[str, Any]) -> None:
    pin = locked["asked"][0]["pin_id"]
    again = refused(friday, unlock_pin_ids=[pin])
    assert f"no locked pin {pin}" in again["message"]


def test_5_an_events_hold_let_go_is_taken(friday: Friday, locked: dict[str, Any]) -> None:
    # an event's time held for a task is named by the event's id, negative (planner/holds.py): taken, where an
    # unknown lock's id is refused
    assert friday.c("resolve", unlock_pin_ids=[-12345])["status"] == "replanning"
    assert friday.until(lambda: locked["work"] not in late(friday))
