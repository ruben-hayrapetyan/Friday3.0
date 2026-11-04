"""Tracking your meals: off until you turn it on (like sleep); eating, done, logged after the fact, skipped, put right
or taken back, with the day's routine of the meal ticked off and opened again; what's offered when; the plan holding
your meal while you eat; and what's learned."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.commands.eating import decide
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


def test_lunch_eaten_well_after_its_window_is_offered_a_later_window(app: App) -> None:
    on(app)
    lunch_routine(app)  # 11:30am to 2:30pm
    for back in range(1, 8):
        day = date(2026, 10, 19) - timedelta(days=back)
        app.do("meal_log", kind="lunch", start=f"{day}T13:45", end=f"{day}T14:15")
    (moved,) = app.do("meals")["times"]
    assert (moved["kind"], moved["start"], moved["end"]) == ("lunch", "11:30", "14:30")
    assert moved["new_start"] == "12:30" and moved["new_end"] == "15:30"
    assert "12:30pm to 3:30pm" in app.do("meal_use_time", kind="lunch")["message"]
    assert todays_lunch(app)["release_utc"] == "2026-10-19T16:30Z"  # 12:30pm EDT
    assert app.do("meals")["times"] == []


def breakfasts(app: App, days: range, skipped: bool = False) -> None:
    for back in days:
        day = date(2026, 10, 19) - timedelta(days=back)
        if skipped:
            app.do("meal_skip", kind="breakfast", date=day.isoformat())
        else:
            app.do("meal_log", kind="breakfast", start=f"{day}T08:00", end=f"{day}T08:15")


def test_breakfast_is_planned_once_you_have_it_most_days_and_dropped_when_you_skip_it(app: App) -> None:
    on(app)
    breakfasts(app, range(1, 8))
    (offered,) = app.do("meals")["plans"]
    assert offered == {"kind": "breakfast", "plan": True, "usual_start": "08:00", "usual_min": 15}
    assert "around 8am, 15 min" in app.do("meal_plan", kind="breakfast", plan=True)["message"]
    made = [r for r in app.table("items") if r["title"] == "Breakfast" and r["occurrence_date"] == "2026-10-19"]
    assert made and made[0]["release_utc"] == "2026-10-19T11:15Z"  # 7:15am EDT, 45 minutes before
    assert app.do("meals")["plans"] == []
    breakfasts(app, range(8, 16), skipped=True)  # 8 of 15 days skipped: neither most nor few, so it stays
    assert app.do("meals")["plans"] == []
    breakfasts(app, range(16, 21), skipped=True)  # 13 of 20
    assert [(p["kind"], p["plan"]) for p in app.do("meals")["plans"]] == [("breakfast", False)]
    app.do("meal_plan", kind="breakfast", plan=False)
    assert app.do("meals")["plans"] == []
    with pytest.raises(FieldError, match="no breakfast routine"):
        app.do("meal_plan", kind="breakfast", plan=False)


def test_any_meal_can_be_planned_or_stopped_from_tracking(app: App) -> None:
    on(app)
    lunch_routine(app)
    for back in range(1, 8):
        day = date(2026, 10, 19) - timedelta(days=back)
        app.do("meal_skip", kind="lunch", date=day.isoformat())
        app.do("meal_log", kind="dinner", start=f"{day}T18:30", end=f"{day}T19:15")
    plans = {p["kind"]: p["plan"] for p in app.do("meals")["plans"]}
    assert plans == {"lunch": False, "dinner": True}
    assert "around 6:30pm, 45 min" in app.do("meal_plan", kind="dinner", plan=True)["message"]
    (dinner,) = [r for r in app.table("items") if r["title"] == "Dinner" and r["occurrence_date"] == "2026-10-19"]
    assert (dinner["release_utc"], dinner["due_utc"]) == ("2026-10-19T21:45Z", "2026-10-20T00:00Z")  # 5:45 to 8pm
    with pytest.raises(FieldError, match="dinner is already planned"):
        app.do("meal_plan", kind="dinner", plan=True)


def test_meals_you_let_friday_decide_are_applied_once_a_night(app: App) -> None:
    on(app)
    lunch_routine(app)  # planned 11:30am to 2:30pm, but you eat at 1:45
    breakfasts(app, range(1, 8))
    for back in range(1, 8):
        day = date(2026, 10, 19) - timedelta(days=back)
        app.do("meal_log", kind="lunch", start=f"{day}T13:45", end=f"{day}T14:15")
    assert decide(app.conn, app.now_utc) == []  # no rule: only offered
    app.do("rule_add", text="Let Friday decide breakfast")
    assert app.do("meals")["decided"] == ["breakfast"]
    (said,) = decide(app.conn, app.now_utc)
    assert "Breakfast is planned around 8am" in said
    assert [c["actor"] for c in app.table("command_log") if c["command"] == "meal_plan"] == ["job"]
    assert [t["kind"] for t in app.do("meals")["times"]] == ["lunch"]  # lunch isn't Friday's to move
    assert decide(app.conn, app.now_utc) == []  # once a day
    app.do("rule_add", text="Friday decides lunch too")  # a changed rule acts the same day
    assert app.do("meals")["decided"] == ["breakfast", "lunch"]
    (said,) = decide(app.conn, app.now_utc)
    assert "12:30pm to 3:30pm" in said
    app.do("settings_set", key="meal_tracking", value={"on": False})
    app.do("rule_add", text="Let Friday decide dinner")
    assert decide(app.conn, app.now_utc) == []  # nothing to learn from with tracking off


def test_removing_a_duplicate_meal_keeps_the_routine_ticked_off(app: App) -> None:
    # 27 Oct: lunch logged twice, one removed: the day's Lunch opened again and showed hours "over".
    on(app)
    lunch_routine(app)
    at(app, "15:00")
    first = app.do("meal_log", kind="lunch", start="2026-10-19T12:30", end="2026-10-19T13:00")
    app.do("meal_log", kind="lunch", start="2026-10-19T12:30", end="2026-10-19T13:00")
    assert todays_lunch(app)["status"] == "done"
    meals = [m for m in app.table("meals") if m["kind"] == "lunch"]
    app.do("meal_remove", id=meals[0]["id"])
    assert todays_lunch(app)["status"] == "done"  # the other lunch still says you had it
    app.do("meal_remove", id=meals[1]["id"])
    assert todays_lunch(app)["status"] == "todo"  # none left: open again
    assert first["message"].startswith("Logged lunch")


def test_done_eating_tapped_hours_late_counts_the_usual_length(app: App) -> None:
    on(app)
    lunch_routine(app)  # 30 minutes
    at(app, "12:00")
    app.do("meal_start", kind="lunch")
    at(app, "16:00")
    out = app.do("meal_end")
    assert "counted as your usual 30 min" in out["message"]
    (meal,) = [m for m in app.table("meals") if m["kind"] == "lunch"]
    assert (meal["start_utc"], meal["end_utc"]) == ("2026-10-19T16:00Z", "2026-10-19T16:30Z")
    at(app, "18:00")
    app.do("meal_start", kind="dinner")
    at(app, "18:40")
    assert app.do("meal_end")["message"] == "Dinner: 40 min"  # an ordinary dinner is as you tapped


def test_each_meal_names_the_routine_it_ticked_off_for_the_calendar_to_draw_it_there(app: App) -> None:
    # 4 Nov: the calendar draws a meal you ate as that day's Lunch, in place of the routine's planned pieces
    on(app)
    lunch_routine(app)
    at(app, "13:00")
    app.do("meal_log", kind="lunch", start="2026-10-19T12:10", end="2026-10-19T12:40")
    app.do("meal_log", kind="breakfast", start="2026-10-19T08:00", end="2026-10-19T08:20")
    by_kind = {m["kind"]: m for m in app.do("meals")["days"][0]["meals"]}
    assert by_kind["lunch"]["item_id"] == todays_lunch(app)["id"]
    assert by_kind["breakfast"]["item_id"] is None  # no breakfast routine: drawn on its own


def test_the_meal_you_are_eating_names_its_routine_too(app: App) -> None:
    on(app)
    lunch_routine(app)
    at(app, "12:00")
    app.do("meal_start", kind="lunch")
    assert app.do("meals")["eating"]["item_id"] == todays_lunch(app)["id"]


def test_a_meal_eaten_after_a_timer_ticked_its_routine_off_still_names_that_routine(app: App) -> None:
    # 4 Nov: lunch timed (the routine done), then logged: without the routine the calendar drew lunch twice
    on(app)
    lunch_routine(app)
    at(app, "13:00")
    app.do("done", id=todays_lunch(app)["id"])
    app.do("meal_log", kind="lunch", start="2026-10-19T12:10", end="2026-10-19T12:40")
    (lunch,) = app.do("meals")["days"][0]["meals"]
    assert lunch["item_id"] == todays_lunch(app)["id"]
    # what's stored is unchanged: the meal ticked nothing off, so taking it back opens nothing
    (row,) = app.table("meals")
    assert row["item_id"] is None
