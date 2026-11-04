"""The eight buttons added on 3 Nov for what Friday could do but had no way in to (the CS 2112 UI lecture's
discoverability; web/src/reachable.test.ts holds that every command has one). A real `fridayd serve` in its own folder,
each command sent over HTTP exactly as its new button sends it, and what you'd then see read back the same way."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("buttons"))
    yield server
    server.stop()


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def test_give_it_back_removes_the_shove_you_clicked_not_the_last_one(friday: Friday) -> None:
    first = friday.c("shove", range="day sat", decision="shove_anyway")["created"]
    second = friday.c("shove", range="day sun", decision="shove_anyway")["created"]
    assert first and second
    friday.c("unshove", id=first[0])  # the older one, which ⌘Z alone couldn't reach
    gone = friday.http.get("/api/q/item", params={"id": first[0]})
    assert gone.status_code == 422  # deleted, not just hidden
    assert friday.q("item", id=second[0])["item"]["event_kind"] == "shove"


def test_save_as_template_keeps_the_order_on_screen(friday: Friday) -> None:
    made = friday.c("template_apply", template="Essay", title="Seminar paper", hours=6, due="2026-12-10T17:00")
    project = made["item"]
    kids = [i["id"] for i in friday.q("items") if i["parent_id"] == project["id"]]
    friday.c("reorder", parent_id=project["id"], ids=[kids[2], kids[0], kids[1]])
    said = friday.c("template_save", name="Seminar paper", project_id=project["id"])
    assert "3 steps" in said["message"]
    steps = friday.q("settings")["templates"]["Seminar paper"]
    assert [s["title"] for s in steps] == ["Revise", "Outline", "Draft"]


def test_put_friday_s_events_on_it_says_what_to_do_first_without_a_calendar(friday: Friday) -> None:
    said = friday.c("events_to_calendar")
    assert said["message"] == "Choose where new events go first, in Settings → Calendars"


def test_merge_into_folds_one_category_into_another(friday: Friday) -> None:
    two = [{"name": "Social", "slug": "social", "color": "graphite", "pattern": "party"},
           {"name": "Campus events", "slug": "campus", "color": "graphite", "pattern": "talk"}]  # fmt: skip
    friday.c("settings_set", key="categories", value={**friday.q("settings")["categories"], "categories": two})
    friday.c("category_merge", name="Campus events", into="Social")
    after = friday.q("settings")["categories"]["categories"]
    assert [c["name"] for c in after] == ["Social"] and after[0]["pattern"] == "party|talk"


def test_a_repeat_s_tag_changes_from_its_row(friday: Friday) -> None:
    friday.c("area_add", name="Fitness")
    series = friday.c("series_add", title="Run", every="mon,wed", duration_min=30)
    sid = series["id"]
    friday.c("series_edit", id=sid, area="Fitness")
    rows = [r for r in friday.q("series_list") if r["title"] == "Run"]
    assert [(r["id"], r["area"]) for r in rows] == [(sid, "Fitness")]  # one row, retagged, not split in two
    runs = [i for i in friday.q("items") if i["title"] == "Run"]
    assert runs and all(i["area"] == "Fitness" for i in runs)


def test_log_time_counts_as_done_and_shows_on_the_task(friday: Friday) -> None:
    task = friday.c("add", title="Read chapter 4", duration_min=120, due="2026-12-01T17:00")["item"]
    yesterday = datetime.now(ZoneInfo(TZ)).replace(hour=14, minute=0, second=0, microsecond=0) - timedelta(days=1)
    friday.c("log", id=task["id"], start=local(yesterday), end=local(yesterday + timedelta(minutes=45)))
    item = friday.q("item", id=task["id"])["item"]
    assert item["done_min"] == 45 and item["remaining_min"] == 75


def test_what_changed_names_what_you_did(friday: Friday) -> None:
    friday.c("add", title="Email the TA", duration_min=15, due="2026-12-02T12:00")

    def latest() -> dict:  # the worker replans after the command: wait for the plan that followed it
        answer = friday.http.get("/api/q/changes")
        if answer.status_code == 422:  # no plan yet: the window says so (ChangesDialog)
            assert "no plan yet" in answer.json()["message"]
            return {}
        out = answer.json()
        return out if any(i.get("command") == "add" for i in out.get("inputs", [])) else {}

    out = friday.until(latest)
    assert {"added", "moved", "removed", "inputs"} <= set(out)


def test_insights_late_on_paper_reads_its_numbers(friday: Friday) -> None:
    out = friday.q("beat_plan")
    assert {"on_time", "late", "counts", "said", "asking"} <= set(out)
    assert out["on_time"] >= 0 and out["late"] >= 0
