"""Large-neighbourhood search on top of any plan: free a few items, lock the rest, let CP-SAT re-optimise exactly.

This is the "sampler proposes, small exact solve repairs" hybrid: the proposal is a random set of items to
reopen; the exact solve works on a model that is small because everything else is locked.
"""
from __future__ import annotations

import copy
import time

import numpy as np

from ..core.builder import prune
from ..core.evaluate import check, evaluate
from ..core.problem import Problem
from .cpsat import GridModel, ModelInfeasible, SolveTimeout


def neighbourhood_problem(problem: Problem, plan, free: set[str]) -> Problem:
    sub = copy.deepcopy(problem)
    for k, it in sub.items.items():
        if k in free:
            it.locked = frozenset(s for s in it.locked)
        else:
            it.locked = frozenset(plan.get(k, ()))
    sub.lock_owner = {s: it.key for it in sub.items.values() for s in it.locked}
    sub._price_cache.clear()
    prune(sub)
    for k, it in sub.items.items():
        if k not in free:
            it.set_allowed(list(it.locked))
    return sub


def lns_polish(problem: Problem, plan, seconds: float, k_free: int = 6, per_round_s: float = 2.0, seed: int = 0,
               workers: int = 8):
    """Repeat neighbourhood solves until the time is up; returns (plan, rounds, accepted)."""
    rng = np.random.default_rng(seed)
    t0 = time.perf_counter()
    best = dict(plan)
    best_lex = evaluate(problem, best).lex()
    keys = [k for k, it in problem.items.items() if not (it.locked and len(it.locked) == len(it.allowed))]
    rounds = accepted = 0
    while time.perf_counter() - t0 < seconds - per_round_s * 0.5 and keys:
        free = set(rng.choice(keys, size=min(k_free, len(keys)), replace=False).tolist())
        sub = neighbourhood_problem(problem, best, free)
        rounds += 1
        try:
            res = GridModel(sub).solve(hint=best, time_limit_s=per_round_s, workers=workers)
        except (ModelInfeasible, SolveTimeout):
            continue
        cand = res.plan
        if check(problem, cand):
            continue
        lex = evaluate(problem, cand).lex()
        if lex < best_lex:
            best, best_lex = dict(cand), lex
            accepted += 1
    return best, rounds, accepted
