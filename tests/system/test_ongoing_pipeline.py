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


# Changing one (`ongoing_set`, its card's settings on the Ongoing shelf), sent over HTTP as the card sends it.


def set_refused(friday: Friday, **body: object) -> dict:
    answer = friday.http.post("/api/c/ongoing_set", json=body)
    assert answer.status_code == 422, answer.text
    return answer.json()


def test_its_name_tag_hours_and_priority_change_on_the_shelf_its_week_and_the_plan(friday: Friday) -> None:
    made = friday.c("ongoing_add", title="Violin", hours_per_week=2)
    week = shelf(friday)["Violin"]["week"]["item_id"]
    out = friday.c("ongoing_set", id=made["id"], title="  Viola  ", area="Music", hours_per_week=4, priority=5)
    assert out["id"] == made["id"]
    now = shelf(friday)
    assert "Violin" not in now and now["Viola"]["area"] == "Music"
    assert (now["Viola"]["hours_per_week"], now["Viola"]["priority"]) == (4, 5)
    assert now["Viola"]["week"]["item_id"] == week and now["Viola"]["week"]["target_min"] >= 4 * 60
    assert friday.q("item", id=week)["item"]["title"] == "Viola"  # this week's own item, renamed with it
    planned(friday)
    assert friday.until(lambda: blocks_of(friday, week))
    assert {b["title"] for b in blocks_of(friday, week)} == {"Viola"}
    friday.c("ongoing_set", id=made["id"], area="")  # no tag
    assert shelf(friday)["Viola"]["area"] is None


def test_a_rhythm_spreads_the_week_and_whenever_it_fits_takes_it_back(friday: Friday) -> None:
    made = friday.c("ongoing_add", title="Sketching", hours_per_week=3)
    friday.c("ongoing_set", id=made["id"], rhythm_days=3)
    assert shelf(friday)["Sketching"]["rhythm_days"] == 3
    week = shelf(friday)["Sketching"]["week"]["item_id"]
    planned(friday)
    days: dict[str, int] = {}
    for b in blocks_of(friday, week):  # 3 hours in three pieces: at most an hour a day
        minutes = (datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).seconds // 60
        days[b["start"][:10]] = days.get(b["start"][:10], 0) + minutes
    assert all(minutes <= 60 for minutes in days.values()), days
    friday.c("ongoing_set", id=made["id"], rhythm_days=0)
    assert shelf(friday)["Sketching"]["rhythm_days"] is None


def test_paused_until_a_day_its_week_goes_and_resumed_it_comes_back(friday: Friday) -> None:
    made = friday.c("ongoing_add", title="Pottery", hours_per_week=1)
    later = (datetime.now(ZoneInfo(TZ)) + timedelta(days=3)).date().isoformat()
    friday.c("ongoing_set", id=made["id"], paused_until=later)
    paused = shelf(friday)["Pottery"]
    assert (paused["active"], paused["paused_until"], paused["week"]) == (False, later, None)
    friday.c("ongoing_set", id=made["id"], paused_until="resume")  # until you resume it
    assert (shelf(friday)["Pottery"]["active"], shelf(friday)["Pottery"]["paused_until"]) == (False, None)
    friday.c("ongoing_set", id=made["id"], paused_until="")
    back = shelf(friday)["Pottery"]
    assert back["active"] is True and back["week"] is not None
    planned(friday)
    assert friday.until(lambda: blocks_of(friday, back["week"]["item_id"]))


def test_a_weekly_goal_made_as_a_repeat_becomes_ongoing_once_a_setting_changes(friday: Friday) -> None:
    goal = friday.c("series_add", title="French", preset="Goal", amount="target", target_min=120, every="week")
    assert shelf(friday)["French"]["as_before"] is True
    friday.c("ongoing_set", id=goal["id"], priority=4)
    assert shelf(friday)["French"]["as_before"] is False and shelf(friday)["French"]["priority"] == 4


def test_what_isnt_so_is_refused_and_nothing_changes(friday: Friday) -> None:
    made = friday.c("ongoing_add", title="Knitting", hours_per_week=1)
    before = shelf(friday)["Knitting"]
    assert set_refused(friday, id=made["id"], title="   ")["message"] == "title: an ongoing project needs a name"
    assert set_refused(friday, id=made["id"], paused_until="soon")["message"] == "paused_until: a date like 2026-11-20"
    assert set_refused(friday, id=made["id"], paused_until="2020-01-01")["message"] == "paused_until: a day after today"
    run = friday.c("series_add", title="Swim", every="tue", duration_min=30)
    assert set_refused(friday, id=run["id"], priority=2)["message"] == "id: that repeat isn't an ongoing project"
    assert set_refused(friday, id=999_999, priority=2)["field"] == "id"
    for bad in ({"hours_per_week": 0}, {"hours_per_week": 61}, {"priority": 6}, {"rhythm_days": 8}, {"carry": 2}):
        answer = friday.http.post("/api/c/ongoing_set", json={"id": made["id"], **bad})
        assert answer.status_code == 422, bad
    assert shelf(friday)["Knitting"] == before
