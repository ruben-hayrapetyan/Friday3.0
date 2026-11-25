"""Meals, the whole pipeline (tests/features.toml: eating; 24 Nov, the user: "build an extensive test suite ... i want
to make sure that absolutely nothing can break without our tests flagging it"): a real `fridayd serve` with meal
tracking on, a Lunch routine open all day and a Dinner routine from 5 to 7pm; every meal command sent over HTTP as Sleep
& meals and the Now bar send it, and what it did read back through `meals`, the items, the repeats and the plan.

The tests run in order and build on each other (one server): taps today first, then eight days of meals logged in the
past, from which Friday learns the lengths and times it then offers, and each offer taken."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from friday.core.time import clock_time
from tests.system.test_beat_plan_system import SLEEP, Friday


def midday_zone() -> str:
    """A zone where it's about noon now: the tests set up today's 5-7pm Dinner, which a repeat made after 7pm rightly
    doesn't backfill (24 Nov: run in the evening, the tests found no Dinner today and failed)."""
    hours = 12 - datetime.now(ZoneInfo("UTC")).hour  # UTC-11 to UTC+12
    return "UTC" if hours == 0 else f"Etc/GMT{'-' if hours > 0 else '+'}{abs(hours)}"  # Etc/ signs are reversed


TZ = midday_zone()

DAY_START = "04:00"
DINNER = (17 * 60, 19 * 60)  # the Dinner routine's window, local minutes
PAST = range(2, 10)  # the days before today the learned meals are logged on: eight, so both weekdays and weekends count


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("eating"))
    now = datetime.now(ZoneInfo(TZ))
    away = {"bedtime": f"{now + timedelta(hours=8):%H:%M}", "wake": f"{now + timedelta(hours=15):%H:%M}",
            "margin_min": 60}  # fmt: skip
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, away))  # never asleep while the tests run
    server.c("settings_set", key="meal_tracking", value={"on": True, "min_days": 2})
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"day_start": DAY_START, "timezone": TZ})
    server.c("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=0,
             due_offset_min=24 * 60 - 1, min_min=15, ideal_min=30, max_min=30)  # fmt: skip
    server.c("series_add", title="Dinner", preset="Routine", every="day", release_offset_min=DINNER[0] - 4 * 60,
             due_offset_min=DINNER[1] - 4 * 60, min_min=15, ideal_min=30, max_min=30)  # fmt: skip
    yield server
    server.stop()


def now() -> datetime:
    return datetime.now(ZoneInfo(TZ)).replace(second=0, microsecond=0)


def local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def ago(minutes: int) -> str:
    return local(now() - timedelta(minutes=minutes))


def today() -> date:
    """Friday's day: from 4am."""
    return (datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date()


def at(days_back: int, clock: str) -> str:
    return f"{today() - timedelta(days=days_back)}T{clock}"


def said(moment: str) -> str:
    return clock_time(moment[11:16])


def refused(friday: Friday, verb: str, **body: Any) -> str:
    """A command Friday turns down: the 422 and the words it gives."""
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    said = answer.json()
    if "message" in said:  # Friday's own: "field: words"
        return said["message"]
    first = said["detail"][0]  # the request's shape, checked before the command runs
    return f"{first['loc'][-1]}: {first['msg']}"


def routine(friday: Friday, title: str, day: date) -> dict:
    """That day's routine of that name (Lunch on Tuesday)."""
    (found,) = [i for i in friday.q("items", status="all") if i["title"] == title and i["series_id"]
                and (i["release"] or "").startswith(str(day))]  # fmt: skip
    return found


def meals_on(friday: Friday, day: date | str) -> list[dict]:
    return next((d["meals"] for d in friday.q("meals")["days"] if d["date"] == str(day)), [])


def every_meal(friday: Friday) -> dict[int, dict]:
    return {m["id"]: m for d in friday.q("meals")["days"] for m in d["meals"]}


def test_01_off_every_tap_is_refused_and_meals_say_off(friday: Friday) -> None:
    friday.c("settings_set", key="meal_tracking", value={"on": False, "min_days": 2})
    assert friday.q("meals") == {**friday.q("meals"), "on": False, "days": [], "eating": None}
    for verb, body in (("meal_start", {"kind": "lunch"}), ("meal_end", {}), ("meal_skip", {"kind": "lunch"}),
                       ("meal_log", {"kind": "lunch", "start": ago(60), "end": ago(30)})):  # fmt: skip
        assert refused(friday, verb, **body) == "kind: Meal tracking is off: turn it on in Insights → Meals"
    friday.c("settings_set", key="meal_tracking", value={"on": True, "min_days": 2})
    assert friday.q("meals")["on"] is True and friday.q("meals")["days"] == []


def test_02_eating_now_holds_the_lunch_routine_and_done_eating_ticks_it_off(friday: Friday) -> None:
    lunch = routine(friday, "Lunch", today())
    assert lunch["status"] == "todo"
    start = ago(20)
    assert friday.c("meal_start", kind="lunch", at=start)["message"] == f"Eating lunch since {said(start)}"
    eating = friday.q("meals")["eating"]
    assert (eating["kind"], eating["start"], eating["end"], eating["item_id"]) == ("lunch", start, None, lunch["id"])
    assert routine(friday, "Lunch", today())["status"] == "todo"  # held while you eat, not done yet
    assert refused(friday, "meal_start", kind="lunch", at=start) == "at: you're eating lunch since then"
    assert friday.c("meal_end", at=local(datetime.fromisoformat(start) + timedelta(minutes=20)))["message"] == (
        "Lunch: 20 min"
    )
    out = friday.q("meals")
    assert out["eating"] is None and out["again"] == "lunch"  # the Now bar offers another lunch, not a snack
    (eaten,) = [m for m in meals_on(friday, today()) if m["kind"] == "lunch"]
    assert (eaten["minutes"], eaten["skipped"], eaten["item_id"]) == (20, False, lunch["id"])
    assert routine(friday, "Lunch", today())["status"] == "done"
    assert refused(friday, "meal_end") == "at: you aren't eating"


def test_03_a_start_later_than_now_or_an_end_before_the_start_is_refused(friday: Friday) -> None:
    assert (
        refused(friday, "meal_start", kind="snack", at=local(now() + timedelta(hours=1))) == "at: that's later than now"
    )
    assert refused(friday, "meal_start", kind="pizza").startswith("kind:")  # not a meal
    friday.c("meal_start", kind="snack", at=ago(10))
    assert refused(friday, "meal_end", at=ago(30)) == "at: that's before you started"
    assert refused(friday, "meal_end", at=local(now() + timedelta(minutes=30))) == "at: that's later than now"
    assert friday.q("meals")["eating"]["kind"] == "snack"  # still eating: nothing refused was kept
    assert friday.c("meal_end", at=ago(5))["message"] == "Snack: 5 min"


def test_04_a_meal_started_while_eating_another_finishes_that_one(friday: Friday) -> None:
    base = now()
    first, second = local(base - timedelta(minutes=40)), local(base - timedelta(minutes=25))
    friday.c("meal_start", kind="snack", at=first)
    friday.c("meal_start", kind="snack", at=second)
    meals = [m for m in meals_on(friday, today()) if m["kind"] == "snack"]
    (finished,) = [m for m in meals if m["start"] == first]
    assert finished["minutes"] == 15 and finished["end"] == second
    assert friday.q("meals")["eating"]["start"] == second
    assert refused(friday, "meal_start", kind="snack", at=local(base - timedelta(minutes=50))) == (
        "at: you're eating snack since then"
    )
    assert friday.c("meal_end", at=local(base))["message"] == "Snack: 25 min"


def test_05_done_eating_tapped_hours_later_counts_the_usual_length(friday: Friday) -> None:
    start = ago(150)
    friday.c("meal_start", kind="snack", at=start)
    message = friday.c("meal_end")["message"]
    assert message == (
        "Snack: counted as your usual 30 min (Done eating came 2 h 30 min after you started); change it in "
        "Insights → Meals"
    )
    (snack,) = [m for m in meals_on(friday, today()) if m["start"] == start]
    assert snack["minutes"] == 30 and snack["end"] == local(datetime.fromisoformat(start) + timedelta(minutes=30))


def test_06_eating_now_with_no_kind_is_the_meal_whose_time_it_is(friday: Friday) -> None:
    moment = now() - timedelta(minutes=1)
    minute = moment.hour * 60 + moment.minute
    # no Breakfast routine: breakfast in its usual hours; else Lunch, open all day, comes before Dinner
    expected = "breakfast" if 6 * 60 <= minute < 10 * 60 + 30 else "lunch"
    message = friday.c("meal_start", at=local(moment))["message"]
    assert friday.q("meals")["eating"]["kind"] == expected
    assert message.startswith("Eating ")
    friday.c("meal_end")
    (meal,) = [m for m in meals_on(friday, today()) if m["start"] == local(moment)]
    meal_remove = friday.c("meal_remove", id=meal["id"])  # taken back: the next tests count lunches
    assert meal_remove["message"] == f"Removed {expected}"
    assert routine(friday, "Lunch", today())["status"] == "done"  # the first lunch still says you had it


def test_07_a_meal_logged_after_the_fact_shows_and_ticks_its_routine(friday: Friday) -> None:
    yesterday = at(1, "18:00")
    out = friday.c("meal_log", kind="dinner", start=yesterday, end=at(1, "18:40"))
    assert out["message"] == "Logged dinner, 6pm to 6:40pm"
    (dinner,) = meals_on(friday, today() - timedelta(days=1))
    assert (dinner["kind"], dinner["start"], dinner["end"], dinner["minutes"]) == ("dinner", yesterday,
                                                                                  at(1, "18:40"), 40)  # fmt: skip
    # today's: its Dinner routine is ticked off, done at the meal's end
    assert routine(friday, "Dinner", today())["status"] == "todo"
    friday.c("meal_log", kind="dinner", start=ago(90), end=ago(60))
    assert routine(friday, "Dinner", today())["status"] == "done"
    (logged,) = [m for m in meals_on(friday, today()) if m["kind"] == "dinner"]
    assert logged["item_id"] == routine(friday, "Dinner", today())["id"]


def test_08_a_logged_meal_must_end_after_it_starts_within_four_hours_and_by_now(friday: Friday) -> None:
    before = len(every_meal(friday))
    words = "end: a meal ends after it starts, within four hours"
    assert refused(friday, "meal_log", kind="lunch", start=at(1, "12:00"), end=at(1, "12:00")) == words
    assert refused(friday, "meal_log", kind="lunch", start=at(1, "12:00"), end=at(1, "11:00")) == words
    assert refused(friday, "meal_log", kind="lunch", start=at(1, "10:00"), end=at(1, "14:01")) == words
    assert refused(friday, "meal_log", kind="lunch", start=ago(10), end=local(now() + timedelta(hours=1))) == (
        "end: that's later than now"
    )
    assert len(every_meal(friday)) == before


def test_09_a_skipped_meal_is_recorded_once_and_never_for_a_day_to_come(friday: Friday) -> None:
    assert friday.c("meal_skip", kind="breakfast")["message"] == "Skipped breakfast"
    (skipped,) = [m for m in meals_on(friday, today()) if m["kind"] == "breakfast"]
    assert skipped["skipped"] and skipped["start"] is None and skipped["minutes"] is None
    assert refused(friday, "meal_skip", kind="breakfast") == "kind: breakfast is already recorded that day"
    assert refused(friday, "meal_skip", kind="dinner", date=str(today() - timedelta(days=1))) == (
        "kind: dinner is already recorded that day"  # logged in test 7
    )
    assert refused(friday, "meal_skip", kind="lunch", date=str(today() + timedelta(days=1))) == (
        "date: that day hasn't come yet"
    )
    # nothing learned of breakfast yet (one day): it can't be planned from what you do
    assert refused(friday, "meal_plan", kind="breakfast", plan=True) == (
        "plan: Friday hasn't learned when you have breakfast yet"
    )


def test_10_removing_a_meal_opens_its_routine_again_unless_another_says_you_had_it(friday: Friday) -> None:
    (dinner,) = [m for m in meals_on(friday, today()) if m["kind"] == "dinner"]
    assert friday.c("meal_remove", id=dinner["id"])["message"] == "Removed dinner"
    assert dinner["id"] not in every_meal(friday)
    assert routine(friday, "Dinner", today())["status"] == "todo"
    # skipped now: the routine is skipped with it
    assert friday.c("meal_skip", kind="dinner")["message"] == "Skipped dinner"
    assert routine(friday, "Dinner", today())["status"] == "skipped"

    # two lunches today: taking back the first leaves Lunch done (27 Oct: a duplicate removed reopened it)
    second = friday.c("meal_log", kind="lunch", start=ago(15), end=ago(12))
    assert second["message"].startswith("Logged second lunch, ")
    lunches = sorted((m for m in meals_on(friday, today()) if m["kind"] == "lunch"), key=lambda m: m["start"])
    assert [m["nth"] for m in lunches] == [1, 2]
    friday.c("meal_remove", id=lunches[0]["id"])
    assert routine(friday, "Lunch", today())["status"] == "done"
    friday.c("meal_remove", id=lunches[1]["id"])
    assert routine(friday, "Lunch", today())["status"] == "todo"
    assert refused(friday, "meal_remove", id=999_999) == "id: no meal 999999"


def test_11_a_meal_put_right_moves_its_times_and_its_day(friday: Friday) -> None:
    (dinner,) = meals_on(friday, today() - timedelta(days=1))
    out = friday.c("meal_edit", id=dinner["id"], end=at(1, "19:10"))
    assert out["message"] == "Dinner now 6pm to 7:10pm"
    assert every_meal(friday)[dinner["id"]]["minutes"] == 70
    friday.c("meal_edit", id=dinner["id"], start=at(12, "18:00"), end=at(12, "18:30"))  # the wrong day: moved
    moved = every_meal(friday)[dinner["id"]]
    assert (moved["date"], moved["minutes"]) == (str(today() - timedelta(days=12)), 30)
    assert meals_on(friday, today() - timedelta(days=1)) == []


def test_12_a_meal_edit_is_refused_for_no_meal_a_skip_or_times_that_cant_be(friday: Friday) -> None:
    (dinner,) = meals_on(friday, today() - timedelta(days=12))
    (skipped,) = [m for m in meals_on(friday, today()) if m["kind"] == "breakfast"]
    assert refused(friday, "meal_edit", id=999_999, start=at(1, "12:00")) == "id: no meal 999999"
    assert refused(friday, "meal_edit", id=skipped["id"], start=at(0, "08:00")) == "id: a skipped meal has no times"
    words = "end: a meal ends after it starts, within four hours"
    assert refused(friday, "meal_edit", id=dinner["id"], end=at(12, "17:00")) == words
    assert refused(friday, "meal_edit", id=dinner["id"], end=at(12, "23:00")) == words
    assert refused(friday, "meal_edit", id=dinner["id"], start=local(now() + timedelta(hours=1))) == (
        "start: that's later than now"
    )
    unchanged = every_meal(friday)[dinner["id"]]
    assert (unchanged["start"], unchanged["end"]) == (at(12, "18:00"), at(12, "18:30"))


@pytest.fixture(scope="module")
def learned(friday: Friday) -> dict:
    """Eight days before today: breakfast 8–8:20, lunch 12–1 (twice the Lunch planned) and dinner 8–8:30pm (after the
    Dinner routine's 5–7pm)."""
    for n in PAST:
        friday.c("meal_log", kind="breakfast", start=at(n, "08:00"), end=at(n, "08:20"))
        friday.c("meal_log", kind="lunch", start=at(n, "12:00"), end=at(n, "13:00"))
        friday.c("meal_log", kind="dinner", start=at(n, "20:00"), end=at(n, "20:30"))
    return friday.q("meals")


def test_13_friday_learns_each_meal_and_offers_what_differs_from_the_plan(friday: Friday, learned: dict) -> None:
    usual = {(x["kind"], x["group"]): x for x in learned["learned"]}
    lunch = usual[("lunch", "weekdays")]
    assert (lunch["usual_start"], lunch["usual_min"]) == ("12:00", 60)
    assert (usual[("breakfast", "weekdays")]["usual_start"], usual[("dinner", "weekdays")]["usual_start"]) == (
        "08:00",
        "20:00",
    )
    assert {c["kind"]: (c["planned_min"], c["usual_min"], c["new_min"]) for c in learned["changes"]} == {
        "lunch": (30, 60, 60)  # dinner takes the 30 planned
    }
    (dinner,) = [t for t in learned["times"] if t["kind"] == "dinner"]
    assert (dinner["start"], dinner["end"], dinner["new_start"], dinner["new_end"]) == ("17:00", "19:00", "19:15",
                                                                                     "21:15")  # fmt: skip
    (breakfast,) = learned["plans"]
    assert (breakfast["kind"], breakfast["plan"], breakfast["usual_start"]) == ("breakfast", True, "08:00")


def test_14_plan_lunch_at_the_length_you_take(friday: Friday, learned: dict) -> None:
    assert refused(friday, "meal_use_length", kind="breakfast") == "kind: there's no breakfast routine to change"
    assert (
        refused(friday, "meal_use_length", kind="dinner") == "kind: Friday hasn't learned a different length for dinner"
    )
    out = friday.c("meal_use_length", kind="lunch")
    assert out["message"] == "Lunch is planned at 60 min from today (you take about 60)"
    assert "lunch" not in {c["kind"] for c in friday.q("meals")["changes"]}
    assert (
        refused(friday, "meal_use_length", kind="lunch") == "kind: Friday hasn't learned a different length for lunch"
    )
    # the plan gives tomorrow's Lunch the hour
    tomorrow = routine(friday, "Lunch", today() + timedelta(days=1))

    def lunch_minutes() -> int | None:
        status = friday.q("status")
        if status["plan_generation"] is None or status["plan_generation"] < status["generation"]:
            return None
        window = {"start": f"{today() + timedelta(days=1)}T04:00", "end": f"{today() + timedelta(days=2)}T04:00"}
        blocks = [b for b in friday.q("plan", **window)["blocks"] if b["item_id"] == tomorrow["id"]]
        return sum((datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).seconds // 60
                   for b in blocks) or None  # fmt: skip

    assert friday.until(lunch_minutes) == 60


def test_15_plan_dinner_around_when_you_eat_it(friday: Friday, learned: dict) -> None:
    assert refused(friday, "meal_use_time", kind="snack") == "kind: Friday hasn't learned a different time for snack"
    out = friday.c("meal_use_time", kind="dinner")
    assert out["message"] == "Dinner is planned 7:15pm to 9:15pm from today"
    tomorrow = routine(friday, "Dinner", today() + timedelta(days=1))
    assert (tomorrow["release"][11:], tomorrow["due"][11:]) == ("19:15", "21:15")
    assert "dinner" not in {t["kind"] for t in friday.q("meals")["times"]}
    assert refused(friday, "meal_use_time", kind="dinner") == "kind: Friday hasn't learned a different time for dinner"


def test_16_plan_breakfast_you_have_most_days_then_stop_planning_it(friday: Friday, learned: dict) -> None:
    assert refused(friday, "meal_plan", kind="breakfast", plan=False) == "plan: there's no breakfast routine to stop"
    assert refused(friday, "meal_plan", kind="dinner", plan=True) == "plan: dinner is already planned"
    assert refused(friday, "meal_plan", kind="snack", plan=True).startswith("kind:")  # snacks aren't planned
    out = friday.c("meal_plan", kind="breakfast", plan=True)
    assert out["message"] == "Breakfast is planned around 8am, 15 min, every day"
    (series,) = [s for s in friday.q("series_list") if s["title"] == "Breakfast"]
    assert series["active"] and series["pattern"] == "Every day"
    # 45 minutes either side of 8am, for its quarter hour
    tomorrow = routine(friday, "Breakfast", today() + timedelta(days=1))
    assert (tomorrow["preset"], tomorrow["release"][11:], tomorrow["due"][11:]) == ("Routine", "07:15", "09:00")
    assert "breakfast" not in {p["kind"] for p in friday.q("meals")["plans"]}
    assert refused(friday, "meal_plan", kind="breakfast", plan=True) == "plan: breakfast is already planned"

    assert friday.c("meal_plan", kind="breakfast", plan=False)["message"] == "Breakfast is no longer planned"
    (stopped,) = [s for s in friday.q("series_list") if s["title"] == "Breakfast"]
    assert not stopped["active"] and stopped["next"] is None
    assert not [i for i in friday.q("items") if i["title"] == "Breakfast"]  # its times to come are gone
    assert refused(friday, "meal_plan", kind="breakfast", plan=False) == "plan: there's no breakfast routine to stop"
