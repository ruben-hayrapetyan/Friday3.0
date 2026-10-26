"""Tracking your meals: off until you turn it on (like sleep); eating, done, logged after the fact, skipped, put right
or taken back, with the day's routine of the meal ticked off and opened again; what's offered when; the plan holding
your meal while you eat; and what's learned."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_local, to_utc
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    return new_app(tmp_path)


def on(app: App) -> None:
    app.do("settings_set", key="meal_tracking", value={"on": True})


def lunch_routine(app: App) -> None:
    """Lunch every day between 11:30am and 2:30pm, 30 minutes (the day starts at 4am)."""
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=15, ideal_min=30, max_min=30)  # fmt: skip


def todays_lunch(app: App) -> dict:
    (row,) = [r for r in app.table("items") if r["title"] == "Lunch" and r["occurrence_date"] == "2026-10-19"]
    return row


def at(app: App, local: str) -> None:
    """Move the clock to a time on Monday."""
    app.now_utc = to_utc(parse_local(f"2026-10-19T{local}"), TZ)


def test_it_is_off_until_you_turn_it_on(app: App) -> None:
    assert app.do("meals") == app.do("meals") | {"on": False, "days": [], "eating": None, "next": None}
    with pytest.raises(FieldError, match="meal tracking is off"):
        app.do("meal_start")


def test_breakfast_is_offered_in_the_morning_with_no_routine_and_lunch_in_its_window(app: App) -> None:
    on(app)
    lunch_routine(app)
    assert app.do("meals")["next"] == "breakfast"  # 9am: no breakfast routine, so 6 to 10:30am
    at(app, "11:00")
    assert app.do("meals")["next"] is None  # breakfast's hours are over and lunch's window hasn't opened
    at(app, "12:10")
    assert app.do("meals")["next"] == "lunch"


def test_eating_then_done_ticks_off_the_days_routine(app: App) -> None:
    on(app)
    lunch_routine(app)
    at(app, "12:10")
    assert app.do("meal_start")["message"] == "Eating lunch since 12:10pm"
    out = app.do("meals")
    assert (out["eating"]["kind"], out["next"]) == ("lunch", None)
    assert todays_lunch(app)["status"] == "todo"  # still eating
    at(app, "12:35")
    assert app.do("meal_end")["message"] == "Lunch: 25 min"
    assert todays_lunch(app)["status"] == "done"
    out = app.do("meals")
    assert out["eating"] is None and out["next"] is None
    (day,) = out["days"]
    assert day["date"] == "2026-10-19" and day["meals"][0] | {"minutes": 25} == day["meals"][0]


def test_a_meal_at_another_hour_is_a_snack_and_a_new_one_finishes_the_last(app: App) -> None:
    on(app)
    at(app, "16:00")
    assert app.do("meal_start")["message"] == "Eating snack since 4pm"
    at(app, "18:00")
    assert app.do("meal_start")["message"] == "Eating dinner since 6pm"  # no dinner routine: 5 to 9pm
    meals = app.do("meals")["days"][0]["meals"]
    assert [(m["kind"], m["minutes"]) for m in meals] == [("snack", 120), ("dinner", None)]
    with pytest.raises(FieldError, match="you're eating dinner since then"):
        app.do("meal_start", at="2026-10-19T17:30")


def test_a_skip_skips_the_routine_and_taking_it_back_opens_it(app: App) -> None:
    on(app)
    lunch_routine(app)
    app.do("meal_skip", kind="lunch")
    assert todays_lunch(app)["status"] == "skipped"
    with pytest.raises(FieldError, match="already recorded"):
        app.do("meal_skip", kind="lunch")
    assert app.do("meals")["next"] != "lunch"
    (meal,) = app.do("meals")["days"][0]["meals"]
    app.do("meal_remove", id=meal["id"])
    assert todays_lunch(app)["status"] == "todo"
    assert app.do("meals")["days"] == []


def test_a_meal_logged_after_the_fact_counts_and_can_be_put_right(app: App) -> None:
    on(app)
    app.do("meal_log", kind="breakfast", start="2026-10-19T07:40", end="2026-10-19T08:00")
    (meal,) = app.do("meals")["days"][0]["meals"]
    assert (meal["kind"], meal["minutes"]) == ("breakfast", 20)
    app.do("meal_edit", id=meal["id"], start="2026-10-19T07:30")
    assert app.do("meals")["days"][0]["meals"][0]["minutes"] == 30
    assert app.do("meals")["next"] is None  # breakfast is recorded
    with pytest.raises(FieldError, match="ends after it starts"):
        app.do("meal_log", kind="lunch", start="2026-10-19T08:00", end="2026-10-19T07:00")
    with pytest.raises(FieldError, match="later than now"):
        app.do("meal_log", kind="lunch", start="2026-10-19T08:00", end="2026-10-19T12:00")
    with pytest.raises(FieldError, match="hasn't come"):
        app.do("meal_skip", kind="dinner", date="2026-10-20")


def test_no_work_is_planned_while_you_eat(app: App) -> None:
    on(app)
    lunch_routine(app)
    app.do("add", text="essay due mon 6pm ~3h")
    at(app, "12:00")
    app.do("meal_start")
    replan(app.conn, app.now_utc)
    blocks = app.do("plan")["blocks"]
    lunch = next(b for b in blocks if b["title"] == "Lunch")
    assert lunch["start"] == "2026-10-19T12:00"
    work = [b for b in blocks if b["title"] != "Lunch" and b["start"].startswith("2026-10-19")]
    assert all(b["start"] >= lunch["end"] or b["end"] <= lunch["start"] for b in work)


def test_lunches_taken_longer_offer_a_longer_routine(app: App) -> None:
    on(app)
    lunch_routine(app)
    for back in range(1, 8):  # last week: five weekdays and a weekend
        day = date(2026, 10, 19) - timedelta(days=back)
        app.do("meal_log", kind="lunch", start=f"{day}T12:00", end=f"{day}T12:45")
    out = app.do("meals")
    (weekdays,) = [x for x in out["learned"] if x["kind"] == "lunch" and x["group"] == "weekdays"]
    assert (weekdays["usual_start"], weekdays["usual_min"], weekdays["skip_share"]) == ("12:00", 45, 0)
    assert out["changes"] == [{"kind": "lunch", "planned_min": 30, "usual_min": 45}]
    assert "planned at 45 min" in app.do("meal_use_length", kind="lunch")["message"]
    assert todays_lunch(app)["ideal_units"] == 3
    assert app.do("meals")["changes"] == []
    with pytest.raises(FieldError, match="no dinner routine"):
        app.do("meal_use_length", kind="dinner")
