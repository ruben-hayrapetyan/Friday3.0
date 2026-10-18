"""The v3 planner with a fixed step budget (deterministic regardless of machine load; decision 20).

Same pipeline as `engines.api.run_v3` (construction -> sampler repair -> CP-SAT deadline fallback on small instances ->
lexpolish annealing), but with step counts instead of seconds, which is what a shipped engine and the simulations need.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from ..core.problem import Problem
from ..engines.prepare import Prepared, prepare
from ..engines.repair import ensure_deadlines
from ..samplers.anneal import SAConfig, anneal, protected
from ..samplers.tiered import W_DEADLINE

LEXPOLISH = (np.array([W_DEADLINE, 1000.0, 1.0]), np.array([W_DEADLINE, 0.0, 1.0]))


def polish(pr: Prepared, start: np.ndarray, steps: tuple[int, int], seed: int, wts1: np.ndarray | None = None,
           wts2: np.ndarray | None = None) -> np.ndarray:
    """Weighted search (wellbeing x1000 + preferences), then a preference polish that may not raise wellbeing."""
    c = pr.c
    prot = protected(c, start)
    base = SAConfig(wall=True, seed=seed, lam=1e6, t0_scale=0.1, t1_scale=0.003)
    r1 = anneal(c, start, replace(base, steps=steps[0], wts=LEXPOLISH[0] if wts1 is None else wts1), prot)
    r2 = anneal(c, r1.owner, replace(base, steps=steps[1], wts=LEXPOLISH[1] if wts2 is None else wts2,
                                     cap=(-1, r1.sv[1], -1), seed=seed + 1), prot)
    return r2.owner


def plan(p: Problem, steps: tuple[int, int] = (150_000, 100_000), seed: int = 0, cpsat_s: float = 2.0,
         small_items: int = 60) -> tuple[Prepared, np.ndarray, dict]:
    pr = prepare(p)
    rep = ensure_deadlines(pr, seed=seed, steps=200_000, use_cpsat=len(p.items) <= small_items, cpsat_s=cpsat_s)
    owner = polish(pr, rep.owner, steps, seed)
    return pr, owner, dict(repair=rep.stage, repair_late=rep.late)
