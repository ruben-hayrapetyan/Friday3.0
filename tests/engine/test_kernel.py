"""The kernel's energy equals the evaluator and its violation counts equal the checker, after any moves."""

import numpy as np
import pytest

from friday.engine.compile import compile_problem
from friday.engine.evaluate import evaluate
from friday.engine.kernel import N_MOVES, init_state, new_state, rule_totals, seed_rng, undo
from friday.engine.moves import propose
from friday.engine.rules import RULE_TYPES
from tests.engine.golden import plan_of, problem, read
from tests.engine.instances import VARIANTS, single_rule, variant
from tests.engine.kernel_check import assert_kernel_matches, random_moves
from tests.engine.plans import random_plan

GOLDEN = ["ref20-s1", "ref60-s0", "cornell-extra-s0", "cornell-mixed", "deps-s0", "onesit-s0", "pins-s1",
          "tight-s0", "fragmented-s0", "overload-s1", "ref30-extra-current"]  # fmt: skip
FIRED = np.zeros(N_MOVES, dtype=int)


def compiled_with_plan(name: str, seed: int, fill: float):
    p = problem(read(name))
    c = compile_problem(p)
    st = new_state(c.m)
    init_state(c.m, st, c.owner_from_plan(random_plan(p, np.random.default_rng(seed), fill)))
    return c, st


@pytest.mark.parametrize("name", GOLDEN)
def test_initial_energy_matches_the_evaluator(name: str) -> None:
    c, st = compiled_with_plan(name, 0, 0.3)
    assert_kernel_matches(c, st)


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_plans_load_with_the_research_values(name: str) -> None:
    fixture = read(name)
    p = problem(fixture)
    c = compile_problem(p)
    for raw in fixture["plans"]:
        st = new_state(c.m)
        init_state(c.m, st, c.owner_from_plan(plan_of(raw, p)))
        assert list(st.stage_value) == [raw["stage_values"][s] for s in ("deadlines", "wellbeing", "preferences")]
        assert int(st.counters[1]) == 0


@pytest.mark.parametrize("name", GOLDEN)
@pytest.mark.parametrize("seed", [0, 1])
def test_random_moves_keep_energy_and_violations_exact(name: str, seed: int) -> None:
    c, st = compiled_with_plan(name, seed, 0.25)
    FIRED[:] += random_moves(c, st, 1500, seed)


def compiled_random(p, seed: int, fill: float):
    c = compile_problem(p)
    st = new_state(c.m)
    init_state(c.m, st, c.owner_from_plan(random_plan(p, np.random.default_rng(seed), fill)))
    return c, st


@pytest.mark.parametrize("name", VARIANTS)
def test_random_moves_stay_exact_on_dst_dial_and_theta_variants(name: str) -> None:
    c, st = compiled_random(variant(name), 1, 0.25)
    FIRED[:] += random_moves(c, st, 1000, 1, check_every=100)


@pytest.mark.parametrize("rule_type", sorted(RULE_TYPES))
def test_random_moves_stay_exact_with_each_rule_alone(rule_type: str) -> None:
    p = single_rule(rule_type)
    c, st = compiled_random(p, 2, 0.3)
    assert c.m.M > 0 or any(r.has_price for r in p.rules)
    FIRED[:] += random_moves(c, st, 1000, 2, check_every=100)


def test_every_move_kind_ran() -> None:
    assert FIRED.min() > 0, FIRED


def test_undo_restores_everything() -> None:
    c, st = compiled_with_plan("ref20-s1", 5, 0.3)
    before = [a.copy() for a in (st.owner, st.stage_value, st.measure_value, st.placed, st.day_units, st.group_count)]
    touched = np.zeros(64, dtype=np.int64)
    seed_rng(1)
    for move in range(N_MOVES * 20):
        st.counters[0] = 0
        if propose(c.m, st, np.zeros(c.m.I, dtype=bool), move % N_MOVES, touched):
            undo(c.m, st)
    after = [st.owner, st.stage_value, st.measure_value, st.placed, st.day_units, st.group_count]
    for a, b in zip(before, after, strict=True):
        assert (a == b).all()


@pytest.mark.parametrize("name", ["ref30-extra-current", "cornell-easy"])
def test_rule_totals_match_the_evaluator(name: str) -> None:
    c, st = compiled_with_plan(name, 3, 0.3)
    M = c.m
    out = np.zeros(M.R, dtype=np.int64)
    work = (
        np.zeros(M.M, dtype=np.int64),
        np.zeros(max(M.G, 1), dtype=np.int64),
        np.zeros(M.I, dtype=np.int64),
    )
    rule_totals(M, st.owner, out, *work)
    ev = evaluate(c.problem, c.plan_from_owner(st.owner))
    assert {n: int(out[r]) for r, n in enumerate(c.rule_names)} == {n: ev.rule_totals.get(n, 0) for n in c.rule_names}
