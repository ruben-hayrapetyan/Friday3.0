"""Deleting an ongoing project (tests/features.toml: ongoing, `ongoing_delete`), the whole pipeline: a real `fridayd
serve` on the real clock, its worker planning each change, the Projects page's Ongoing shelf sent over HTTP as it
sends it, and what deleting leaves read back through the shelf, the repeats, the plan and the week's own item: its weeks
to come go, the hours you put in stay. The next hours are kept awake whatever the time (sleep starts 14 hours from
now)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday
from tests.system.test_decisions_pipeline import at, awake, planned


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("ongoing"))
    awake(server)
    yield server
    server.stop()


def shelf(friday: Friday) -> dict[str, dict]:
    return {o["title"]: o for o in friday.q("ongoing_projects")}


def blocks_of(friday: Friday, item_id: int) -> list[dict]:
    return [b for b in friday.q("plan", start=at(-60), end=at(60 * 24 * 7))["blocks"] if b["item_id"] == item_id]


def refused(friday: Friday, **body: object) -> dict:
    answer = friday.http.post("/api/c/ongoing_delete", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_deleting_one_takes_it_off_the_shelf_its_repeat_and_the_plan(friday: Friday) -> None:
    made = friday.c("ongoing_add", title="Guitar", hours_per_week=3)
    week = shelf(friday)["Guitar"]["week"]["item_id"]
    planned(friday)
    assert friday.until(lambda: blocks_of(friday, week))  # planned this week
    said = friday.c("ongoing_delete", id=made["id"])
    assert said["message"] == "Guitar deleted; the hours you put in stay in your history"
    assert "Guitar" not in shelf(friday)
    assert made["id"] not in {s["id"] for s in friday.q("series_list")}
    assert friday.http.get("/api/q/item", params={"id": week}).status_code == 422  # its week, with no time in it, went
    planned(friday)
    assert friday.until(lambda: blocks_of(friday, week) == [])


def test_a_week_with_time_in_it_is_kept_done_with_its_hours(friday: Friday) -> None:
    made = friday.c("ongoing_add", title="Piano", hours_per_week=2)
    week = shelf(friday)["Piano"]["week"]["item_id"]
    now = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
    start = max(now - timedelta(minutes=40), datetime.fromisoformat(shelf(friday)["Piano"]["week"]["start"]).replace(
        tzinfo=ZoneInfo(TZ)))  # fmt: skip
    friday.c("log", id=week, start=start.strftime("%Y-%m-%dT%H:%M"), end=(start + timedelta(minutes=30))
             .strftime("%Y-%m-%dT%H:%M"))  # fmt: skip
    assert shelf(friday)["Piano"]["week"]["done_min"] == 30
    friday.c("ongoing_delete", id=made["id"])
    kept = friday.q("item", id=week)["item"]
    assert (kept["status"], kept["done_min"]) == ("done", 30)
    assert "Piano" not in shelf(friday)
    assert made["id"] not in {s["id"] for s in friday.q("series_list")}


def test_a_weekly_goal_made_as_a_repeat_is_on_the_shelf_and_deleted_the_same_way(friday: Friday) -> None:
    goal = friday.c("series_add", title="Spanish", preset="Goal", amount="target", target_min=120, every="week")
    assert shelf(friday)["Spanish"]["as_before"] is True
    friday.c("ongoing_delete", id=goal["id"])
    assert "Spanish" not in shelf(friday)
    assert goal["id"] not in {s["id"] for s in friday.q("series_list")}


def test_a_repeat_that_isnt_an_ongoing_project_is_refused_and_kept(friday: Friday) -> None:
    run = friday.c("series_add", title="Run", every="mon,wed", duration_min=30)
    said = refused(friday, id=run["id"])
    assert said == {"field": "id", "message": "id: that repeat isn't an ongoing project"}
    assert run["id"] in {s["id"] for s in friday.q("series_list")}
    assert any(i["title"] == "Run" for i in friday.q("items"))


def test_deleting_one_leaves_the_others(friday: Friday) -> None:
    keep = friday.c("ongoing_add", title="Drawing", hours_per_week=1)
    gone = friday.c("ongoing_add", title="Chess", hours_per_week=1)
    friday.c("ongoing_delete", id=gone["id"])
    assert set(shelf(friday)) == {"Drawing"} and shelf(friday)["Drawing"]["id"] == keep["id"]
    assert shelf(friday)["Drawing"]["week"] is not None


def test_deleting_one_twice_or_one_that_never_was_is_refused(friday: Friday) -> None:
    gone = friday.c("ongoing_add", title="Poetry", hours_per_week=1)
    friday.c("ongoing_delete", id=gone["id"])
    assert refused(friday, id=gone["id"])["field"] == "id"
    assert refused(friday, id=999_999)["field"] == "id"
    answer = friday.http.post("/api/c/ongoing_delete", json={})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["body", "id"]
