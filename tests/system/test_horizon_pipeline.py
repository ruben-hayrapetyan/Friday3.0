"""The Projects page's horizon (tests/features.toml: horizon), the whole pipeline: a real `fridayd serve` on the real
clock, its worker planning each change. The load ahead (`load`) read week by week against the plan and the work added;
a project's step made "any time" (`step_any_time`) and back, each read back through `projects`, the plan and what's
late. The next hours are kept awake whatever the time (sleep starts 14 hours from now)."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import TZ, Friday
from tests.system.test_decisions_pipeline import at, awake, planned


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("horizon"))
    awake(server)
    planned(server)
    yield server
    server.stop()


def refused(friday: Friday, verb: str, query: bool = False, **given: object) -> dict:
    answer = friday.http.get(f"/api/q/{verb}", params=given) if query else friday.http.post(f"/api/c/{verb}",
                                                                                            json=given)  # fmt: skip
    assert answer.status_code == 422, answer.text
    return answer.json()


def total(weeks: list[dict]) -> float:
    return round(sum(w["hours"] for w in weeks), 1)


def test_load_is_weeks_from_this_one_each_starting_on_your_week_s_first_day(friday: Friday) -> None:
    weeks = friday.q("load")
    starts = [date.fromisoformat(w["start"]) for w in weeks]
    assert 12 <= len(weeks) <= 13 and all(d.weekday() == 0 for d in starts)  # weeks start on Monday here
    assert all(b - a == timedelta(days=7) for a, b in zip(starts, starts[1:], strict=False))
    today = (datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date()  # the planning day starts at 4am
    assert starts[0] <= today < starts[0] + timedelta(days=7)
    assert all(w["capacity"] > 0 for w in weeks)
    assert weeks[0]["forecast"] is False and weeks[-1]["forecast"] is True  # past the 14-day horizon: forecast


def test_work_added_shows_as_hours_in_the_weeks_and_its_due_in_its_week(friday: Friday) -> None:
    before = total(friday.q("load"))
    due = at(60 * 24 * 9)
    report = friday.c("add", title="grant report", duration_min=360, firmness="hard", due=due)["item"]["id"]
    friday.c("add", title="tidy notes", duration_min=60, firmness="soft", due=at(60 * 24 * 9))
    planned(friday)

    def grown() -> list[dict] | None:
        weeks = friday.q("load")
        return weeks if total(weeks) >= before + 6.9 else None

    weeks = friday.until(grown)
    assert total(weeks) == pytest.approx(before + 7, abs=0.3)
    marked = [(w["start"], d) for w in weeks for d in w["due"]]
    (week, marker) = [(s, d) for s, d in marked if d["item_id"] == report][0]
    assert marker == {"item_id": report, "title": "grant report", "due": due}
    assert date.fromisoformat(week) <= date.fromisoformat(due[:10]) < date.fromisoformat(week) + timedelta(days=7)
    assert "tidy notes" not in {d["title"] for _, d in marked}  # only hard dues are marked


def test_the_hours_in_this_week_are_the_plan_s_blocks_from_now(friday: Friday) -> None:
    weeks = friday.q("load")
    first = date.fromisoformat(weeks[0]["start"])
    end = first + timedelta(days=7)
    blocks = friday.q("plan", start=at(0), end=f"{end}T04:00")["blocks"]
    hours = sum((datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).total_seconds() for b in blocks)
    assert weeks[0]["hours"] == pytest.approx(hours / 3600, abs=0.6)


def test_load_takes_one_week_to_a_year_and_refuses_more_or_none(friday: Friday) -> None:
    assert 1 <= len(friday.q("load", weeks=1)) <= 2
    assert refused(friday, "load", query=True, weeks=0)["detail"][0]["loc"] == ["query", "weeks"]
    assert refused(friday, "load", query=True, weeks=53)["detail"][0]["loc"] == ["query", "weeks"]


@pytest.fixture(scope="module")
def paper(friday: Friday) -> dict[str, int]:
    """A paper whose outline can't start for three days while its draft is due in two: waiting for the outline, as a
    project's steps do, the draft can't be on time."""
    project = friday.c("template_apply", template="Essay", title="Seminar paper", hours=8, due=at(60 * 24 * 10))["item"]
    steps = {i["title"]: i["id"] for i in friday.q("items") if i["parent_id"] == project["id"]}
    friday.c("edit", id=steps["Outline"], release=at(60 * 24 * 3), due=at(60 * 24 * 10))
    friday.c("edit", id=steps["Draft"], due=at(60 * 24 * 2), firmness="hard")
    planned(friday)
    return steps | {"project": project["id"]}


def late_or_unplanned(friday: Friday) -> set[int]:
    status = friday.q("status")
    return {i["item_id"] for i in status["late_items"]} | {i["item_id"] for i in status["slipping"]}


def blocks_of(friday: Friday, item_id: int) -> list[dict]:
    return [b for b in friday.q("plan", start=at(-60), end=at(60 * 24 * 14))["blocks"] if b["item_id"] == item_id]


def test_a_step_waits_for_the_one_above_it(friday: Friday, paper: dict[str, int]) -> None:
    (project,) = [p for p in friday.q("projects") if p["item"]["id"] == paper["project"]]
    assert project["any_time"] == []
    outline_start = min(b["start"] for b in blocks_of(friday, paper["Outline"]))
    assert all(b["start"] >= outline_start for b in blocks_of(friday, paper["Draft"]))
    assert all(b["start"] >= at(60 * 24 * 3) for b in blocks_of(friday, paper["Draft"]))
    assert paper["Draft"] in {i["item_id"] for i in friday.q("status")["late_items"]}  # it waits past its due


def test_a_step_made_any_time_is_planned_before_the_one_above_and_on_time(friday: Friday, paper: dict) -> None:
    said = friday.c("step_any_time", id=paper["Draft"], any_time=True)
    assert said["message"] == "Any time"
    (project,) = [p for p in friday.q("projects") if p["item"]["id"] == paper["project"]]
    assert project["any_time"] == [paper["Draft"]]
    planned(friday)
    due = friday.q("item", id=paper["Draft"])["item"]["due"]
    draft = friday.until(lambda: (b := blocks_of(friday, paper["Draft"])) and max(x["end"] for x in b) <= due and b)
    assert sum((datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).seconds for b in draft) >= (
        friday.q("item", id=paper["Draft"])["item"]["duration_min"] * 60
    )
    assert max(b["end"] for b in draft) <= min(b["start"] for b in blocks_of(friday, paper["Outline"]))
    assert paper["Draft"] not in late_or_unplanned(friday)


def test_made_to_wait_again_it_follows_the_step_above(friday: Friday, paper: dict) -> None:
    said = friday.c("step_any_time", id=paper["Draft"], any_time=False)
    assert said["message"] == "After the step above"
    (project,) = [p for p in friday.q("projects") if p["item"]["id"] == paper["project"]]
    assert project["any_time"] == []
    planned(friday)
    friday.until(lambda: all(b["start"] >= at(60 * 24 * 3) for b in blocks_of(friday, paper["Draft"])))
    assert paper["Draft"] in {i["item_id"] for i in friday.q("status")["late_items"]}


def test_only_a_project_s_step_can_be_made_any_time(friday: Friday, paper: dict) -> None:
    said = refused(friday, "step_any_time", id=paper["project"], any_time=True)
    assert said == {"field": "id", "message": "id: only a project's step waits for the one above it"}
    lone = next(i["id"] for i in friday.q("items") if i["title"] == "grant report")
    assert refused(friday, "step_any_time", id=lone, any_time=True)["field"] == "id"
    assert "isn't there any more" in refused(friday, "step_any_time", id=999_999, any_time=True)["message"]
    (project,) = [p for p in friday.q("projects") if p["item"]["id"] == paper["project"]]
    assert project["any_time"] == []
