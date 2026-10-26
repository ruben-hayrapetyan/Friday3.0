"""Learning from meals: medians by weekdays and weekends, a late snack counted past midnight, skips over the days
recorded, nothing said before enough days, and a routine's length offered only when it's well off."""

from datetime import date, datetime, timedelta

from friday.learn.meals import Learned, Meal, learn, length_changes

MONDAY = date(2026, 10, 12)


def eaten(day: date, kind: str, start: str, minutes: int, n: int = 0) -> Meal:
    begin = datetime.fromisoformat(f"{day}T{start}")
    return Meal(n, kind, day, begin, begin + timedelta(minutes=minutes))


def test_weekdays_and_weekends_are_learned_apart() -> None:
    week = [MONDAY + timedelta(days=d) for d in range(7)]
    meals = [eaten(d, "lunch", "12:00" if d.weekday() < 5 else "13:30", 30 if d.weekday() < 5 else 60) for d in week]
    found = {x.group: x for x in learn(meals, min_days=2)}
    assert (found["weekdays"].usual_start, found["weekdays"].usual_min, found["weekdays"].days) == ("12:00", 30, 5)
    assert (found["weekends"].usual_start, found["weekends"].usual_min) == ("13:30", 60)


def test_a_snack_after_midnight_counts_late_not_early() -> None:
    days = [MONDAY + timedelta(days=d) for d in range(4)]
    after_midnight = [datetime.combine(d + timedelta(days=1), datetime.min.time()) for d in days]
    meals = [
        Meal(n, "snack", days[n], at + timedelta(minutes=30 + 30 * (n % 2)), None)
        for n, at in enumerate(after_midnight)
    ]
    meals.append(eaten(MONDAY + timedelta(days=4), "snack", "23:30", 10))
    (snack,) = learn(meals, min_days=4)
    assert snack.usual_start == "00:30"  # the median of 12:30am, 1am, 12:30am, 1am and 11:30pm


def test_skips_count_against_the_days_recorded_and_an_eaten_meal_beats_a_skip() -> None:
    days = [MONDAY + timedelta(days=d) for d in range(4)]
    meals = [eaten(d, "breakfast", "08:00", 15) for d in days[:3]]
    meals += [Meal(9, "breakfast", days[3], None, None, skipped=True)]
    meals += [Meal(10, "breakfast", days[0], None, None, skipped=True)]  # skipped, then eaten after all
    (breakfast,) = learn(meals, min_days=4)
    assert (breakfast.days, breakfast.skip_share, breakfast.usual_min) == (4, 0.25, 15)


def test_nothing_is_said_before_enough_days() -> None:
    assert learn([eaten(MONDAY + timedelta(days=d), "dinner", "19:00", 40) for d in range(3)], min_days=4) == []


def test_a_routine_is_offered_the_length_you_take_only_when_well_off() -> None:
    took = [
        Learned("lunch", "weekdays", 5, "12:00", 45, 15, 0.0),
        Learned("dinner", "weekends", 4, "19:00", 50, 0, 0.0),
    ]
    assert length_changes(took, {"lunch": 15, "dinner": 45}) == {"lunch": 45}  # dinner is 5 minutes off
    assert length_changes(took, {"breakfast": 15}) == {}
