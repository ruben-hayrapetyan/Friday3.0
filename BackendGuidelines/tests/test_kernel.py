"""The compiled energy must equal the shared evaluator, and its violation counts the checker, after any moves."""
from __future__ import annotations

import numpy as np
import pytest

from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance, tiny
from fr.core.plans import random_plan
from fr.engines.compile import compile_problem
from fr.engines.kernel import N_MOVES, init_state, item_viol, new_state, propose, set_owner, undo, add_touched_dependents, \
    total_violations
from fr.core.settings import STAGES


def stage_vector(ev):
    return [ev.stage_values[s] for s in STAGES]


def viol_counts(problem, plan):
    out = {}
    for v in check(problem, plan):
        out[v.key] = out.get(v.key, 0) + 1
    return out


def make(sc, seed=0, fill=0.3):
    p = sc.build()
    c = compile_problem(p)
    rng = np.random.default_rng(seed)
    plan = random_plan(p, rng, fill)
    st = new_state(c.m)
    init_state(c.m, st, c.owner_from_plan(plan))
    return p, c, st


def assert_matches(p, c, st):
    plan = c.plan_from_owner(st.owner)
    ev = evaluate(p, plan)
    assert list(st.sv) == stage_vector(ev)
    got = {c.keys[i]: int(st.vitem[i]) for i in range(c.m.I) if st.vitem[i]}
    want = {k: n for k, n in viol_counts(p, plan).items() if not k.startswith("d")}
    assert got == want
    day = sum(1 for v in check(p, plan) if v.code == "day_cap")
    assert total_violations(c.m, st) == sum(want.values()) + day


@pytest.mark.parametrize("name,sc", [("ref20", lambda: reference_instance(20, 3)), ("cornell", lambda: cornell_semester(1)),
                                     ("ref40", lambda: reference_instance(40, 1))])
def test_initial_energy_matches_evaluator(name, sc):
    p, c, st = make(sc())
    assert_matches(p, c, st)


@pytest.mark.parametrize("seed", range(3))
def test_random_moves_keep_energy_and_violations_exact(seed):
    p, c, st = make(reference_instance(30, seed), seed, 0.25)
    np.random.seed(seed)
    touched = np.zeros(64, dtype=np.int64)
    fired = np.zeros(N_MOVES, dtype=int)
    prot = np.zeros(c.m.I, dtype=bool)
    for step in range(600):
        kx = step % N_MOVES
        st.ctr[0] = 0
        n = propose(c.m, st, prot, kx, touched)
        if n:
            fired[kx] += 1
            n = add_touched_dependents(c.m, touched, n)
            for k in range(n):
                st.vitem[touched[k]] = item_viol(c.m, st, touched[k])
            st.ctr[1] = int(st.vitem.sum())
        if step % 50 == 0:
            assert_matches(p, c, st)
    assert_matches(p, c, st)
    assert fired.min() > 0, fired  # every move type actually ran


def test_undo_restores_everything():
    p, c, st = make(reference_instance(20, 5), 5, 0.3)
    before = (st.owner.copy(), st.sv.copy(), st.mval.copy(), st.placed.copy(), st.dayu.copy(), st.cnt.copy())
    touched = np.zeros(64, dtype=np.int64)
    np.random.seed(1)
    for kx in range(N_MOVES * 20):
        st.ctr[0] = 0
        if propose(c.m, st, np.zeros(c.m.I, dtype=bool), kx % N_MOVES, touched):
            undo(c.m, st)
    after = (st.owner, st.sv, st.mval, st.placed, st.dayu, st.cnt)
    for a, b in zip(before, after):
        assert (a == b).all()
