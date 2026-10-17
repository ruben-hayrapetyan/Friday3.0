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
