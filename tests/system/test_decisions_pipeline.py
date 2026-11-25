"""What only you can decide, in the Inbox (tests/features.toml: decisions), the whole pipeline: a real `fridayd serve`
on the real clock, its worker replanning after each change, and the Inbox's answers (`late_accept`, `lock_keep`) sent
over HTTP as its buttons send them; what the Inbox then asks is read back from `status`, as the Inbox and its count read
it. The next hours are kept awake whatever the time the test runs (sleep starts 14 hours from now)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, WEEKDAYS, Friday


def quarter() -> datetime:
    """The next quarter hour, local: where the plan's slots start."""
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    return now + timedelta(minutes=15 - now.minute % 15)


def at(minutes: int) -> str:
    return (quarter() + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def awake(friday: Friday) -> None:
    bed = quarter() + timedelta(hours=14)
    times = {"bedtime": bed.strftime("%H:%M"), "wake": (bed + timedelta(hours=8)).strftime("%H:%M"), "margin_min": 0}
    friday.c("settings_set", key="sleep", value=dict.fromkeys(WEEKDAYS, times))


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("decisions"))
    awake(server)
    yield server
    server.stop()


def asked(friday: Friday, kind: str) -> list[dict]:
    return [d for d in friday.q("status")["decisions"] if d["kind"] == kind]


def late_ids(friday: Friday) -> set[int]:
    return {i["item_id"] for d in asked(friday, "late") for i in d["items"]}


def planned(friday: Friday) -> None:
    """The worker has planned every change so far."""
    # five minutes: a fresh server's first plans, beside others on a busy machine, took over 90 s (24 Nov, debian)
    friday.until(lambda: (s := friday.q("status"))["plan_generation"] is not None
                 and s["plan_generation"] >= s["generation"], timeout=300)  # fmt: skip


def refused(friday: Friday, verb: str, **body: object) -> dict:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


@pytest.fixture(scope="module")
def late(friday: Friday) -> list[int]:
    """Two things due in three hours that need four between them, the rest of the day busy after."""
    friday.c("add", title="busy", when="fixed", start=at(180), end=at(600))
    made = [
        friday.c("add", title=title, duration_min=120, firmness="hard", due=at(180))["item"]["id"]
        for title in ("essay draft", "lab report")
    ]
    friday.c("add", title="email the TA", duration_min=30, firmness="hard", due=at(60 * 24 * 6))
    assert friday.until(lambda: late_ids(friday) & set(made))
    return made


def test_work_that_will_be_late_waits_in_the_inbox_naming_it(friday: Friday, late: list[int]) -> None:
    (decision,) = asked(friday, "late")
    assert decision["key"] == "late" and decision["hours"] > 0
    assert decision["title"] in ("essay draft will be late", "lab report will be late", "2 things will be late")
    assert {i["item_id"] for i in decision["items"]} <= set(late)
    assert {i["title"] for i in friday.q("status")["late_items"]} & {"essay draft", "lab report"}


def test_only_late_work_can_be_left_late(friday: Friday, late: list[int]) -> None:
    on_time = next(i["id"] for i in friday.q("items") if i["title"] == "email the TA")
    said = refused(friday, "late_accept", item_ids=[on_time])
    assert said == {"field": "item_ids", "message": f"item_ids: item {on_time} isn't late"}
    assert refused(friday, "late_accept", item_ids=[999_999])["message"] == "item_ids: item 999999 isn't late"
    assert late_ids(friday)  # still asked


def test_leaving_it_late_takes_it_out_of_the_inbox(friday: Friday, late: list[int]) -> None:
    shown = sorted(late_ids(friday))
    said = friday.c("late_accept", item_ids=shown)
    assert said["message"] == ("Left it late" if len(shown) == 1 else "Left late")
    assert asked(friday, "late") == []
    assert {i["item_id"] for i in friday.q("status")["late_items"]} >= set(shown)  # still late, said so elsewhere


def test_left_late_stays_answered_when_more_is_added(friday: Friday, late: list[int]) -> None:
    friday.c("add", title="read ch 4", duration_min=60, firmness="soft", due=at(60 * 24 * 5))
    planned(friday)
    assert asked(friday, "late") == []


def test_one_answer_left_late_is_kept_and_new_late_work_is_asked_about(friday: Friday, late: list[int]) -> None:
    slides = friday.c("add", title="slides", duration_min=90, firmness="hard", due=at(15))["item"]["id"]
    friday.until(lambda: slides in late_ids(friday))
    assert late_ids(friday) == {slides}  # only the new one: the others were answered
    friday.c("late_accept", item_ids=[slides])
    assert asked(friday, "late") == []


@pytest.fixture(scope="module")
def lock(friday: Friday, late: list[int]) -> dict:
    """The late work out of the way, then a chore locked in the middle of the only free time before a due."""
    for item in friday.q("items"):
        friday.c("drop", id=item["id"])
    friday.c("add", title="cover letter", duration_min=120, firmness="hard", shape="one_sitting", due=at(180))
    chore = friday.c("add", title="call bank", duration_min=60)["item"]["id"]
    friday.c("pin", id=chore, start=at(60), end=at(120), kind="locked")
    found = friday.until(lambda: asked(friday, "lock"))
    return found[0]


def test_a_lock_that_makes_work_late_is_asked_about_by_name(friday: Friday, lock: dict) -> None:
    assert lock["title"] == "Keep call bank where you locked it?"
    assert lock["key"] == f"lock:{lock['pin_id']}" and lock["start"] == at(60)
    assert "cover letter finish" in lock["detail"] and lock["hours"] >= 0.25
    blocks = [b for b in friday.q("plan", start=at(0), end=at(600))["blocks"] if b["title"] == "call bank"]
    assert [(b["start"], b["pinned"]) for b in blocks] == [(at(60), "locked")]  # kept meanwhile: nothing waits


def test_keeping_the_lock_takes_it_out_of_the_inbox_and_keeps_it_there(friday: Friday, lock: dict) -> None:
    said = friday.c("lock_keep", pin_ids=[lock["pin_id"]])
    assert said["message"] == "Kept call bank"
    assert asked(friday, "lock") == []
    friday.c("replan")
    planned(friday)
    assert asked(friday, "lock") == []  # not asked again: it makes it no later than when you answered
    blocks = [b for b in friday.q("plan", start=at(0), end=at(600))["blocks"] if b["title"] == "call bank"]
    assert [b["start"] for b in blocks] == [at(60)]


def test_only_a_lock_making_work_late_can_be_kept(friday: Friday, lock: dict) -> None:
    said = refused(friday, "lock_keep", pin_ids=[lock["pin_id"] + 1000])
    assert said == {"field": "pin_ids", "message": f"pin_ids: lock {lock['pin_id'] + 1000} isn't making work late"}
    answer = friday.http.post("/api/c/lock_keep", json={"pin_ids": "all"})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body", "pin_ids"]
