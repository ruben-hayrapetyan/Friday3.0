"""closed_gaps from inside (engine/gaps.py): which measures count as keeping the plan steady, the values a slide is
judged by, where a piece ends, and each reason a piece isn't slid."""

import numpy as np

from friday.engine.compile import compile_problem
from friday.engine.evaluate import evaluate
from friday.engine.gaps import closed_gaps, piece_end, slid_back, steady_measures, unsteady_values
from friday.engine.problem import STAGES
from tests.engine.helpers import at, item, plan, problem, zone_problem

EVENING = at(0, "21:30")
CURRENT = {1: [(EVENING, EVENING + 60)], 2: [(EVENING + 75, EVENING + 105)]}


def two(rules=("late_night", "minimize_changes"), extra=(), **build):  # noqa: ANN001, ANN201
    pieces = [item("assignment", 1, duration_units=4, due_utc=at(1, "09:00")),
              item("reading", 2, duration_units=2, due_utc=at(1, "09:00"))]  # fmt: skip
    return compile_problem(problem(pieces, rules, extra, now=EVENING, slots=8, **build))


def test_the_steady_measures_are_minimize_changes_and_nothing_else() -> None:
    breaks = [dict(type="buffer", name="breathing_room", weight=3, params=dict(minutes="15m"))]
    c = two(current=CURRENT, extra=breaks)
    steady = steady_measures(c)
    assert steady and {c.rule_names[c.m.m_rule[m]] for m in steady} == {"minimize_changes"}
    others = {c.rule_names[c.m.m_rule[m]] for m in range(c.m.M) if m not in steady}
    assert others == {"breathing_room"}  # a break you set still counts


def test_the_values_a_slide_is_judged_by_are_the_stage_values_less_keeping_the_plan_steady() -> None:
    c = two(current=CURRENT)
    moved = plan(item_1=(0, 1, 2, 3), item_2=(4, 5))  # off where the last plan had the reading: steadiness costs
    found = evaluate(c.problem, moved)
    assert found.rule_totals["minimize_changes"] > 0
    expected = tuple(
        found.stage_values[s]
        - (found.rule_totals["minimize_changes"] if s == found.rule_stage["minimize_changes"] else 0)
        for s in STAGES
    )
    assert unsteady_values(c, c.owner_from_plan(moved), steady_measures(c)) == expected


def test_a_piece_ends_where_the_next_slot_is_someone_else_s_or_free() -> None:
    owner = np.array([0, 0, 0, -1, 1, 1, 0], dtype=np.int16)
    assert (piece_end(owner, 0), piece_end(owner, 4), piece_end(owner, 6)) == (2, 5, 6)


def test_a_piece_with_no_empty_time_before_it_isn_t_slid() -> None:
    c = two()
    owner = c.owner_from_plan(plan(item_1=(0, 1, 2, 3), item_2=(4, 5)))
    assert slid_back(c, owner, c.problem.items["item:2"], 1, 4, 5) is None


def test_a_slide_lands_right_after_the_work_before_it_and_keeps_its_length() -> None:
    c = two()
    owner = c.owner_from_plan(plan(item_1=(0, 1), item_2=(5, 6)))
    trial = slid_back(c, owner, c.problem.items["item:2"], 1, 5, 6)
    assert trial is not None and c.plan_from_owner(trial) == plan(item_1=(0, 1), item_2=(2, 3))


def test_meals_and_work_with_travel_aren_t_slid() -> None:
    c = two()
    owner = c.owner_from_plan(plan(item_1=(0, 1), item_2=(5, 6)))
    reading = c.problem.items["item:2"]
    reading.meal_window = (EVENING, EVENING + 120)
    assert slid_back(c, owner, reading, 1, 5, 6) is None
    reading.meal_window, reading.travel_before = None, 1
    assert slid_back(c, owner, reading, 1, 5, 6) is None


def test_a_piece_on_another_planning_day_than_the_work_before_it_isn_t_slid() -> None:
    # zone_problem: 23:00 Monday on, the planning day turning at 04:00 (slot 20)
    pieces = [item("chore", 1, duration_units=2, due_utc=at(2, "09:00")),
              item("chore", 2, duration_units=2, due_utc=at(2, "09:00"))]  # fmt: skip
    c = compile_problem(zone_problem(pieces))
    owner = c.owner_from_plan(plan(item_1=(17, 18), item_2=(21,)))  # 03:15–03:45, then the first slot of Tuesday
    assert c.problem.grid.day[18] != c.problem.grid.day[21]
    assert slid_back(c, owner, c.problem.items["item:2"], 1, 21, 21) is None


def test_a_slide_that_costs_the_same_is_taken() -> None:
    c = two(rules=())
    owner = c.owner_from_plan(plan(item_1=(0, 1, 2, 3), item_2=(6, 7)))
    assert c.plan_from_owner(closed_gaps(c, owner)) == plan(item_1=(0, 1, 2, 3), item_2=(4, 5))


def test_a_set_cancel_flag_leaves_the_plan_as_it_was() -> None:
    c = two(rules=())
    owner = c.owner_from_plan(plan(item_1=(0, 1, 2, 3), item_2=(6, 7)))
    assert (closed_gaps(c, owner, np.ones(1, dtype=np.int64)) == owner).all()
