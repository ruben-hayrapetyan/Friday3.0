"""The plan on the calendar (tests/features.toml: plan_view: plan, events, fits, paces), the whole pipeline (24 Nov,
the user: "go through every single functionality of the app and build an extensive test suite"): a real
`fridayd serve` on the real clock, work and events added over HTTP, the worker's plan read back as the week, the
day, the event search, "what fits now" and the pace bar read it. The tests run in order on one server."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import Friday, local, zone_for_hour

# about noon now (24 Nov): what fits now is what fits while you're awake (at 3 or 4am, asleep until 7:30, nothing does),
# the soonest due fits first when the plan does it first (just before bedtime the plan starts the essay first
# tomorrow), and a pace for three days counts from Friday's day, which before 4am is still yesterday
TZ = zone_for_hour(12)
NOW = datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)
TOMORROW = (NOW + timedelta(days=1)).replace(hour=0, minute=0)
ESSAY_DUE = local(TOMORROW + timedelta(days=4, hours=17))
LAB_DUE = local(TOMORROW + timedelta(days=2, hours=17))


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("plan-view"))
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"timezone": TZ})
    yield server
    server.stop()


def planned(friday: Friday) -> dict[str, Any]:
    """The plan once the worker has planned every change sent so far."""

    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up)
    return friday.q("plan")


def minutes(block: dict[str, Any]) -> int:
    start, end = (datetime.fromisoformat(block[k]) for k in ("start", "end"))
    return int((end - start).total_seconds() // 60)


@pytest.fixture(scope="module")
def world(friday: Friday) -> dict[str, int]:
    essay = friday.c("add", title="Essay", duration_min=240, due=ESSAY_DUE)["item"]["id"]
    lab = friday.c("add", title="Lab report", duration_min=90, due=LAB_DUE)["item"]["id"]
    start = TOMORROW + timedelta(hours=10)
    lecture = friday.c("add", title="Chem Lecture", when="fixed", start=local(start),
                       end=local(start + timedelta(hours=1)))["item"]["id"]  # fmt: skip
    planned(friday)
    return {"essay": essay, "lab": lab, "lecture": lecture}


def test_1_a_new_friday_plans_nothing(friday: Friday) -> None:
    plan = planned(friday)
    assert plan["blocks"] == [] and plan["fixed"] == [] and plan["day_hours"] == {}


def test_2_the_plan_gives_each_task_its_length_before_its_due(friday: Friday, world: dict[str, int]) -> None:
    plan = friday.q("plan")
    assert plan["plan_id"] is not None and plan["provisional"] is False
    mine = {world["essay"]: (240, ESSAY_DUE), world["lab"]: (90, LAB_DUE)}
    for item, (length, due) in mine.items():
        blocks = [b for b in plan["blocks"] if b["item_id"] == item]
        assert sum(minutes(b) for b in blocks) == length
        assert all(b["end"] <= due and b["start"] >= local(NOW - timedelta(minutes=15)) for b in blocks)
        assert all(b["key"] == f"T{item}@{b['start']}" and not b["fixed"] for b in blocks)
    assert {b["item_id"] for b in plan["blocks"]} == set(mine)


def test_3_the_days_hours_add_up_the_blocks(friday: Friday, world: dict[str, int]) -> None:
    plan = friday.q("plan")
    by_day: dict[str, float] = {}
    for b in plan["blocks"]:  # none of them over midnight here: a block counts on its start's day
        by_day[b["start"][:10]] = by_day.get(b["start"][:10], 0) + minutes(b) / 60
    assert plan["day_hours"] == pytest.approx(by_day)
    assert sum(plan["day_hours"].values()) == pytest.approx((240 + 90) / 60)


def test_4_events_are_drawn_and_no_work_goes_over_them(friday: Friday, world: dict[str, int]) -> None:
    plan = friday.q("plan")
    [lecture] = [f for f in plan["fixed"] if f["id"] == world["lecture"]]
    assert lecture["title"] == "Chem Lecture" and lecture["start"] == local(TOMORROW + timedelta(hours=10))
    assert not [b for b in plan["blocks"] if b["start"] < lecture["end"] and b["end"] > lecture["start"]]
    blocks = sorted(plan["blocks"], key=lambda b: b["start"])
    assert all(a["end"] <= b["start"] for a, b in zip(blocks, blocks[1:], strict=False))  # nothing double-booked


def test_5_a_task_shows_the_same_sessions_as_the_plan(friday: Friday, world: dict[str, int]) -> None:
    plan = friday.q("plan")
    for item in (world["essay"], world["lab"]):
        detail = friday.q("item", id=item)["blocks"]
        assert sorted((b["start"], b["end"]) for b in detail if b["end"] > local(NOW)) == sorted(
            (b["start"], b["end"]) for b in plan["blocks"] if b["item_id"] == item
        )


def test_6_a_range_gives_only_what_overlaps_it(friday: Friday, world: dict[str, int]) -> None:
    lo, hi = TOMORROW, TOMORROW + timedelta(days=1)
    day = friday.q("plan", start=local(lo), end=local(hi))
    assert [f["id"] for f in day["fixed"]] == [world["lecture"]]
    assert all(b["start"] < local(hi) and b["end"] > local(lo) for b in day["blocks"])
    every = friday.q("plan")["blocks"]
    assert len(day["blocks"]) == len([b for b in every if b["start"] < local(hi) and b["end"] > local(lo)])
    later = friday.q("plan", start=local(TOMORROW + timedelta(days=40)), end=local(TOMORROW + timedelta(days=41)))
    assert later["blocks"] == [] and later["fixed"] == [] and later["day_hours"] == {}


def test_7_a_range_it_cant_read_is_said_on_its_field(friday: Friday) -> None:
    answer = friday.http.get("/api/q/plan", params={"start": "nope"})
    assert answer.status_code == 422
    said = "start: 'nope' is not a time like 2026-10-20T14:00 or tue 14:00"
    assert answer.json() == {"field": "start", "message": said}
    answer = friday.http.get("/api/q/plan", params={"end": "tomorrowish"})
    assert answer.status_code == 422 and answer.json()["field"] == "end"


def test_8_what_fits_a_gap_is_cut_to_the_gap(friday: Friday, world: dict[str, int]) -> None:
    hour = friday.q("fits", minutes=60)
    assert {f["item_id"] for f in hour} == {world["essay"], world["lab"]}
    assert all(f["minutes"] == 60 and f["slack_hours"] > 0 for f in hour)
    titles = {f["item_id"]: f["title"] for f in hour}
    assert titles == {world["essay"]: "Essay", world["lab"]: "Lab report"}
    whole = {f["item_id"]: f["minutes"] for f in friday.q("fits", minutes=600)}
    assert whole == {world["essay"]: 240, world["lab"]: 90}  # never more than what's left of it


def test_9_a_gap_too_short_for_a_sitting_fits_nothing(friday: Friday, world: dict[str, int]) -> None:
    assert friday.q("fits", minutes=15) == []
    answer = friday.http.get("/api/q/fits", params={"minutes": "abc"})
    assert answer.status_code == 422 and answer.json()["detail"][0]["loc"] == ["query", "minutes"]


def test_10_the_soonest_due_fits_first(friday: Friday, world: dict[str, int]) -> None:
    found = friday.q("fits", minutes=60)
    assert found[0]["item_id"] == world["lab"]  # due two days before the essay
    assert found[0]["slack_hours"] < found[1]["slack_hours"]


def test_11_events_are_found_by_their_title_in_any_case_one_per_repeat(friday: Friday, world: dict[str, int]) -> None:
    friday.c("repeat", id=world["lecture"], every="week")
    found = friday.q("events", text="CHEM")
    assert [(e["title"], e["start"]) for e in found] == [("Chem Lecture", local(TOMORROW + timedelta(hours=10)))]
    assert found[0]["id"] == world["lecture"]  # the next time, not one of its later weeks
    assert friday.q("events", text="lect") == found
    assert friday.q("events", text="   ") == [] and friday.q("events", text="physics") == []


def test_12_events_soonest_first_then_the_latest_gone_and_never_a_dropped_one(friday: Friday) -> None:
    def event(title: str, start: datetime) -> int:
        return friday.c("add", title=title, when="fixed", start=local(start), end=local(start + timedelta(hours=1)))[
            "item"
        ]["id"]

    gone = event("Office hours", NOW - timedelta(days=2))
    soon = event("Office hours", TOMORROW + timedelta(days=3, hours=15))
    sooner = event("Office hours", TOMORROW + timedelta(days=1, hours=15))
    assert [e["id"] for e in friday.q("events", text="office")] == [sooner, soon, gone]
    assert [e["id"] for e in friday.q("events", text="office", limit=2)] == [sooner, soon]
    assert [e["id"] for e in friday.q("events", text="office", limit=0)] == [sooner]  # at least one
    friday.c("drop", id=sooner)
    assert [e["id"] for e in friday.q("events", text="office")] == [soon, gone]


def test_13_a_finished_task_leaves_the_plan_and_what_fits_at_once(friday: Friday, world: dict[str, int]) -> None:
    friday.c("done", id=world["lab"])
    plan = friday.q("plan")  # before the replan lands
    assert world["lab"] not in {b["item_id"] for b in plan["blocks"]}
    assert world["lab"] not in {f["item_id"] for f in friday.q("fits", minutes=60)}
    assert world["essay"] in {b["item_id"] for b in planned(friday)["blocks"]}


def test_14_paces_say_the_default_and_whats_in_effect(friday: Friday) -> None:
    paces = friday.q("paces")
    assert paces["default"] == "Normal" and paces["now_label"] == "Normal" and paces["period_end"] is None
    assert set(paces["paces"]) == {"Normal", "Easy", "Push"}
    assert paces["now_dials"] == paces["paces"]["Normal"]


def test_15_a_pace_for_a_while_shows_until_when(friday: Friday) -> None:
    out = friday.c("pace", name="easy", for_days=3)
    end = (NOW.date() + timedelta(days=2)).isoformat()  # today and two more
    assert out["label"] == "Easy" and out["end_date"] == end
    paces = friday.q("paces")
    assert (paces["now_label"], paces["period_end"]) == ("Easy", end)
    assert paces["now_dials"] == paces["paces"]["Easy"]


def test_16_dials_set_by_hand_are_custom_until_changed(friday: Friday) -> None:
    friday.c("pace", capacity=0.8)
    paces = friday.q("paces")
    assert paces["now_label"] == "Custom" and paces["now_dials"]["capacity"] == 0.8
    assert paces["period_end"] is None


def test_17_a_saved_pace_is_listed_and_can_be_used(friday: Friday) -> None:
    friday.c("pace_save", name="Exam week", capacity=1.3, rest=0.5)
    paces = friday.q("paces")
    assert paces["paces"]["Exam week"]["capacity"] == 1.3 and paces["paces"]["Exam week"]["rest"] == 0.5
    friday.c("pace", name="Exam week")
    assert friday.q("paces")["now_label"] == "Exam week"
    friday.c("pace", name="Normal")
    assert friday.q("paces")["now_label"] == "Normal"


def test_18_a_pace_friday_doesnt_have_is_refused(friday: Friday) -> None:
    answer = friday.http.post("/api/c/pace", json={"name": "Turbo"})
    assert answer.status_code == 422
    said = "name: no pace called Turbo; saved: Normal, Easy, Push, Exam week"
    assert answer.json() == {"field": "name", "message": said}
    assert friday.q("paces")["now_label"] == "Normal"
