"""Sampler guarantees: valid plans, deadline walls that hold, determinism, energies equal to the evaluator."""
from __future__ import annotations

import numpy as np
import pytest

from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, many_deps, many_one_sitting, reference_instance, tight_deadlines
from fr.engines.prepare import prepare
from fr.samplers.anneal import protected
from fr.samplers.tiered import tiered

FAMILIES = [lambda s: reference_instance(20, s), cornell_semester, tight_deadlines, many_deps, many_one_sitting]


@pytest.mark.parametrize("make", FAMILIES)
@pytest.mark.parametrize("seed", [0, 1])
def test_constructed_start_is_valid(make, seed):
    pr = prepare(make(seed).build())
    assert pr.violations == 0
    assert not check(pr.c.problem, pr.c.plan_from_owner(pr.owner))


@pytest.mark.parametrize("make", FAMILIES)
def test_tiered_anneal_keeps_every_hard_guarantee(make):
    p = make(2).build()
    pr = prepare(p)
    prot = protected(pr.c, pr.owner)
    r = tiered(pr.c, pr.owner, steps=(30_000, 60_000), seed=3)
    plan = pr.c.plan_from_owner(r.owner)
    assert check(p, plan) == []
    ev = evaluate(p, plan)
    assert list(r.sv) == list(ev.lex())  # kernel energy == shared evaluator
    # every item that was on time at the start is still complete and on time
    for i in np.flatnonzero(prot):
        key = pr.c.keys[i]
        assert key not in ev.deadline_misses


def test_same_seed_same_plan_and_other_seed_other_plan():
    pr = prepare(reference_instance(20, 4).build())
    a = tiered(pr.c, pr.owner, steps=(20_000, 40_000), seed=7)
    b = tiered(pr.c, pr.owner, steps=(20_000, 40_000), seed=7)
    c = tiered(pr.c, pr.owner, steps=(20_000, 40_000), seed=8)
    assert (a.owner == b.owner).all()
    assert not (a.owner == c.owner).all()


def test_why_not_is_the_exact_evaluator_difference():
    from fr.engines.explain import per_rule, why_not

    p = reference_instance(20, 1).build()
    pr = prepare(p)
    owner = pr.owner
    ev0 = evaluate(p, pr.c.plan_from_owner(owner))
    assert per_rule(pr.c, owner) == {k: ev0.rule_totals.get(k, 0) for k in pr.c.rule_names}
    slots = [s for s in range(len(owner)) if owner[s] >= 0 and not pr.c.m.locked[owner[s], s]]
    checked = 0
    for s in slots[:: max(1, len(slots) // 60)]:
        for shift in (-8, 4, 40, 300):
            w = why_not(pr.c, owner, s, s + shift)
            if not w.delta:
                continue
            from fr.engines.kernel import init_state, new_state, relocate, run_around
            st = new_state(pr.c.m)
            init_state(pr.c.m, st, owner)
            i = int(owner[s])
            a, b = run_around(pr.c.m, st, s)
            relocate(pr.c.m, st, np.zeros(pr.c.m.I, dtype=bool), i, a, b, s + shift, np.zeros(64, dtype=np.int64))
            ev1 = evaluate(p, pr.c.plan_from_owner(st.owner))
            assert w.total == ev1.total - ev0.total
            assert w.valid == (check(p, pr.c.plan_from_owner(st.owner)) == [])
            checked += 1
    assert checked >= 10


def test_parallel_runs_do_not_depend_on_thread_count():
    from fr.samplers.chains import Spec, multistart, parallel_tempering

    pr = prepare(reference_instance(20, 6).build())
    prot = protected(pr.c, pr.owner)
    spec = Spec(np.array([1e6, 1.0, 0.0]))
    temps = np.array([2.0, 6.0, 20.0, 60.0])
    a = parallel_tempering(pr.c, pr.owner, prot, spec, temps, 5, 2000, seed=3, threads=1)[0]
    b = parallel_tempering(pr.c, pr.owner, prot, spec, temps, 5, 2000, seed=3, threads=4)[0]
    assert (a == b).all()
    c = multistart(pr.c, pr.owner, prot, spec, 4, 5000, 50.0, 1.0, seed=3, threads=1)[0]
    d = multistart(pr.c, pr.owner, prot, spec, 4, 5000, 50.0, 1.0, seed=3, threads=4)[0]
    assert (c == d).all()
