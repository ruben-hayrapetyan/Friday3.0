"""Meals and naps across a clock change (audit, 12 Nov: they were read as plain clock times, so one across the change
was an hour too long or too short, or no length at all, and what Friday learned from them was off). Each keeps its
clock times on both sides of the change and lasts the real minutes that went by, as sleep does (1 Nov). Glass box:
`Meal` and `Nap` from zoned times, their lengths and a meal's minute of its day. Black box through the commands, on
the nights the clocks go back (1 Nov 2026) and forward (14 Mar 2027) in New York: the times you logged, the minutes
they took, and the usual time learned from a week of them. Through the HTTP API:
tests/server/test_meals_naps_clock_change_flow.py (a real `fridayd` runs on the real clock, which can't be put on the
night the clocks change)."""

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from friday.core.time import to_utc, to_zoned
from friday.learn.meals import Meal, minute_of
from friday.learn.sleep import Nap
from tests.commands.helpers import TZ, App, new_app

BACK, FORWARD = date(2026, 11, 1), date(2027, 3, 14)  # the clocks go back at 2am, forward at 2am


def zoned(text: str, fold: int = 0) -> datetime:
    """A New York clock time as Friday reads it from the database: zoned. `fold` 1 is the second 1:30 the night the
    clocks go back."""
    return to_zoned(to_utc(datetime.fromisoformat(text), TZ) + 60 * fold, TZ)


# Glass box


def test_a_snack_across_the_clocks_going_back_is_three_real_hours() -> None:
    snack = Meal(1, "snack", date(2026, 10, 31), zoned("2026-11-01T01:30"), zoned("2026-11-01T03:30"))
    assert snack.minutes == 180


def test_a_snack_across_the_clocks_going_forward_is_one_real_hour() -> None:
    snack = Meal(1, "snack", date(2027, 3, 13), zoned("2027-03-14T01:30"), zoned("2027-03-14T03:30"))
    assert snack.minutes == 60


def test_a_snack_in_the_hour_that_comes_twice_is_its_real_length_not_none() -> None:
    first, second = zoned("2026-11-01T01:45"), zoned("2026-11-01T01:15", fold=1)  # 1:45 EDT, then 1:15 EST
    assert Meal(1, "snack", date(2026, 10, 31), first, second).minutes == 30


def test_a_nap_across_the_change_is_its_real_length() -> None:
    assert Nap(1, date(2026, 10, 31), zoned("2026-11-01T01:30"), zoned("2026-11-01T02:30")).minutes == 120
    assert Nap(1, date(2027, 3, 13), zoned("2027-03-14T01:30"), zoned("2027-03-14T03:00")).minutes == 30


def test_a_meals_minute_of_its_day_is_its_clock_time() -> None:
    assert minute_of(zoned("2026-11-01T12:00"), BACK) == 12 * 60  # 13 hours after midnight, at noon on the clock
    assert minute_of(zoned("2027-03-14T12:00"), FORWARD) == 12 * 60
    assert minute_of(zoned("2026-11-01T01:30"), date(2026, 10, 31)) == 25 * 60 + 30


def test_plain_clock_times_still_count_clock_minutes() -> None:
    snack = Meal(1, "snack", BACK, datetime(2026, 11, 1, 15, 0), datetime(2026, 11, 1, 15, 20))
    assert snack.minutes == 20


# Black box


@pytest.fixture
def app(tmp_path: Path) -> App:
    made = new_app(tmp_path, now="2026-11-02T20:00")
    made.do("settings_set", key="meal_tracking", value={"on": True})
    made.do("settings_set", key="sleep_tracking", value={"on": True})
    return made


@pytest.fixture
def spring(tmp_path: Path) -> App:
    made = new_app(tmp_path, now="2027-03-15T20:00")
    made.do("settings_set", key="meal_tracking", value={"on": True})
    made.do("settings_set", key="sleep_tracking", value={"on": True})
    return made


def meals_on(app: App, day: str) -> list[tuple[str, str, str, int]]:
    (found,) = [d for d in app.do("meals")["days"] if d["date"] == day]
    return [(m["kind"], m["start"], m["end"], m["minutes"]) for m in found["meals"]]


def test_a_late_snack_the_night_the_clocks_go_back_keeps_its_times_and_real_length(app: App) -> None:
    app.do("meal_log", kind="lunch", start="2026-10-31T12:00", end="2026-10-31T12:30")
    app.do("meal_log", kind="snack", start="2026-11-01T01:00", end="2026-11-01T03:00")
    assert meals_on(app, "2026-10-31") == [
        ("lunch", "2026-10-31T12:00", "2026-10-31T12:30", 30),
        ("snack", "2026-11-01T01:00", "2026-11-01T03:00", 180),  # the clocks went back an hour in between
    ]


def test_a_late_snack_the_night_the_clocks_go_forward_keeps_its_times_and_real_length(spring: App) -> None:
    spring.do("meal_log", kind="snack", start="2027-03-14T01:00", end="2027-03-14T03:30")
    assert meals_on(spring, "2027-03-13") == [("snack", "2027-03-14T01:00", "2027-03-14T03:30", 90)]


def test_lunch_at_noon_through_the_change_is_usually_at_noon(app: App) -> None:
    for d in range(7):
        day = BACK - timedelta(days=5) + timedelta(days=d)  # 27 Oct to 2 Nov
        app.do("meal_log", kind="lunch", start=f"{day}T12:00", end=f"{day}T12:30")
    found = {x["group"]: x for x in app.do("meals")["learned"] if x["kind"] == "lunch"}
    assert (found["weekdays"]["usual_start"], found["weekdays"]["usual_min"]) == ("12:00", 30)


def test_a_nap_across_the_change_shows_its_times_and_real_length(app: App) -> None:
    app.do("nap_log", start="2026-11-01T01:00", end="2026-11-01T02:30")
    (nap,) = app.do("sleep")["naps"]
    assert (nap["start"], nap["end"], nap["minutes"]) == ("2026-11-01T01:00", "2026-11-01T02:30", 150)


def test_a_nap_the_night_the_clocks_go_forward(spring: App) -> None:
    spring.do("nap_log", start="2027-03-14T01:30", end="2027-03-14T03:15")
    (nap,) = spring.do("sleep")["naps"]
    assert (nap["start"], nap["end"], nap["minutes"]) == ("2027-03-14T01:30", "2027-03-14T03:15", 45)


def test_a_second_dinner_in_the_hour_that_comes_twice_is_counted_second() -> None:
    from friday.learn.meals import nths

    day = date(2026, 10, 31)
    first = Meal(1, "dinner", day, zoned("2026-11-01T01:45"), zoned("2026-11-01T01:55"))  # 1:45 EDT
    second = Meal(2, "dinner", day, zoned("2026-11-01T01:15", fold=1), zoned("2026-11-01T01:40", fold=1))  # EST
    assert nths([second, first]) == {1: 1, 2: 2}
