"""The checker must accept exactly the plans an independent reading of the hard rules accepts."""
import itertools

import numpy as np
import pytest

from fr.core.brute import brute_force
from fr.core.evaluate import check, evaluate
from fr.core.generate import tiny


def reference_valid(p, plan) -> bool:
    """Hard rules re-derived from ENGINE_REFERENCE 6A.4 with 0/1 strings per item (not the checker's code)."""
    g = p.grid
    n = g.S
    bits = {k: [1 if s in set(plan.get(k, ())) else 0 for s in range(n)] for k in p.items}
    for s in range(n):
        if sum(bits[k][s] for k in p.items) > 1:  # C1
            return False
    for k, it in p.items.items():
        b = bits[k]
        placed = sum(g.units[s] for s in range(n) if b[s])
        if any(b[s] and s not in it.allowed_set for s in range(n)):
            return False
        if any(s in it.locked and not b[s] for s in range(n)):  # C4
            return False
        if it.amount == "fixed" and placed > it.need:  # C2 (tightened: +1 only through a coarse slot)
            if placed > it.need + 1 or not any(g.units[s] > 1 for s in range(n) if b[s]):
                return False
        if it.amount == "elastic" and placed > it.max:
            return False
        if it.amount == "target" and placed > it.cap:
            return False
        if it.amount == "open":
            for d in range(g.n_days):
                if sum(g.units[s] for s in g.day_slots[d] if b[s]) > it.daily_ceiling - (it.progress_today if d == 0 else 0):
                    return False
        starts = [s for s in range(n) if b[s] and (s == 0 or not b[s - 1])]
        if it.shape == "one_sitting":  # C6
            if len(starts) > 1 or (it.amount == "fixed" and 0 < placed < it.need):
                return False
        for s in starts:  # C7 min chunk: slots from s must cover min_chunk units
            need, j, units = it.min_chunk, s, 0
            while units < need:
                if j >= n or not b[j]:
                    return False
                units += int(g.units[j])
                j += 1
        if it.max_chunk is not None:  # any run longer than max_chunk
            run = 0
            for s in range(n):
                run = run + int(g.units[s]) if b[s] else 0
                if run > it.max_chunk:
                    return False
    for d in range(g.n_days):
        if sum(g.units[s] for s in range(n) if g.slots[s].day == d and any(bits[k][s] for k in p.items)) > p.day_caps[d]:
            return False
    return True


@pytest.mark.parametrize("seed", range(12))
def test_checker_matches_independent_validity_on_every_assignment(seed):
    sc = tiny(seed, 7, 3)
    p = sc.build()
    slots = sorted({s for it in p.items.values() for s in it.allowed})
    owners = [[None] + [k for k, it in p.items.items() if s in it.allowed_set] for s in slots]
    n_valid = 0
    for assign in itertools.product(*owners):
        plan = {k: [] for k in p.items}
        for s, k in zip(slots, assign):
            if k is not None:
                plan[k].append(s)
        plan = {k: tuple(v) for k, v in plan.items()}
        ok = reference_valid(p, plan)
        assert ok == (check(p, plan) == []), plan
        n_valid += ok
    assert n_valid > 0


@pytest.mark.parametrize("seed", range(8))
def test_brute_force_optimum_beats_or_ties_every_valid_plan(seed):
    p = tiny(seed, 6, 2).build()
    res = brute_force(p)
    rng = np.random.default_rng(seed)
    from fr.core.plans import random_plan
    for _ in range(40):
        plan = random_plan(p, rng, rng.random())
        if not check(p, plan):
            assert evaluate(p, plan).lex() >= res.best.lex()
    assert all(check(p, pl) == [] for pl in res.plans)


def test_brute_force_refuses_large_instances():
    from fr.core.generate import reference_instance

    with pytest.raises(ValueError):
        brute_force(reference_instance(20, 0).build())
