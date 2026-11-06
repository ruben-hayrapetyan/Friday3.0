"""A meal's place among that day's of its kind, from inside (5 Nov: "sometimes i have 4 meals (2 dinners)"): counted
by start, per day and kind; skips and snacks not counted; the names; and what's usual kept to each day's first."""

from datetime import date, datetime, timedelta

from friday.learn.meals import Meal, learn, meal_name, nths

MONDAY = date(2026, 10, 12)


def eaten(n: int, day: date, kind: str, start: str, minutes: int = 30) -> Meal:
    begin = datetime.fromisoformat(f"{day}T{start}")
    return Meal(n, kind, day, begin, begin + timedelta(minutes=minutes))


def test_the_second_dinner_of_a_day_is_2_by_when_it_started_not_by_when_it_was_logged() -> None:
    late, early = eaten(1, MONDAY, "dinner", "22:00"), eaten(2, MONDAY, "dinner", "18:00")
    assert nths([late, early]) == {2: 1, 1: 2}


def test_each_day_and_each_meal_counts_on_its_own() -> None:
    meals = [eaten(1, MONDAY, "dinner", "18:00"), eaten(2, MONDAY, "lunch", "12:00"),
             eaten(3, MONDAY + timedelta(days=1), "dinner", "19:00"), eaten(4, MONDAY, "dinner", "21:30")]  # fmt: skip
    assert nths(meals) == {1: 1, 2: 1, 3: 1, 4: 2}


def test_a_skipped_meal_and_snacks_aren_t_counted() -> None:
    skipped = Meal(1, "dinner", MONDAY, None, None, skipped=True)
    snacks = [eaten(2, MONDAY, "snack", "15:00"), eaten(3, MONDAY, "snack", "16:00")]
    dinner = eaten(4, MONDAY, "dinner", "19:00")
    assert nths([skipped, *snacks, dinner]) == {4: 1}


def test_names_by_place() -> None:
    assert [meal_name("dinner", n) for n in (1, 2, 3, 5, 6)] == [
        "dinner", "second dinner", "third dinner", "fifth dinner", "dinner 6",
    ]  # fmt: skip
    assert meal_name("snack", 3) == "snack"


def test_a_second_dinner_doesn_t_move_the_usual_dinner() -> None:
    days = [MONDAY + timedelta(days=d) for d in range(4)]  # Monday to Thursday
    firsts = [eaten(n, d, "dinner", "18:00", 40) for n, d in enumerate(days)]
    seconds = [eaten(10 + n, d, "dinner", "22:30", 20) for n, d in enumerate(days[:3])]
    (found,) = [x for x in learn([*firsts, *seconds], min_days=2) if x.kind == "dinner"]
    assert (found.usual_start, found.usual_min, found.days) == ("18:00", 40, 4)
