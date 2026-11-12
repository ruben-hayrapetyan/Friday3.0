"""Meal tracking at the edges: what can't be ended, put right or changed, said in words; a done-eating tapped late
counted at what Friday learned you take; and Friday deciding a meal's length."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.commands.eating import decide
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app
from tests.commands.test_meals import at, lunch_routine, on, todays_lunch


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    app = new_app(tmp_path)
    on(app)
    return app


def long_lunches(app: App) -> None:
    """Last week's lunches, 45 minutes each, at noon."""
    for back in range(1, 8):
        day = date(2026, 10, 19) - timedelta(days=back)
        app.do("meal_log", kind="lunch", start=f"{day}T12:00", end=f"{day}T12:45")


def test_done_eating_needs_a_meal_and_a_time_after_it_began(app: App) -> None:
    with pytest.raises(FieldError, match="you aren't eating"):
        app.do("meal_end")
    app.do("meal_start", kind="breakfast")
    with pytest.raises(FieldError, match="that's before you started"):
        app.do("meal_end", at="2026-10-19T08:30")


def test_done_eating_tapped_late_counts_the_length_friday_learned(app: App) -> None:
    lunch_routine(app)  # planned at 30 minutes
    long_lunches(app)
    at(app, "12:00")
    app.do("meal_start", kind="lunch")
    at(app, "16:00")
    assert "counted as your usual 45 min" in app.do("meal_end")["message"]


def test_a_meal_put_right_must_exist_have_times_and_end_after_it_starts(app: App) -> None:
    with pytest.raises(FieldError, match="no meal 99"):
        app.do("meal_edit", id=99, start="2026-10-19T08:00")
    app.do("meal_skip", kind="breakfast")
    (skipped,) = app.table("meals")
    with pytest.raises(FieldError, match="a skipped meal has no times"):
        app.do("meal_edit", id=skipped["id"], start="2026-10-19T08:00")
    app.do("meal_log", kind="dinner", start="2026-10-18T18:00", end="2026-10-18T18:30")
    dinner = next(m for m in app.table("meals") if m["kind"] == "dinner")
    with pytest.raises(FieldError, match="ends after it starts"):
        app.do("meal_edit", id=dinner["id"], end="2026-10-18T17:00")


def test_nothing_learned_means_no_new_length_time_or_plan(app: App) -> None:
    lunch_routine(app)
    with pytest.raises(FieldError, match="hasn't learned a different length for lunch"):
        app.do("meal_use_length", kind="lunch")
    with pytest.raises(FieldError, match="hasn't learned a different time for lunch"):
        app.do("meal_use_time", kind="lunch")
    with pytest.raises(FieldError, match="hasn't learned when you have dinner yet"):
        app.do("meal_plan", kind="dinner", plan=True)


def test_friday_deciding_lunch_plans_it_at_the_length_you_take(app: App) -> None:
    lunch_routine(app)
    long_lunches(app)
    app.do("rule_add", text="Let Friday decide lunch")
    said = decide(app.conn, app.now_utc)
    assert any("planned at 45 min" in s for s in said)
    assert todays_lunch(app)["ideal_units"] == 3
