"""Work archived once its due passed, the whole pipeline (tests/features.toml: pointless; 20 Nov, a user's notes: an
exam's prep "2h late" after the exam; your answer: "Archive it, say so", H232). A real `fridayd serve` on the real
clock: work that's pointless once late and already past its due is archived by the server's own job loop, the Inbox
says so (`inbox.archived`), and "OK" (`archived_ok`) and "Bring back" (`archived_restore`) are sent over HTTP as the
Inbox sends them, each effect read back through the items, the Inbox and the plan."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday

WAIT = 180  # the job loop's minute, and its 30 s rest


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("pointless"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def made(friday: Friday) -> dict[str, int]:
    """Due an hour ago: an exam's prep (pointless after by its kind), a reading you marked pointless after its due, and
    a problem set still worth doing late; and a quiz prep due tomorrow."""
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    past, later = local(now - timedelta(hours=1)), local(now + timedelta(days=1))

    def add(**fields: Any) -> int:
        return friday.c("add", duration_min=60, **fields)["item"]["id"]

    out = {
        "quiz": add(title="Midterm 2 study", preset="Exam prep", due=past),
        "reading": add(title="Reading response 9", due=past, expires=True),
        "pset": add(title="Problem set 6", due=past),
        "tomorrow": add(title="Final exam study", preset="Exam prep", due=later),
    }
    friday.until(lambda: len(archived(friday)) == 2, WAIT)
    return out


def archived(friday: Friday) -> list[dict[str, Any]]:
    return friday.q("inbox")["archived"]


def status(friday: Friday, item: int) -> str:
    return friday.q("item", id=item)["item"]["status"]


def test_pointless_work_past_its_due_is_archived_and_the_inbox_says_why(friday: Friday, made: dict[str, int]) -> None:
    said = {a["id"]: (a["title"], a["why"]) for a in archived(friday)}
    assert said == {made["quiz"]: ("Midterm 2 study", "Its exam is over"),
                    made["reading"]: ("Reading response 9", "Its due passed, and it's pointless after")}  # fmt: skip
    assert status(friday, made["quiz"]) == "dropped" and status(friday, made["reading"]) == "dropped"


def test_late_work_still_worth_doing_and_work_not_due_yet_stay(friday: Friday, made: dict[str, int]) -> None:
    assert status(friday, made["pset"]) == "todo"
    assert status(friday, made["tomorrow"]) == "todo"
    todo = {i["id"] for i in friday.q("items")}
    assert {made["pset"], made["tomorrow"]} <= todo and not {made["quiz"], made["reading"]} & todo


def test_archived_work_isnt_planned(friday: Friday, made: dict[str, int]) -> None:
    friday.c("replan")

    def planned() -> set[int] | None:
        s = friday.q("status")
        if s["plan_generation"] is None or s["plan_generation"] < s["generation"]:
            return None
        blocks = friday.q("plan")["blocks"]
        return {b["item_id"] for b in blocks if b.get("item_id")} | {0}

    ids = friday.until(planned, WAIT)
    assert made["quiz"] not in ids and made["reading"] not in ids
    assert made["tomorrow"] in ids


def test_ok_lets_the_note_go_and_the_work_stays_archived(friday: Friday, made: dict[str, int]) -> None:
    assert friday.c("archived_ok", id=made["reading"])["message"] == "OK"
    assert [a["id"] for a in archived(friday)] == [made["quiz"]]
    assert status(friday, made["reading"]) == "dropped"


def test_ok_for_one_with_no_note_changes_nothing(friday: Friday, made: dict[str, int]) -> None:
    assert friday.c("archived_ok", id=made["pset"])["message"] == "OK"
    assert [a["id"] for a in archived(friday)] == [made["quiz"]]
    assert status(friday, made["pset"]) == "todo"


def test_bring_back_opens_it_as_still_worth_doing_and_its_planned_late(friday: Friday, made: dict[str, int]) -> None:
    said = friday.c("archived_restore", id=made["quiz"])
    assert said["message"] == "Brought back Midterm 2 study, still worth doing"
    item = friday.q("item", id=made["quiz"])["item"]
    assert (item["status"], item["expires"], item["pointless_late"]) == ("todo", False, False)
    assert archived(friday) == []
    late = friday.until(lambda: {i["item_id"] for i in friday.q("status")["late_items"]} >= {made["quiz"]}, WAIT)
    assert late


def test_brought_back_it_isnt_archived_again_by_the_next_job_run(friday: Friday, made: dict[str, int]) -> None:
    # a new pointless one past its due: the job's next run archives it, and leaves the one brought back alone
    past = local(datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0) - timedelta(minutes=30))
    fresh = friday.c("add", title="Prelim 3 study", preset="Exam prep", due=past, duration_min=30)["item"]["id"]
    friday.until(lambda: [a["id"] for a in archived(friday)] == [fresh], WAIT)
    assert status(friday, made["quiz"]) == "todo"


# 24 Nov: found by this test (500, not a refusal); fixed
def test_bring_back_of_something_not_there_is_refused(friday: Friday) -> None:
    answer = friday.http.post("/api/c/archived_restore", json={"id": 99999})
    assert answer.status_code == 422, answer.text
    assert answer.json()["field"] == "id"
