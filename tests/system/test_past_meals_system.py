"""The meals you ate on the calendar, drawn as your Lunch is but in the past (4 Nov: "treat them as if they were regular
lunch and dinner but just in the past"), the whole system: a real `fridayd serve` with a daily Lunch routine, the Now
bar's taps over HTTP, and the two queries the calendar reads (web/src/plan/pastMeals.ts): the meal names the routine
whose pieces in the plan it takes the place of."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def friday_day() -> date:
    """Friday's day, 4am to 4am: between midnight and 4am it is still yesterday's date (5 Nov, 12:30am)."""
    return (datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date()


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("past_meals"))
    # asleep from eight hours after now, so the test never runs inside sleep, when no lunch is planned (5 Nov, 12:30am)
    now = datetime.now(ZoneInfo(TZ))
    away = {
        "bedtime": f"{(now + timedelta(hours=8)):%H:%M}",
        "wake": f"{(now + timedelta(hours=15)):%H:%M}",
        "margin_min": 60,
    }
    server.c("settings_set", key="sleep", value=dict.fromkeys(SLEEP, away))
    server.c("settings_set", key="meal_tracking", value={"on": True})
    # open all day (4am to 3:30am), so today's Lunch is still to do whenever the test runs
    server.c("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=0,
             due_offset_min=23 * 60 + 30, min_min=15, ideal_min=30, max_min=30)  # fmt: skip
    yield server
    server.stop()


def test_a_meal_eaten_names_the_routine_the_plan_holds_for_it(friday: Friday) -> None:
    today = friday_day()
    window = {"start": f"{today}T04:00", "end": f"{today + timedelta(days=1)}T04:00"}  # Friday's day
    friday.c("meal_start", kind="lunch")
    eating = friday.q("meals")["eating"]
    assert eating["kind"] == "lunch" and eating["item_id"] is not None

    def lunch_in_plan() -> list[dict] | None:
        plan = friday.q("plan", **window)
        found = [b for b in plan["blocks"] + (plan.get("sessions") or []) if b["title"] == "Lunch"]
        return found or None

    # the plan holds the routine at now while you eat: those pieces are the ones the meal takes the place of
    assert {b["item_id"] for b in friday.until(lunch_in_plan)} == {eating["item_id"]}
    # the day's list carries it too (done eating the same minute is refused, so it's read while you eat)
    (day,) = [d for d in friday.q("meals")["days"] if d["date"] == str(today)]
    (lunch,) = [m for m in day["meals"] if m["kind"] == "lunch"]
    assert lunch["item_id"] == eating["item_id"] and lunch["start"] is not None and not lunch["skipped"]


def test_a_skipped_meal_has_no_time_so_nothing_is_drawn(friday: Friday) -> None:
    friday.c("meal_skip", kind="breakfast")
    today = str(friday_day())
    (day,) = [d for d in friday.q("meals")["days"] if d["date"] == today]
    (breakfast,) = [m for m in day["meals"] if m["kind"] == "breakfast"]
    assert breakfast["skipped"] and breakfast["start"] is None
