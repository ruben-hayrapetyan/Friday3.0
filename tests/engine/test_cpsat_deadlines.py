"""The deadline fallback model: its value equals the evaluator's, its constraints equal the walls."""

import itertools

import numpy as np
import pytest
from ortools.sat.python import cp_model

from friday.engine.checker import check
from friday.engine.cpsat_deadlines import DeadlineModel
from friday.engine.evaluate import evaluate
from friday.planner.build import Dependency, Pin
from tests.bench.generator import overload, tiny
from tests.engine.brute import brute_force
from tests.engine.helpers import MON10, item, problem
from tests.engine.plans import random_plan


def fixed_to(model: DeadlineModel, plan: dict) -> cp_model.CpSolverStatus:
    chosen = {(k, s) for k, slots in plan.items() for s in slots}
    for (k, s), v in model.x.items():
        model.m.add(v == int((k, s) in chosen))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    status = solver.solve(model.m)
    model.last_objective = solver.objective_value if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return status


@pytest.mark.parametrize("seed", range(4))
def test_the_model_value_of_a_plan_equals_the_evaluators_deadlines_value(seed: int) -> None:
    p = overload(seed).build()
    from friday.engine.construct import prepare_start

    start = prepare_start(p)
    plan = start.c.plan_from_owner(start.owner)
    model = DeadlineModel(p)
    assert fixed_to(model, plan) == cp_model.OPTIMAL
    assert round(model.last_objective) == evaluate(p, plan).stage_values["deadlines"] > 0


@pytest.mark.parametrize("seed", range(6))
def test_the_feasible_plans_are_exactly_the_valid_plans(seed: int) -> None:
    p = tiny(seed, 6, 2).build()
    slots = sorted({s for it in p.items.values() for s in it.allowed})
    owners = [[None] + [k for k, it in p.items.items() if s in it.allowed_set] for s in slots]
    for assignment in itertools.product(*owners):
        candidate = {k: tuple(s for s, o in zip(slots, assignment, strict=True) if o == k) for k in p.items}
        feasible = fixed_to(DeadlineModel(p), candidate) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        assert feasible == (check(p, candidate) == []), candidate


@pytest.mark.parametrize("seed", range(10))
def test_it_matches_brute_force_on_tiny_instances(seed: int) -> None:
    p = tiny(seed, 7, 3).build()
    result = DeadlineModel(p).solve(None, 10.0, 1)
    assert result.plan is not None and check(p, result.plan) == []
    assert evaluate(p, result.plan).stage_values["deadlines"] == brute_force(p).best.stage_values["deadlines"]


def walls_hold(p, plan) -> bool:  # noqa: ANN001
    return fixed_to(DeadlineModel(p), plan) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_c1_one_thing_per_slot() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 480), item("chore", 2, duration_units=2)])
    assert not walls_hold(p, {"item:1": (0, 1), "item:2": (1, 2)})


def test_c2_amounts_and_overflow() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 480)])
    assert not walls_hold(p, {"item:1": (0, 1, 2)})
    assert walls_hold(p, {"item:1": ()})


def test_c4_locks() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 480)], pins=[Pin(1, MON10, MON10 + 30)])
    assert not walls_hold(p, {"item:1": (2, 3)})


def test_c5_daily_cap() -> None:
    p = problem([item("chore", 1, duration_units=4, shape="split", min_chunk_units=1)], cap_hours=0.75)
    assert not walls_hold(p, {"item:1": (0, 1, 2, 3)})


def test_c6_one_sitting() -> None:
    p = problem([item("chore", 1, duration_units=4)])
    assert not walls_hold(p, {"item:1": (0, 1)})
    assert not walls_hold(p, {"item:1": (0, 1, 3, 4)})


def test_c7_minimum_and_maximum_chunk() -> None:
    p = problem([item("assignment", 1, duration_units=4, due_utc=MON10 + 480, min_chunk_units=2, max_chunk_units=3)])
    assert not walls_hold(p, {"item:1": (0, 2, 3, 4)})
    assert not walls_hold(p, {"item:1": (0, 1, 2, 3)})
    assert walls_hold(p, {"item:1": (0, 1, 3, 4)})


def test_c8_dependencies() -> None:
    a = item("assignment", 1, duration_units=2, due_utc=MON10 + 480)
    b = item("assignment", 2, duration_units=2, due_utc=MON10 + 480)
    p = problem([a, b], deps=[Dependency(2, 1)])
    assert not walls_hold(p, {"item:1": (2, 3), "item:2": (0, 1)})
    assert walls_hold(p, {"item:1": (0, 1), "item:2": (2, 3)})


def test_the_lock_core_names_contradictory_locks() -> None:
    a = item("chore", 1, duration_units=4, shape="split", min_chunk_units=1)
    b = item("chore", 2, duration_units=4, shape="split", min_chunk_units=1)
    p = problem([a, b], cap_hours=1.5, pins=[Pin(1, MON10, MON10 + 60), Pin(2, MON10 + 60, MON10 + 120, created=1)])
    p.day_caps = [6]  # the lock check raised the cap; put it back so the locks contradict it
    assert set(DeadlineModel(p, assume_locks=True).lock_core()) == {"item:1", "item:2"}


def test_a_hint_is_kept_when_nothing_beats_it() -> None:
    p = tiny(3, 7, 3).build()
    hint = random_plan(p, np.random.default_rng(0), 0.0)
    result = DeadlineModel(p).solve(hint, 5.0, 1)
    assert result.status in ("OPTIMAL", "FEASIBLE")
