"""The plan for the Mac app's "Friday" calendar through the whole of Friday (tests/features.toml: mac_plan; 24 Nov, the
user: "build an extensive test suite"): a real `fridayd serve` planning in its worker, the Mac app's `mac_plan` asked
over HTTP as it asks every minute, and its answer checked against the plan the web app reads: the same blocks, the
same plan, a break as one all-day event, nothing once switched off."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday, local


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("mac_plan_pipeline"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def caught_up(friday: Friday) -> bool:
    s = friday.q("status")
    return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]


def settled(friday: Friday) -> dict:
    """The plan once the worker has caught up with every change."""
    return friday.until(lambda: caught_up(friday) and friday.q("plan"))


def utc(moment: str) -> str:
    """A local time as the Mac's blocks give it: RFC 3339 in UTC."""
    at = datetime.fromisoformat(moment).replace(tzinfo=ZoneInfo(TZ)).astimezone(ZoneInfo("UTC"))
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def item_of(block: dict) -> int:
    return int(block["key"].split("@")[0].removeprefix("T"))


def today() -> date:
    return datetime.now(ZoneInfo(TZ)).date()


def test_1_off_until_switched_on(friday: Friday) -> None:
    friday.c("add", title="Essay draft", duration_min=120, due=local(datetime.now(ZoneInfo(TZ)) + timedelta(days=3)))
    settled(friday)
    assert friday.q("mac_plan") == {"wanted": False, "name": "Friday", "plan": None, "blocks": []}


def test_2_on_it_is_the_plans_work_from_now_with_the_plans_id(friday: Friday) -> None:
    friday.c("settings_set", key="mac_plan", value=True)
    assert friday.q("settings")["mac_plan"] is True
    plan = settled(friday)
    out = friday.q("mac_plan")
    assert out["wanted"] is True and out["name"] == "Friday" and out["plan"] == plan["plan_id"]
    timed = [b for b in out["blocks"] if not b["all_day"]]
    # one event per block, nothing else: the same item at the same moment (the plan's in local time, the Mac's UTC)
    shown = {(b["item_id"], utc(b["start"]), utc(b["end"])): b["title"] for b in plan["blocks"]}
    assert {(item_of(b), b["start"], b["end"]) for b in timed} == set(shown)
    assert len({b["key"] for b in timed}) == len(timed)
    assert all(b["title"] == shown[(item_of(b), b["start"], b["end"])] for b in timed)
    essay = [b for b in timed if b["title"] == "Essay draft"]
    assert essay and all(b["start"].endswith("Z") and b["start"] < b["end"] for b in essay)
    now = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M")
    assert all(b["end"][:16] > now for b in timed)  # from now on: nothing that's over


def test_3_a_new_task_is_on_it_once_planned_under_a_new_plan(friday: Friday) -> None:
    before = friday.q("mac_plan")["plan"]
    task = friday.c("add", title="Grant budget", duration_min=60,
                    due=local(datetime.now(ZoneInfo(TZ)) + timedelta(days=2)))["item"]["id"]  # fmt: skip
    friday.c("replan")
    friday.until(lambda: caught_up(friday) and friday.q("mac_plan")["plan"] != before)
    keys = {b["key"] for b in friday.q("mac_plan")["blocks"]}
    assert any(k.startswith(f"T{task}@") for k in keys)
    friday.c("done", id=task)
    friday.c("replan")
    friday.until(lambda: caught_up(friday) and not any(b["key"].startswith(f"T{task}@")
                                                        for b in friday.q("mac_plan")["blocks"]))  # fmt: skip


def test_4_a_break_is_one_all_day_event_from_its_first_day_to_the_day_after_its_last(friday: Friday) -> None:
    first, last = today() + timedelta(days=4), today() + timedelta(days=6)
    made = friday.c("vacation_add", name="Ski trip", start=str(first), end=str(last), mode="off")["vacation"]
    settled(friday)
    (one,) = [b for b in friday.q("mac_plan")["blocks"] if b["all_day"]]
    zone = ZoneInfo(TZ)
    assert one["key"] == f"break:{made['id']}" and one["title"] == "Ski trip" and not one["tentative"]
    assert one["start"] == datetime.combine(first, datetime.min.time(), zone).isoformat()
    assert one["end"] == datetime.combine(last + timedelta(days=1), datetime.min.time(), zone).isoformat()
    # no planned time on the break's days (its days are a list, not times)
    on_break = {str(first + timedelta(days=n)) for n in range(3)}
    timed = [b for b in friday.q("mac_plan")["blocks"] if not b["all_day"]]
    local_days = {datetime.fromisoformat(b["start"].replace("Z", "+00:00")).astimezone(zone).date().isoformat()
                  for b in timed}  # fmt: skip
    assert not local_days & on_break


def test_5_a_break_deleted_leaves_it(friday: Friday) -> None:
    (one,) = [b for b in friday.q("mac_plan")["blocks"] if b["all_day"]]
    friday.c("vacation_delete", id=int(one["key"].removeprefix("break:")))
    assert not [b for b in friday.q("mac_plan")["blocks"] if b["all_day"]]


def test_6_switched_off_again_it_asks_for_nothing(friday: Friday) -> None:
    friday.c("settings_set", key="mac_plan", value=False)
    assert friday.q("mac_plan") == {"wanted": False, "name": "Friday", "plan": None, "blocks": []}


def test_7_a_setting_that_isnt_a_switch_is_refused(friday: Friday) -> None:
    answer = friday.http.post("/api/c/settings_set", json={"key": "mac_plan", "value": "sometimes"})
    assert answer.status_code == 422, answer.text
    assert friday.q("settings")["mac_plan"] is False
