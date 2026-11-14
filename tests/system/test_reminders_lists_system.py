"""Apple Reminders' lists through the whole of Friday (13 Nov: a client's Shopping List came in as tasks to plan): a
real `fridayd serve`, the Mac app's side spoken over HTTP as RemindersBridge speaks it, and the box's commands. The
first read is under way, then in; a list switched off leaves Friday in the same answer; switched on, it's back, and
the job loop reads Reminders again at once rather than at its minute."""

import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

HOME = {"id": "CAL-0001-HOME", "title": "Home"}
SHOPPING = {"id": "CAL-0002-SHOPPING", "title": "Shopping List"}


def reminder(rid: str, title: str, where: dict[str, str], due: str | None = None) -> dict[str, Any]:
    """One reminder as RemindersPayload.reminder sends it."""
    return {"id": rid, "title": title, "notes": "", "list": where["title"], "list_id": where["id"],
            "completed": False} | ({"due": due} if due else {})  # fmt: skip


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("reminders-lists"))
    yield server
    server.stop()


def titles(friday: Friday) -> set[str]:
    return {i["title"] for i in friday.q("items")}


def box(friday: Friday) -> dict[str, Any]:
    (found,) = [c for c in friday.q("integrations") if c["kind"] == "reminders"]
    return found


def test_a_list_switched_off_leaves_at_once_and_comes_back_switched_on(friday: Friday) -> None:
    soon = f"{datetime.now(ZoneInfo(TZ)).date() + timedelta(days=3)}"
    connected = friday.c("integration_connect", kind="reminders", token="")["source"]
    friday.c("integration_set", id=connected["id"], arrival="straight")
    assert connected["reading"] is True and connected["lists"] and connected["off_removes"]
    sent = [reminder("r-1", "Milk", SHOPPING), reminder("r-2", "Eggs", SHOPPING),
            reminder("r-3", "Pay rent", HOME, soon)]  # fmt: skip
    friday.c("reminders_sync", reminders=sent, lists=[HOME, SHOPPING])
    began = time.monotonic()
    assert friday.until(lambda: {"Milk", "Eggs", "Pay rent"} <= titles(friday))
    assert time.monotonic() - began < 20, "read at the job's minute, not when the Mac app sent them"
    assert friday.until(lambda: not box(friday)["reading"])
    lists = {t["name"]: t for t in friday.q("integration_lists", id=connected["id"])}
    assert lists["Shopping List"]["id"] == SHOPPING["id"] and lists["Shopping List"]["made"] == 2

    friday.c("integration_list_set", id=connected["id"], list=SHOPPING["id"], on=False)
    assert not titles(friday) & {"Milk", "Eggs"} and "Pay rent" in titles(friday)  # in the same answer
    assert friday.q("reminder_writes")["jobs"] == [], "switching a list off ticked its reminders in Reminders"

    friday.c("integration_list_set", id=connected["id"], list=SHOPPING["id"], on=True)
    assert {"Milk", "Eggs"} <= titles(friday)  # back at once
    sent[0] = reminder("r-1", "Oat milk", SHOPPING)  # as Reminders has it now
    friday.c("reminders_sync", reminders=sent, lists=[HOME, SHOPPING])
    began = time.monotonic()
    assert friday.until(lambda: "Oat milk" in titles(friday))
    assert time.monotonic() - began < 20
    assert "Milk" not in titles(friday) and friday.q("reminder_writes")["jobs"] == []
