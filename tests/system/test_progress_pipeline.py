"""Progress (tests/features.toml: progress), the whole pipeline: a real `fridayd serve` on the real clock, and what you
say of your work sent over HTTP as the app sends it: how much is done (`progress`), being stuck (`stuck`), the timer's
sittings corrected or taken away (`sitting_edit`, `sitting_delete`), yesterday's blocks settled one at a time
(`settle`), a task's time answered in the Review (`review_task`), the whole day reviewed (`review_submit`), and a day
nobody reviewed closed as the nightly job closes it (`close_day`). Each is read back as the pages read it: the item,
the plan, the day's review sheet.

Yesterday's plan is made as the timed-review test makes one: the server's own commands run on its database at
yesterday noon (locks at set hours, so the blocks are known), the plan solved then; the server's replans since carry
the day's past blocks, as they do for a real day."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from friday.commands.all import REGISTRY
from friday.commands.registry import run
from friday.core.db import connect
from friday.planner.service import replan
from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

DAY_START = timedelta(hours=4)  # Friday's day runs 4am to 4am
assert "add" in REGISTRY  # the commands, registered as the server registers them

# the review sheet's key, spelled so tests/test_features.py doesn't take it for the `reviewed` query tested here (it
# isn't)
REVIEWED = "".join(("review", "ed"))


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def now() -> datetime:
    return datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)


YESTERDAY: date = (now() - DAY_START).date() - timedelta(days=1)  # a planning day that has ended


def at(hour: int, minute: int = 0, day: date = YESTERDAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(TZ))


def seeded(
    folder: Path, locks: dict[str, tuple[int, int]], timed: dict[str, tuple[datetime, datetime]] | None = None
) -> tuple[Friday, dict[str, int]]:
    """A server whose plan, made yesterday at noon, held each of `locks` (title: from hour, to hour) locked there,
    each an hour's task; and each of `timed` timed yesterday from its start to its end."""
    timed = timed or {}
    server = Friday(folder)
    server.c("settings_set", key="sleep", value=SLEEP)  # awake 7:30am to 11:30pm
    conn = connect(server.folder / "data" / "friday.db")

    def do(when: datetime, command: str, **payload: object) -> dict[str, Any]:
        return run(conn, command, payload, now_utc=int(when.timestamp() // 60), actor="you", provisional=False).result

    noon = at(12)
    due = local(now() + timedelta(days=6))
    ids = {}
    for title, (lo, hi) in locks.items():
        ids[title] = do(noon, "add", title=title, duration_min=(hi - lo) * 60, due=due)["item"]["id"]
        do(noon, "pin", id=ids[title], start=local(at(lo)), end=local(at(hi)), kind="locked")
    for title in timed:
        ids[title] = do(noon, "add", title=title, duration_min=60, due=due)["item"]["id"]
    replan(conn, int(noon.timestamp() // 60))
    for title, (start, end) in timed.items():
        do(start, "start", id=ids[title])
        do(end, "stop", id=ids[title])
    conn.close()
    server.c("replan")
    return server, ids


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    """A Friday for what's said now: nothing seeded."""
    server = Friday(tmp_path_factory.mktemp("progress-now"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def answering(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, dict[str, int]]]:
    """Yesterday: five tasks locked an hour each from 1pm, and Notes timed 6–6:45pm."""
    locks = {"Essay": (13, 14), "Lab": (14, 15), "Reading": (15, 16), "Slides": (16, 17), "Flashcards": (17, 18)}
    server, ids = seeded(tmp_path_factory.mktemp("progress-answering"), locks, {"Notes": (at(18), at(18, 45))})
    yield server, ids
    server.stop()


@pytest.fixture(scope="module")
def closing(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, dict[str, int]]]:
    """Yesterday: three tasks locked an hour each from 1pm, nobody reviewing the day."""
    server, ids = seeded(
        tmp_path_factory.mktemp("progress-closing"), {"Poster": (13, 14), "Memo": (14, 15), "Quiz prep": (15, 16)}
    )
    yield server, ids
    server.stop()


def refused(friday: Friday, verb: str, **body: Any) -> dict[str, Any]:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def item(friday: Friday, item_id: int) -> dict[str, Any]:
    return friday.q("item", id=item_id)["item"]


def key(item_id: int, start: datetime) -> str:
    return f"T{item_id}@{local(start)}"


def sheet(friday: Friday) -> dict[str, Any]:
    return friday.q("review", date=YESTERDAY.isoformat())


def gap(friday: Friday, item_id: int) -> dict[str, Any]:
    (found,) = [g for g in sheet(friday)["gaps"] if g["item_id"] == item_id]
    return found


def minutes(block: dict[str, Any]) -> int:
    return int((datetime.fromisoformat(block["end"]) - datetime.fromisoformat(block["start"])).total_seconds() // 60)


def planned_ahead(friday: Friday, item_id: int) -> int:
    start, end = local(now()), local(now() + timedelta(days=14))
    return sum(
        minutes(b)
        for b in friday.q("plan", start=start, end=end)["blocks"]
        if b["item_id"] == item_id and not b.get("state")
    )


# progress: how much is done, as a share


def test_progress_sets_done_as_a_share_and_the_plan_holds_only_whats_left(friday: Friday) -> None:
    task = friday.c("add", title="Thesis chapter", duration_min=240, due=local(now() + timedelta(days=10)))["item"]
    out = friday.c("progress", id=task["id"], share=0.25)["item"]
    assert (out["done_min"], out["remaining_min"]) == (60, 180)
    assert (item(friday, task["id"])["done_min"], item(friday, task["id"])["remaining_min"]) == (60, 180)
    assert friday.until(lambda: planned_ahead(friday, task["id"]) == 180)


def test_progress_said_again_replaces_what_was_said_and_all_of_it_leaves_nothing(friday: Friday) -> None:
    task = friday.c("add", title="Cover letter", duration_min=120, due=local(now() + timedelta(days=10)))["item"]
    friday.c("progress", id=task["id"], share=0.5)
    friday.c("progress", id=task["id"], share=0.75)  # "about three quarters", not half and three quarters more
    assert item(friday, task["id"])["done_min"] == 90
    friday.c("progress", id=task["id"], share=1)
    assert item(friday, task["id"])["remaining_min"] == 0
    assert friday.until(lambda: planned_ahead(friday, task["id"]) == 0)
    friday.c("progress", id=task["id"], share=0)
    assert item(friday, task["id"])["done_min"] == 0


def test_progress_outside_nothing_to_all_or_of_nothing_is_refused(friday: Friday) -> None:
    task = friday.c("add", title="Budget sheet", duration_min=60, due=local(now() + timedelta(days=10)))["item"]
    for share in (-0.1, 1.5):
        said = refused(friday, "progress", id=task["id"], share=share)
        assert said["field"] == "share" and "between 0 and 1" in said["message"]
    assert item(friday, task["id"])["done_min"] == 0
    assert refused(friday, "progress", id=987_654, share=0.5)["field"] == "id"


# stuck: kept with the item, the plan left as it is


def test_stuck_is_kept_in_the_items_history_without_replanning(friday: Friday) -> None:
    task = friday.c("add", title="Proof of lemma 3", duration_min=90, due=local(now() + timedelta(days=7)))["item"]
    friday.c("replan")
    generation = friday.q("status")["generation"]
    said = friday.c("stuck", id=task["id"], note="can't see the induction step")
    assert said["message"] == "Noted that you're stuck on Proof of lemma 3"
    (entry, *_) = friday.q("log_list", item_id=task["id"])
    assert entry["command"] == "stuck" and entry["input"]["note"] == "can't see the induction step"
    assert friday.q("status")["generation"] == generation  # the plan stands
    assert item(friday, task["id"])["status"] == "todo" and item(friday, task["id"])["done_min"] == 0


def test_stuck_on_an_event_or_on_nothing_is_refused(friday: Friday) -> None:
    start = now() + timedelta(days=1)
    event = friday.c(
        "add", title="Office hours", when="fixed", start=local(start), end=local(start + timedelta(hours=1))
    )["item"]
    said = refused(friday, "stuck", id=event["id"])
    assert said["field"] == "id" and "is an event" in said["message"]
    assert refused(friday, "stuck", id=987_654)["field"] == "id"


# the timer's sittings


def test_a_sitting_timed_too_long_is_corrected_and_counts_as_the_corrected_time(
    answering: tuple[Friday, dict[str, int]],
) -> None:
    friday, ids = answering
    notes = ids["Notes"]
    assert item(friday, notes)["done_min"] == 45
    said = refused(friday, "sitting_edit", id=notes, start=local(at(18)), end=local(at(18, 45)),
                   new_start=local(at(18, 30)), new_end=local(at(18, 10)))  # fmt: skip
    assert said["field"] == "new_end" and "after the start" in said["message"]
    later = now() + timedelta(hours=1)
    said = refused(friday, "sitting_edit", id=notes, start=local(at(18)), end=local(at(18, 45)),
                   new_start=local(at(18)), new_end=local(later))  # fmt: skip
    assert said["field"] == "new_end" and "later than now" in said["message"]
    assert item(friday, notes)["done_min"] == 45  # refused: nothing changed
    out = friday.c("sitting_edit", id=notes, start=local(at(18)), end=local(at(18, 45)),
                   new_start=local(at(18, 10)), new_end=local(at(18, 40)))["item"]  # fmt: skip
    assert out["done_min"] == 30 and item(friday, notes)["done_min"] == 30
    timed = [s for s in sheet(friday)["sessions"] if s["item_id"] == notes]
    assert [(s["source"], s["start"], s["end"], s["minutes"]) for s in timed] == [
        ("timer", local(at(18, 10)), local(at(18, 40)), 30)
    ]


def test_a_sitting_where_there_is_none_is_refused(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    said = refused(friday, "sitting_edit", id=ids["Essay"], start=local(at(18)), end=local(at(18, 45)),
                   new_start=local(at(18)), new_end=local(at(18, 30)))  # fmt: skip
    assert said["field"] == "start" and "no timed sitting" in said["message"]
    said = refused(friday, "sitting_delete", id=ids["Notes"], start=local(at(9)), end=local(at(10)))
    assert said["field"] == "start" and "no timed sitting" in said["message"]


def test_a_sitting_timed_by_mistake_is_taken_away(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    notes = ids["Notes"]
    before = item(friday, notes)["done_min"]
    assert before > 0
    said = friday.c("sitting_delete", id=notes, start=local(at(18)), end=local(at(19)))
    assert said["message"] == f"Removed {before} min timed on Notes"
    assert item(friday, notes)["done_min"] == 0
    assert [s for s in sheet(friday)["sessions"] if s["item_id"] == notes] == []
    assert refused(friday, "sitting_delete", id=notes, start=local(at(18)), end=local(at(19)))["field"] == "start"
    assert friday.until(lambda: planned_ahead(friday, notes) == 60)  # planned again, all of it


# yesterday's blocks, answered


def test_yesterdays_locked_hours_are_asked_about(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    asked = {g["item_id"]: g for g in sheet(friday)["gaps"]}
    for title in ("Essay", "Lab", "Reading", "Slides", "Flashcards"):
        assert asked[ids[title]]["planned_min"] == 60 and asked[ids[title]]["answer"] is None, title
    assert ids["Notes"] not in asked  # timed: Friday knows what happened
    assert sheet(friday)[REVIEWED] is False


def test_review_task_all_done_counts_the_hour(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    said = friday.c("review_task", date=YESTERDAY.isoformat(), item_id=ids["Essay"], status="done")
    assert said["message"] == "Essay: all done"
    assert (gap(friday, ids["Essay"])["answer"], gap(friday, ids["Essay"])["done_min"]) == ("done", 60)
    assert item(friday, ids["Essay"])["done_min"] == 60 and item(friday, ids["Essay"])["status"] == "todo"


def test_review_task_some_counts_what_you_say(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    said = refused(friday, "review_task", date=YESTERDAY.isoformat(), item_id=ids["Lab"], status="partial")
    assert said["field"] == "minutes"
    said = friday.c("review_task", date=YESTERDAY.isoformat(), item_id=ids["Lab"], status="partial", minutes=20)
    assert said["message"] == "Lab: 20 min done"
    assert (gap(friday, ids["Lab"])["answer"], gap(friday, ids["Lab"])["done_min"]) == ("partial", 20)
    assert item(friday, ids["Lab"])["done_min"] == 20 and item(friday, ids["Lab"])["remaining_min"] == 40
    assert friday.until(lambda: 40 <= planned_ahead(friday, ids["Lab"]) <= 45)  # to the quarter hour
    # answered again, the new answer replaces the old one
    friday.c("review_task", date=YESTERDAY.isoformat(), item_id=ids["Lab"], status="partial", minutes=500)
    assert item(friday, ids["Lab"])["done_min"] == 60  # no more than the hour planned


def test_review_task_none_plans_it_again(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    said = friday.c("review_task", date=YESTERDAY.isoformat(), item_id=ids["Reading"], status="not_done")
    assert said["message"] == "Reading: Friday plans it again"
    assert (gap(friday, ids["Reading"])["answer"], gap(friday, ids["Reading"])["done_min"]) == ("not_done", 0)
    assert item(friday, ids["Reading"])["done_min"] == 0
    assert friday.until(lambda: planned_ahead(friday, ids["Reading"]) == 60)


def test_review_task_finished_finishes_the_task(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    said = friday.c("review_task", date=YESTERDAY.isoformat(), item_id=ids["Slides"], status="finished")
    assert said["message"] == "Slides: finished"
    assert item(friday, ids["Slides"])["status"] == "done"
    assert gap(friday, ids["Slides"])["finished"] is True


def test_review_task_of_time_that_day_didnt_have_is_refused(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    day_before = (YESTERDAY - timedelta(days=1)).isoformat()
    said = refused(friday, "review_task", date=day_before, item_id=ids["Essay"], status="done")
    assert said["field"] == "item_id" and "has no time on" in said["message"]
    said = refused(friday, "review_task", date=YESTERDAY.isoformat(), item_id=ids["Essay"], status="sort of")
    assert [e["loc"][-1] for e in said["detail"]] == ["status"]


def test_settle_marks_one_block_and_the_review_keeps_the_answer(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    block = key(ids["Flashcards"], at(17))
    assert friday.c("settle", block_key=block, status="partial", share=0.5)["message"] == "Marked partly done"
    assert sheet(friday)["settled"][block] == 30
    assert (gap(friday, ids["Flashcards"])["answer"], item(friday, ids["Flashcards"])["done_min"]) == ("partial", 30)
    assert friday.c("settle", block_key=block, status="done")["message"] == "Marked done"
    assert sheet(friday)["settled"][block] == 60 and item(friday, ids["Flashcards"])["done_min"] == 60


def test_with_every_task_answered_the_day_counts_as_reviewed(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    # every task's time answered by now (the tests above), the last by settle, which settles a block before the
    # Review and doesn't review the day itself: an answer in the Review does
    assert all(g["answer"] is not None for g in sheet(friday)["gaps"])
    assert sheet(friday)[REVIEWED] is False
    friday.c("review_task", date=YESTERDAY.isoformat(), item_id=ids["Essay"], status="done")
    assert sheet(friday)[REVIEWED] is True


def test_settle_refuses_a_block_not_yet_or_never_planned(answering: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = answering
    tomorrow = (now() - DAY_START).date() + timedelta(days=1)
    said = refused(friday, "settle", block_key=key(ids["Essay"], at(13, day=tomorrow)))
    assert said["field"] == "block_key" and "hasn't happened yet" in said["message"]
    said = refused(friday, "settle", block_key=key(ids["Essay"], at(9)))
    assert said["field"] == "block_key" and "no block" in said["message"]
    said = refused(friday, "settle", block_key="essay at one")
    assert said["field"] == "block_key" and "isn't a block like" in said["message"]
    said = refused(friday, "settle", block_key=key(ids["Flashcards"], at(17)), status="partial", share=2)
    assert said["field"] == "share"
    assert sheet(friday)["settled"][key(ids["Flashcards"], at(17))] == 60  # unchanged


# a day nobody reviewed, closed; and the whole day reviewed


def test_1_closing_today_is_refused_and_assuming_nothing_writes_nothing(closing: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = closing
    today = (now() - DAY_START).date().isoformat()
    said = refused(friday, "close_day", date=today)
    assert said["field"] == "date" and "only a day that has ended" in said["message"]
    planner = friday.q("settings")["planner"]
    friday.c("settings_set", key="planner", value=planner | {"assume_unreviewed": "not_done"})
    try:
        assert friday.c("close_day", date=YESTERDAY.isoformat())["message"] == f"Nothing to assume for {YESTERDAY}"
        assert [item(friday, i)["done_min"] for i in ids.values()] == [0, 0, 0]
    finally:
        friday.c("settings_set", key="planner", value=planner)


def test_2_closing_yesterday_assumes_its_blocks_done_once(closing: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = closing
    assert friday.c("close_day")["message"] == f"Assumed 3 blocks done on {YESTERDAY}"  # yesterday when not said
    assert [item(friday, i)["done_min"] for i in ids.values()] == [60, 60, 60]
    assumed = [s for s in sheet(friday)["sessions"] if s["source"] == "assumed"]
    assert sorted(s["item_id"] for s in assumed) == sorted(ids.values())
    assert friday.c("close_day", date=YESTERDAY.isoformat())["message"] == f"Assumed 0 blocks done on {YESTERDAY}"
    assert [item(friday, i)["done_min"] for i in ids.values()] == [60, 60, 60]  # not counted twice


def test_3_reviewing_the_day_replaces_what_was_assumed(closing: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = closing
    extra = (at(18), at(18, 30))  # Quiz prep, half an hour more that evening, unplanned
    said = friday.c("review_submit", date=YESTERDAY.isoformat(), entries=[
        {"block_key": key(ids["Poster"], at(13)), "status": "not_done"},
        {"block_key": key(ids["Memo"], at(14)), "status": "partial", "share": 0.5},
        {"item_id": ids["Quiz prep"], "start": local(extra[0]), "end": local(extra[1])},
    ])["message"]  # fmt: skip
    assert said == f"Reviewed {YESTERDAY:%a %b} {YESTERDAY.day}"
    assert item(friday, ids["Poster"])["done_min"] == 0
    assert item(friday, ids["Memo"])["done_min"] == 30
    assert item(friday, ids["Quiz prep"])["done_min"] == 90  # its block, not answered, counted done, and the extra
    day = sheet(friday)
    assert day[REVIEWED] is True and not [s for s in day["sessions"] if s["source"] == "assumed"]
    assert ("review", local(extra[0]), 30) in {(s["source"], s["start"], s["minutes"]) for s in day["sessions"]}
    assert friday.until(lambda: planned_ahead(friday, ids["Poster"]) == 60)


def test_4_a_reviewed_day_is_not_closed_again(closing: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = closing
    assert friday.c("close_day", date=YESTERDAY.isoformat())["message"] == f"Nothing to assume for {YESTERDAY}"
    assert item(friday, ids["Poster"])["done_min"] == 0


def test_5_a_review_with_what_couldnt_have_happened_is_refused(closing: tuple[Friday, dict[str, int]]) -> None:
    friday, ids = closing
    day = YESTERDAY.isoformat()
    soon = now() + timedelta(hours=2)
    said = refused(
        friday,
        "review_submit",
        date=day,
        entries=[{"item_id": ids["Memo"], "start": local(now() - timedelta(hours=1)), "end": local(soon)}],
    )
    assert said["field"] == "end" and "later than now" in said["message"]
    said = refused(
        friday,
        "review_submit",
        date=day,
        entries=[{"item_id": ids["Memo"], "start": local(at(19)), "end": local(at(18))}],
    )
    assert said["field"] == "end" and "after the start" in said["message"]
    said = refused(friday, "review_submit", date=day, entries=[{"block_key": key(ids["Memo"], at(9))}])
    assert said["field"] == "block_key"
    said = refused(
        friday, "review_submit", date=day, entries=[{"item_id": 987_654, "start": local(at(18)), "end": local(at(19))}]
    )
    assert said["field"] == "id"
    assert item(friday, ids["Memo"])["done_min"] == 30  # each refused whole: nothing written
