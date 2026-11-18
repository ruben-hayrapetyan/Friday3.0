"""Early isn't shredded (17 Nov, the user's choice: "as soon as there's time" for all deadline work, in due order).
With work pulled into the first free time, the half hours between events were where short work went: Jordan's
hour-long Aplia quiz 7 came out 30 + 30 minutes. An hour's work goes in one sitting when an hour is free for it
(planner/build.py `one_sitting_when_it_fits`, in tests/commands/test_as_soon_as_there_is_time.py); for longer work the
start plan looks for real sittings first (construct.py `start_sittings`), and what the search leaves with a piece
short of an hour is put in one sitting where that's better (scheduler.py `whole_again`)."""

from friday.engine.compile import compile_problem
from friday.engine.construct import construct
from friday.engine.evaluate import evaluate
from friday.engine.scheduler import stage_values, whole_again
from tests.engine.helpers import at, item, make, plan, problem


def quiz_day(rules=("late_work",)):  # noqa: ANN001, ANN201
    """10:00–14:00 (16 quarter hours), a class 10:30–11:00: a half hour before it, three hours after. A 90-minute
    problem set due at 14:00, wanted as soon as there's time."""
    quiz = item("assignment", 1, title="MATH 2940 HW 8", duration_units=6, due_utc=at(0, "14:00"))
    lecture = make.fixed("commitment", "ECON 1110 Lecture", at(0, "10:30"), 30)
    return problem([quiz, lecture], rules, slots=16)


def test_the_start_plan_looks_for_a_real_sitting_before_the_half_hour_before_class() -> None:
    c = compile_problem(quiz_day())
    started = c.plan_from_owner(construct(c))
    assert started["item:1"] == (4, 5, 6, 7, 8, 9)  # 11:00–12:30; it took 10:00–10:30 and 11:00–12:00


def test_pieces_left_by_the_search_are_put_back_in_one_sitting() -> None:
    c = compile_problem(quiz_day())
    pieces = c.owner_from_plan(plan(item_1=(0, 1, 8, 9, 10, 11)))  # 30 minutes before class, an hour later on
    whole = whole_again(c, pieces)
    assert c.plan_from_owner(whole)["item:1"] == (4, 5, 6, 7, 8, 9)
    assert stage_values(c, whole) < stage_values(c, pieces)


def test_work_you_placed_stays_in_its_pieces() -> None:
    # a preferred pin: where you put it, not for whole_again to move
    p = quiz_day()
    p.items["item:1"].preferred = frozenset({0, 1})
    c = compile_problem(p)
    pieces = c.owner_from_plan(plan(item_1=(0, 1, 8, 9, 10, 11)))
    assert (whole_again(c, pieces) == pieces).all()


def test_with_only_short_gaps_before_its_due_it_is_still_done_in_them() -> None:
    # due 11:30: only the half hours before and after class in time; split, not late
    quiz = item("assignment", 1, duration_units=4, due_utc=at(0, "11:30"))
    lecture = make.fixed("commitment", "ECON 1110 Lecture", at(0, "10:30"), 30)
    c = compile_problem(problem([quiz, lecture], ["late_work"], slots=16))
    halves = c.owner_from_plan(plan(item_1=(0, 1, 4, 5)))
    assert evaluate(c.problem, c.plan_from_owner(halves)).stage_values["deadlines"] == 0
    assert (whole_again(c, halves) == halves).all()  # one sitting would be late: the pieces stand
