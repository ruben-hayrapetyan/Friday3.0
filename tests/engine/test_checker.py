"""Each wall has a plan that breaks it and a plan that keeps it (DESIGN §11.4)."""

import itertools

import numpy as np
import pytest

from friday.engine.checker import check
from friday.engine.evaluate import evaluate
from friday.planner.build import Dependency, Pin
from tests.bench.generator import reference_instance, tiny
from tests.engine.brute import brute_force
from tests.engine.helpers import MON10, at, item, plan, problem
from tests.engine.plans import random_plan


def walls(p, plan_, protected=()) -> set[str]:  # noqa: ANN001
    return {v.wall for v in check(p, plan_, protected)}


def codes(p, plan_) -> set[str]:  # noqa: ANN001
    return {v.code for v in check(p, plan_)}


def test_a_valid_plan_and_overflow_have_no_violations() -> None:
    p = problem([item("assignment", 1, duration_units=4, due_utc=MON10 + 480)], ["late_work"])
    assert check(p, plan(item_1=(0, 1, 2, 3))) == []
    assert check(p, plan(item_1=())) == []


def test_w1_one_thing_at_a_time() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 480), item("chore", 2, duration_units=2)])
    assert "W1" in walls(p, plan(item_1=(0, 1), item_2=(1, 2)))
    assert "duplicate_slot" in codes(p, plan(item_1=(0, 0)))


def test_w2_allowed_slots_exclude_before_release_fixed_items_and_sleep() -> None:
    meeting = item("commitment", 9, start_utc=MON10 + 30, end_utc=MON10 + 45, event_kind="meeting")  # 5 + 5 buffers
    work = item("assignment", 1, duration_units=2, due_utc=MON10 + 480, release_utc=MON10 + 60)
    p = problem([meeting, work])
    assert walls(p, plan(item_1=(0, 1))) == {"W2"}  # before the release
    assert "W2" in walls(p, plan(item_1=(2,)))  # inside the meeting and its buffers
    asleep = problem([work], now=at(0, "00:45"))
    assert "W2" in walls(asleep, plan(item_1=(0, 1)))  # sleep core


def test_w3_locks_must_be_held() -> None:
    items = [item("assignment", 1, duration_units=2, due_utc=MON10 + 480), item("chore", 2, duration_units=1)]
    p = problem(items, pins=[Pin(1, MON10, MON10 + 30, "locked")])
    assert "W3" in walls(p, plan(item_1=(0,)))
    assert "W2" in walls(p, plan(item_1=(0, 1), item_2=(0,)))  # another item can't use a locked slot
    assert check(p, plan(item_1=(0, 1))) == []


def test_w4_amounts() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 480)])
    assert "W4" in walls(p, plan(item_1=(0, 1, 2)))  # fine slots: no free extra unit
    elastic = problem([item("routine", 1, min_units=1, ideal_units=2, max_units=3, release_utc=MON10,
                            due_utc=MON10 + 120)])  # fmt: skip
    assert "over_max" in codes(elastic, plan(item_1=(0, 1, 2, 3)))
    target = problem([item("goal", 1, target_units=2, release_utc=MON10, due_utc=MON10 + 120, min_chunk_units=1)])
    assert "over_cap" in codes(target, plan(item_1=(0, 1, 2, 3)))  # cap = ⌈1.5 × 2⌉ = 3 units
    side = problem([item("side_project", 1, daily_ceiling_units=2, min_chunk_units=1)])
    assert "over_ceiling" in codes(side, plan(item_1=(0, 1, 2)))


def test_w4_allows_one_extra_unit_only_to_fill_a_coarse_slot() -> None:
    p = problem([item("assignment", 1, duration_units=3, due_utc=at(3, "12:00"), min_chunk_units=1)],
                slots=None, days=2, fine_days=0)  # fmt: skip
    coarse = [s for s in range(p.grid.S) if p.grid.units[s] == 2][:2]
    assert check(p, plan(item_1=tuple(coarse))) == []  # 4 units hold 3


def test_w5_daily_cap() -> None:
    p = problem([item("chore", 1, duration_units=4, shape="split", min_chunk_units=1)], cap_hours=0.75)
    assert walls(p, plan(item_1=(0, 1, 2, 3))) == {"W5"}


def test_w6_one_sitting_is_whole_and_contiguous() -> None:
    p = problem([item("chore", 1, duration_units=4)])
    assert "not_one_sitting" in codes(p, plan(item_1=(0, 1, 4, 5)))
    assert "partial_one_sitting" in codes(p, plan(item_1=(0, 1)))
    assert check(p, plan(item_1=(0, 1, 2, 3))) == [] and check(p, plan(item_1=())) == []


def test_w7_chunk_lengths() -> None:
    p = problem([item("assignment", 1, duration_units=4, due_utc=MON10 + 480, min_chunk_units=2, max_chunk_units=3)])
    assert "short_chunk" in codes(p, plan(item_1=(0, 2, 3, 4)))
    assert "long_chunk" in codes(p, plan(item_1=(0, 1, 2, 3)))
    assert check(p, plan(item_1=(0, 1, 3, 4))) == []


def test_w7_a_short_chunk_is_fine_when_it_is_the_whole_amount() -> None:
    p = problem([item("assignment", 1, duration_units=1, due_utc=MON10 + 480)])  # preset minimum is 2 units
    assert check(p, plan(item_1=(3,))) == []


def test_w8_dependency_needs_its_source_first() -> None:
    a = item("assignment", 1, duration_units=2, due_utc=MON10 + 480)
    b = item("assignment", 2, duration_units=2, due_utc=MON10 + 480)
    p = problem([a, b], deps=[Dependency(2, 1)])
    assert walls(p, plan(item_1=(2, 3), item_2=(0, 1))) == {"W8"}
    assert check(p, plan(item_1=(0, 1), item_2=(2, 3))) == []


def test_w8_dependency_fraction_and_lag() -> None:
    a = item("assignment", 1, duration_units=4, due_utc=MON10 + 480)
    b = item("assignment", 2, duration_units=1, due_utc=MON10 + 480, min_chunk_units=1)
    p = problem([a, b], deps=[Dependency(2, 1, 0.5, 15)], slots=12)  # half of A (2 units) done by 10:30, +15 min
    a_plan = (0, 1, 6, 7)
    assert "W8" in walls(p, plan(item_1=a_plan, item_2=(2,)))
    assert check(p, plan(item_1=a_plan, item_2=(3,))) == []


def test_w9_a_protected_item_must_stay_complete_and_on_time() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 60)])
    assert check(p, plan(item_1=(0, 1)), protected=["item:1"]) == []
    assert walls(p, plan(item_1=(4, 5)), protected=["item:1"]) == {"W9"}  # late
    assert walls(p, plan(item_1=()), protected=["item:1"]) == {"W9"}  # lost its units
    assert check(p, plan(item_1=())) == []  # unprotected, overflow is merely priced


def independent_validity(p, plan_) -> bool:  # noqa: ANN001, C901
    """The walls re-derived from DESIGN §11.4 with 0/1 strings per item, not the checker's code."""
    grid, n = p.grid, p.grid.S
    bits = {k: [1 if s in set(plan_.get(k, ())) else 0 for s in range(n)] for k in p.items}
    if any(sum(bits[k][s] for k in p.items) > 1 for s in range(n)):
        return False
    for key, it in p.items.items():
        b = bits[key]
        placed = sum(grid.units[s] for s in range(n) if b[s])
        if any(b[s] and s not in it.allowed_set for s in range(n)) or any(
            s in it.locked and not b[s] for s in range(n)
        ):
            return False
        fills_coarse = placed == it.need + 1 and any(grid.units[s] > 1 for s in range(n) if b[s])
        if it.amount == "fixed" and placed > it.need and not fills_coarse:
            return False
        if (it.amount == "elastic" and placed > it.max) or (it.amount == "target" and placed > it.cap):
            return False
        if it.amount == "open":
            for d in range(grid.n_days):
                limit = it.daily_ceiling - (it.progress_today if d == 0 else 0)
                if sum(grid.units[s] for s in grid.day_slots[d] if b[s]) > limit:
                    return False
        starts = [s for s in range(n) if b[s] and (s == 0 or not b[s - 1])]
        if it.shape == "one_sitting" and (len(starts) > 1 or (it.amount == "fixed" and 0 < placed < it.need)):
            return False
        for s in starts:
            j, got = s, 0
            while got < it.min_chunk:
                if j >= n or not b[j]:
                    return False
                got, j = got + int(grid.units[j]), j + 1
        run = 0
        for s in range(n):
            run = run + int(grid.units[s]) if b[s] else 0
            if it.max_chunk is not None and run > it.max_chunk:
                return False
    for d in range(grid.n_days):
        used = sum(grid.units[s] for s in grid.day_slots[d] if any(bits[k][s] for k in p.items))
        if used > p.day_caps[d]:
            return False
    return True


@pytest.mark.parametrize("seed", range(12))
def test_checker_matches_an_independent_reading_on_every_assignment(seed: int) -> None:
    p = tiny(seed, 7, 3).build()
    slots = sorted({s for it in p.items.values() for s in it.allowed})
    owners = [[None] + [k for k, it in p.items.items() if s in it.allowed_set] for s in slots]
    n_valid = 0
    for assignment in itertools.product(*owners):
        candidate: dict[str, list[int]] = {k: [] for k in p.items}
        for s, key in zip(slots, assignment, strict=True):
            if key is not None:
                candidate[key].append(s)
        as_plan = {k: tuple(v) for k, v in candidate.items()}
        valid = independent_validity(p, as_plan)
        assert valid == (check(p, as_plan) == []), as_plan
        n_valid += valid
    assert n_valid > 0


@pytest.mark.parametrize("seed", range(8))
def test_brute_force_optimum_ties_or_beats_every_valid_plan(seed: int) -> None:
    p = tiny(seed, 6, 2).build()
    result = brute_force(p)
    rng = np.random.default_rng(seed)
    for _ in range(40):
        candidate = random_plan(p, rng, rng.random())
        if not check(p, candidate):
            assert evaluate(p, candidate).lex() >= result.best.lex()
    assert all(check(p, best) == [] for best in result.plans)


def test_brute_force_refuses_large_instances() -> None:
    with pytest.raises(ValueError):
        brute_force(reference_instance(20, 0).build())
