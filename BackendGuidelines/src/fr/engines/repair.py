"""Getting to zero late work: construct, then a repair run of the sampler on the deadline stage alone, then CP-SAT.

The sampler repair uses the same moves with hard rules as penalties (it may pass through infeasible states), minimising
only the deadline stage; the best violation-free state wins. CP-SAT stage 1 is the last resort.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..baseline.cpsat import GridModel, ModelInfeasible, SolveTimeout
from ..samplers.anneal import SAConfig, anneal
from .kernel import init_state, new_state
from .prepare import Prepared


@dataclass
class Repaired:
    owner: np.ndarray
    late: int
    stage: str  # construct | sampler | cpsat
    seconds: float


def late_value(pr: Prepared, owner: np.ndarray) -> int:
    st = new_state(pr.c.m)
    init_state(pr.c.m, st, owner)
    return int(st.sv[0])


def ensure_deadlines(pr: Prepared, seed: int = 0, steps: int = 400_000, cpsat_s: float = 5.0, workers: int = 8,
                     use_cpsat: bool = True) -> Repaired:
    t = time.perf_counter()
    late = late_value(pr, pr.owner)
    if late == 0:
        return Repaired(pr.owner, 0, "construct", time.perf_counter() - t)
    cfg = SAConfig(steps=steps, wall=False, lam=1e9, wts=np.array([1.0, 0.0, 0.0]), t0_scale=0.3, t1_scale=0.003, seed=seed)
    r = anneal(pr.c, pr.owner, cfg, np.zeros(pr.c.m.I, dtype=bool))
    owner, late = (r.owner, r.sv[0]) if r.sv[0] < late and r.violations == 0 else (pr.owner, late)
    if late == 0 or not use_cpsat:
        return Repaired(owner, int(late), "sampler", time.perf_counter() - t)
    try:
        p = pr.c.problem
        p.settings.workers = workers
        p.settings.det_time = (cpsat_s * 3,) * 3
        res = GridModel(p).solve(stages=["deadlines"], time_limit_s=cpsat_s, workers=workers, hint=pr.c.plan_from_owner(owner))
        cand = pr.c.owner_from_plan(res.plan)
        cl = late_value(pr, cand)
        if cl < late:
            owner, late = cand, cl
    except (SolveTimeout, ModelInfeasible):
        pass
    return Repaired(owner, int(late), "cpsat", time.perf_counter() - t)
