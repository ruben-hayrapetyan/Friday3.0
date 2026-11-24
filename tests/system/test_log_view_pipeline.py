"""The log and the week's stats, the whole pipeline (tests/features.toml: log_view; 24 Nov, the user: "go through every
single functionality of the app and build an extensive test suite"): a real `fridayd serve` in its own folder, changes
made over HTTP as the app makes them, and `log_list` (a block's History) and `stats` read back after each."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("log-view"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def soon(days: int) -> str:
    return local(datetime.now(ZoneInfo(TZ)).replace(hour=17, minute=0) + timedelta(days=days))


def run(friday: Friday, verb: str, **body: Any) -> tuple[int, Any]:
    """A command's log id and its result."""
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 200, answer.text
    return answer.json()["command_id"], answer.json()["result"]


# ---- stats -----------------------------------------------------------------------------------------------------------


def test_the_estimate_ratio_is_the_time_things_took_over_fridays_estimates(friday: Friday) -> None:
    # first in the file: nothing finished yet, so the ratio is these alone
    assert friday.q("stats") == {"done_this_week": 0, "hours_this_week": 0.0, "late_items": 0, "estimate_ratio": None}
    for n in (1, 2, 3):  # lengths you gave: Friday has no estimate of its own to compare yet
        item = friday.c("add", title=f"Stats: chapter {n}", preset="Reading", duration_min=60, due=soon(3))["item"]
        friday.c("done", id=item["id"], actual_min=30)
    assert friday.q("stats")["estimate_ratio"] is None
    four = friday.c("add", title="Stats: chapter 4", preset="Reading", due=soon(3))["item"]  # no length: Friday's
    g4 = friday.q("item", id=four["id"])["item"]["guess_min"]
    assert g4 == 30  # what the last three readings took
    friday.c("done", id=four["id"], actual_min=60)
    assert friday.q("stats")["estimate_ratio"] == 2.0  # twice as long as Friday thought
    five = friday.c("add", title="Stats: chapter 5", preset="Reading", due=soon(3))["item"]
    g5 = friday.q("item", id=five["id"])["item"]["guess_min"]
    assert g5
    friday.c("done", id=five["id"], actual_min=g5)
    after = friday.q("stats")
    assert after["estimate_ratio"] == round((60 + g5) / (30 + g5), 2)  # summed, not averaged
    assert (after["done_this_week"], after["hours_this_week"]) == (5, round((90 + 60 + g5) / 60, 1))


def test_stats_count_what_you_finish_this_week_and_the_hours_it_took(friday: Friday) -> None:
    before = friday.q("stats")
    task = friday.c("add", title="Stats: lab report", duration_min=60, due=soon(3))["item"]
    friday.c("done", id=task["id"], actual_min=90)
    after = friday.q("stats")
    assert after["done_this_week"] == before["done_this_week"] + 1
    assert after["hours_this_week"] == round(before["hours_this_week"] + 1.5, 1)
    friday.c("reopen", id=task["id"])  # opened again: not finished after all
    again = friday.q("stats")
    assert (again["done_this_week"], again["hours_this_week"]) == (before["done_this_week"], before["hours_this_week"])


def test_stats_hours_follow_the_time_logged_when_none_is_said(friday: Friday) -> None:
    before = friday.q("stats")
    task = friday.c("add", title="Stats: reading", duration_min=60, due=soon(3))["item"]
    start = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0) - timedelta(hours=2)
    friday.c("log", id=task["id"], start=local(start), end=local(start + timedelta(minutes=48)))
    friday.c("done", id=task["id"])
    after = friday.q("stats")
    assert after["done_this_week"] == before["done_this_week"] + 1
    assert after["hours_this_week"] == round(before["hours_this_week"] + 0.8, 1)


def test_stats_count_the_late_work_in_the_plan(friday: Friday) -> None:
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    due = local(now + timedelta(hours=2))
    friday.c("add", title="Stats: busy", when="fixed", start=local(now), end=due)
    item = friday.c("add", title="Stats: due too soon", duration_min=150, firmness="hard", due=due)["item"]
    friday.c("replan")
    friday.until(lambda: item["id"] in {i["item_id"] for i in friday.q("status")["late_items"]}, timeout=180)
    late = friday.q("stats")["late_items"]
    assert late >= 1
    assert late == len(friday.q("status")["late"])  # the same count the plan's late list has


# ---- log_list --------------------------------------------------------------------------------------------------------


def test_the_log_lists_each_change_newest_first_with_who_made_it_and_what_was_asked(friday: Friday) -> None:
    first, made = run(friday, "add", title="Log: read chapter 2", duration_min=60, due=soon(3))
    second, _ = run(friday, "edit", id=made["item"]["id"], duration_min=90)
    log = friday.q("log_list", limit=5)
    assert [e["id"] for e in log[:2]] == [second, first]
    newest = log[0]
    assert (newest["command"], newest["actor"], newest["undone_by"]) == ("edit", "you", None)
    assert newest["input"] == {"id": made["item"]["id"], "duration_min": 90}
    assert log[1]["command"] == "add" and log[1]["input"]["title"] == "Log: read chapter 2"
    assert newest["at"][:10] == local(datetime.now(ZoneInfo(TZ)))[:10]  # when, on your clock
    ids = [e["id"] for e in log]
    assert ids == sorted(ids, reverse=True)


def test_queries_arent_changes_and_arent_logged(friday: Friday) -> None:
    before = friday.q("log_list", limit=1)[0]["id"]
    friday.q("items")
    friday.q("status")
    friday.q("stats")
    assert friday.q("log_list", limit=1)[0]["id"] == before


def test_the_log_keeps_to_its_limit(friday: Friday) -> None:
    for n in range(4):
        friday.c("add", title=f"Log: errand {n}", duration_min=15, due=soon(2))
    assert len(friday.q("log_list", limit=3)) == 3
    assert [e["input"]["title"] for e in friday.q("log_list", limit=2)] == ["Log: errand 3", "Log: errand 2"]
    assert len(friday.q("log_list")) == 20  # twenty unless asked: there are more than that now
    friday.c("add", title="Log: padding", duration_min=15, due=soon(2))
    assert len(friday.q("log_list", limit=50)) > 6


def test_one_items_history_names_only_what_was_done_to_it(friday: Friday) -> None:
    # a block's History (plan/Elsewhere.tsx): its add, by the id in the result, and every command naming it
    _, a = run(friday, "add", title="Log: essay outline", duration_min=45, due=soon(4))
    _, b = run(friday, "add", title="Log: essay draft", duration_min=120, due=soon(5))
    a_id, b_id = a["item"]["id"], b["item"]["id"]
    friday.c("edit", id=a_id, notes="three parts")
    friday.c("depend", item_id=b_id, depends_on_id=a_id)
    friday.c("edit", id=b_id, notes="after the outline")
    friday.c("done", id=a_id)
    history = friday.q("log_list", item_id=a_id)
    assert [e["command"] for e in history] == ["done", "depend", "edit", "add"]  # depend names it as depends_on_id
    of_b = friday.q("log_list", item_id=b_id)
    assert [e["command"] for e in of_b] == ["edit", "depend", "add"]
    assert friday.q("log_list", item_id=999_999) == []


def test_an_undone_change_says_what_undid_it_and_an_undo_undone_clears_it(friday: Friday) -> None:
    added, made = run(friday, "add", title="Log: something to undo", duration_min=30, due=soon(2))
    undo, _ = run(friday, "undo", command_id=added)
    entry = next(e for e in friday.q("log_list", limit=5) if e["id"] == added)
    assert entry["undone_by"] == undo
    assert friday.http.get("/api/q/item", params={"id": made["item"]["id"]}).status_code == 422  # gone
    redo, _ = run(friday, "undo", command_id=undo)
    log = {e["id"]: e for e in friday.q("log_list", limit=5)}
    assert log[added]["undone_by"] is None and log[undo]["undone_by"] == redo
    assert friday.q("item", id=made["item"]["id"])["item"]["title"] == "Log: something to undo"


def test_a_limit_that_isnt_a_number_is_refused(friday: Friday) -> None:
    answer = friday.http.get("/api/q/log_list", params={"limit": "lots"})
    assert answer.status_code == 422 and "limit" in answer.text
