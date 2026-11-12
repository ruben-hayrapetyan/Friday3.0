"""Construction honours every wall and, on small instances, finds zero lateness whenever it is possible."""

import numpy as np
import pytest

from friday.engine.checker import check
from friday.engine.construct import construct, prepare_start
from friday.engine.evaluate import evaluate
from friday.engine.kernel import init_state, new_state, total_violations
from friday.planner.build import Dependency, Pin
from tests.bench.generator import ADVERSARIAL, reference_instance, tiny
from tests.engine.brute import brute_force
from tests.engine.helpers import MON10, at, item, problem, zone_problem

FAMILIES = {"ref20": lambda s: reference_instance(20, s), "ref60": lambda s: reference_instance(60, s), **ADVERSARIAL}


@pytest.mark.parametrize("family", list(FAMILIES))
@pytest.mark.parametrize("seed", [0, 1])
def test_the_start_plan_breaks_no_wall(family: str, seed: int) -> None:
    p = FAMILIES[family](seed).build()
    start = prepare_start(p)
    assert start.violations == 0
    assert check(p, start.c.plan_from_owner(start.owner)) == []


@pytest.mark.parametrize("family", ["ref20", "ref60", "tight", "deps", "onesit", "pins", "fragmented"])
def test_construction_meets_every_deadline_when_load_is_reasonable(family: str) -> None:
    p = FAMILIES[family](0).build()
    start = prepare_start(p)
    assert evaluate(p, start.c.plan_from_owner(start.owner)).deadline_misses == []


@pytest.mark.parametrize("seed", range(40))
def test_zero_late_whenever_brute_force_finds_it_possible(seed: int) -> None:
    p = tiny(seed, 7, 3).build()
    if not any(it.firmness == "hard" for it in p.items.values()):
        pytest.skip("no hard deadline in this instance")
    best = brute_force(p).best.stage_values["deadlines"]
    start = prepare_start(p)
    late = evaluate(p, start.c.plan_from_owner(start.owner)).stage_values["deadlines"]
    assert best > 0 or late == 0


def test_a_warm_start_keeps_the_previous_plan_where_it_is_still_allowed() -> None:
    p = reference_instance(20, 3).build()
    first = prepare_start(p)
    again = construct(first.c, first.owner.copy())
    assert (again == first.owner).all()


def test_a_warm_start_drops_kept_work_that_no_longer_fits_its_walls() -> None:
    p = problem([item("chore", 1, duration_units=4)], ["unscheduled"])
    start = prepare_start(p)
    stale = np.full(p.grid.S, -1, dtype=np.int16)
    stale[[0, 1]] = 0  # half a one-sitting chore, as if it had been longer before
    owner = construct(start.c, stale)
    st = new_state(start.c.m)
    init_state(start.c.m, st, owner)
    assert total_violations(start.c.m, st) == 0


def test_a_warm_start_moves_what_waits_on_dropped_work_along_with_it() -> None:
    # B was kept after half of chore A; A's stale half is dropped and A goes after B, so B must start over too.
    p = problem([item("chore", 1, duration_units=4), item("chore", 2, duration_units=2)], ["unscheduled"],
                deps=[Dependency(2, 1, fraction=0.5)])  # fmt: skip
    start = prepare_start(p)
    stale = np.full(p.grid.S, -1, dtype=np.int16)
    a, b = start.c.keys.index("item:1"), start.c.keys.index("item:2")
    stale[[0, 1]], stale[[2, 3]] = a, b
    owner = construct(start.c, stale)
    assert check(p, start.c.plan_from_owner(owner)) == []


def test_a_lock_that_breaks_its_own_chunk_rule_becomes_preferred() -> None:
    work = [item("assignment", 1, duration_units=4, due_utc=MON10 + 480, min_chunk_units=2, max_chunk_units=2)]
    p = problem(work, ["late_work"], pins=[Pin(1, MON10, MON10 + 45, "locked")])  # 3 units, more than the max chunk
    start = prepare_start(p)
    assert start.violations == 0
    assert not p.items["item:1"].locked


def test_new_work_beside_a_lock_as_long_as_the_longest_chunk_leaves_the_lock_kept() -> None:
    # The lock (midnight to 1am) is a whole longest chunk; new work placed right before it made one run of two hours,
    # past the longest chunk, and the lock was demoted to a preferred pin though nothing stopped it being kept.
    work = [item("assignment", 1, duration_units=8, max_chunk_units=4, release_utc=at(0, "23:00"),
                 due_utc=at(1, "12:00"))]  # fmt: skip
    p = zone_problem(work, ["late_work"], pins=[Pin(1, at(1, "00:00"), at(1, "01:00"), "locked")])
    start = prepare_start(p)
    assert start.demoted == [] and len(p.items["item:1"].locked) == 4
    assert start.violations == 0 and check(p, start.c.plan_from_owner(start.owner)) == []


def test_work_across_the_start_of_a_planning_day_keeps_to_the_longest_chunk() -> None:
    # 03:00–04:00 ends one planning day and 04:00 begins the next: chunks filled on each side met in one long run.
    work = [item("assignment", 1, duration_units=8, max_chunk_units=4, release_utc=at(1, "03:00"),
                 due_utc=at(1, "12:00"))]  # fmt: skip
    p = zone_problem(work, ["late_work"])
    start = prepare_start(p)
    assert start.violations == 0 and check(p, start.c.plan_from_owner(start.owner)) == []
