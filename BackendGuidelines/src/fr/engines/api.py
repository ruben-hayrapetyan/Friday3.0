"""Engines behind one signature, so experiments compare them on equal wall-clock budgets.

Every engine takes an already `prepare`d problem (locks made consistent once, identically for all) and returns a plan;
the caller scores it with the shared evaluator and checker. Setup that is not search (compile, construct) counts
against the budget; numba JIT compilation does not, it is measured once by `warmup()` and reported separately.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

import numpy as np

from ..baseline.cpsat import GridModel, ModelInfeasible, SolveTimeout, solve
from ..baseline.lns import lns_polish
from ..core.problem import Problem
from ..samplers.anneal import SAConfig, anneal, protected
from ..samplers.tiered import W_DEADLINE
from .prepare import Prepared, prepare


@dataclass
class EngineResult:
    plan: dict
    seconds: float
    info: dict = field(default_factory=dict)


_WARM = {"s": None}


def warmup() -> float:
    """Compile every numba function once on a tiny instance; returns the seconds spent (JIT time, reported separately)."""
    if _WARM["s"] is not None:
        return _WARM["s"]
    from ..core.generate import reference_instance

    t = time.perf_counter()
    pr = prepare(reference_instance(20, 0).build())
    tiered_budget(pr, 0.5, 0)
    _WARM["s"] = time.perf_counter() - t
    return _WARM["s"]


def _rate(c, owner, prot, seed: int = 0, probe: int = 60_000) -> float:
    """Steps per second of the chain on this instance (a short probe run)."""
    r = anneal(c, owner, SAConfig(steps=probe, wts=np.array([W_DEADLINE, 1.0, 0.0]), seed=seed), prot)
    return probe / max(r.seconds, 1e-3)


def tiered_budget(pr: Prepared, budget_s: float, seed: int, wall: bool = True, split: float = 0.35,
                  start: np.ndarray | None = None, lam: float = 1e6, t0_scale: float = 0.1, t1_scale: float = 0.003,
                  probs: np.ndarray | None = None, stages: str = "tiered"):
    """Tiered annealing (wellbeing, then preferences under a wellbeing cap) for about `budget_s` seconds.
    stages="lexpolish": a weighted search first (E006), then the same capped preference polish."""
    t0 = time.perf_counter()
    c = pr.c
    owner = pr.owner if start is None else start
    prot = protected(c, owner) if wall else np.zeros(c.m.I, dtype=bool)
    rate = _rate(c, owner, prot, seed)
    left = max(0.05, budget_s - (time.perf_counter() - t0))
    n1, n2 = int(rate * left * split * 0.9), int(rate * left * (1 - split) * 0.9)
    base = SAConfig(wall=wall, seed=seed, lam=lam, t0_scale=t0_scale, t1_scale=t1_scale)
    if probs is not None:
        base = replace(base, probs=probs)
    if stages == "lexpolish":  # E006: search one weighted energy (stage ratio 1000), then polish under a wellbeing cap
        n1, n2 = int(rate * left * 0.6 * 0.9), int(rate * left * 0.4 * 0.9)
        w1 = np.array([W_DEADLINE, 1000.0, 1.0])
    else:
        w1 = np.array([W_DEADLINE, 1.0, 0.0])
    r1 = anneal(c, owner, replace(base, steps=max(n1, 1000), wts=w1), prot)
    cap = (-1, r1.sv[1], -1)
    r2 = anneal(c, r1.owner, replace(base, steps=max(n2, 1000), wts=np.array([W_DEADLINE, 0.0, 1.0]), cap=cap,
                                     seed=seed + 1), prot)
    plan = c.plan_from_owner(r2.owner)
    return plan, dict(rate=rate, steps=(n1, n2), violations=r2.violations, protected=int(prot.sum()))


def run_cpsat(p: Problem, pr: Prepared, budget_s: float, seed: int = 0, workers: int = 8, hint=None) -> EngineResult:
    t = time.perf_counter()
    p.settings.time_limit_s = budget_s
    p.settings.workers = workers
    p.settings.det_time = (budget_s * 3,) * 3
    try:
        res = solve(p, hint=hint, seed=seed)
        return EngineResult(res.plan, time.perf_counter() - t, dict(status="/".join(s.status for s in res.stages)))
    except (SolveTimeout, ModelInfeasible) as exc:
        plan = {k: tuple(sorted(it.locked)) for k, it in p.items.items()}  # no answer: the locks-only plan
        return EngineResult(plan, time.perf_counter() - t, dict(status=f"FAIL:{type(exc).__name__}"))


def run_wall_sa(p: Problem, pr: Prepared, budget_s: float, seed: int = 0) -> EngineResult:
    t = time.perf_counter()
    plan, info = tiered_budget(pr, budget_s - (time.perf_counter() - t), seed, wall=True)
    return EngineResult(plan, time.perf_counter() - t, info)


def run_potts_penalty(p: Problem, pr: Prepared, budget_s: float, seed: int = 0, lam: float = 1e6) -> EngineResult:
    """Same slot model and moves, hard rules as penalties instead of walls (deadlines are just a heavy stage)."""
    t = time.perf_counter()
    plan, info = tiered_budget(pr, budget_s, seed, wall=False, lam=lam)
    return EngineResult(plan, time.perf_counter() - t, info)


def run_skeleton_hybrid(p: Problem, pr: Prepared, budget_s: float, seed: int = 0, skeleton_s: float | None = None,
                        workers: int = 8) -> EngineResult:
    """CP-SAT solves the deadline stage only (the feasibility skeleton), the sampler does wellbeing and preferences."""
    t = time.perf_counter()
    skeleton_s = min(3.0, 0.3 * budget_s) if skeleton_s is None else skeleton_s
    p.settings.workers = workers
    p.settings.det_time = (skeleton_s * 3,) * 3
    info: dict = {}
    try:
        res = GridModel(p).solve(stages=["deadlines"], time_limit_s=skeleton_s, workers=workers, seed=seed)
        cand = pr.c.owner_from_plan(res.plan)
        info["skeleton_late"] = res.evaluation.stage_values["deadlines"]
        # a time-limited skeleton can be later than the construction (E004): keep the better start
        from .repair import late_value

        start = cand if late_value(pr, cand) < late_value(pr, pr.owner) else pr.owner
    except (SolveTimeout, ModelInfeasible):
        start = pr.owner
        info["skeleton_late"] = None
    plan, i2 = tiered_budget(pr, budget_s - (time.perf_counter() - t), seed, wall=True, start=start)
    info.update(i2)
    return EngineResult(plan, time.perf_counter() - t, info)


def run_sa_then_lns(p: Problem, pr: Prepared, budget_s: float, seed: int = 0, sa_share: float = 0.5,
                    workers: int = 8) -> EngineResult:
    t = time.perf_counter()
    plan, info = tiered_budget(pr, budget_s * sa_share, seed, wall=True)
    left = budget_s - (time.perf_counter() - t)
    plan, rounds, acc = lns_polish(p, plan, left, seed=seed, workers=workers)
    info.update(lns_rounds=rounds, lns_accepted=acc)
    return EngineResult(plan, time.perf_counter() - t, info)


ENGINES = {
    "cpsat": run_cpsat,
    "wall_sa": run_wall_sa,
    "potts_penalty": run_potts_penalty,
    "skeleton_hybrid": run_skeleton_hybrid,
    "sa_lns": run_sa_then_lns,
}


def run_v3(p: Problem, pr: Prepared, budget_s: float, seed: int = 0, fallback_s: float = 5.0,
           small_items: int = 60) -> EngineResult:
    """The recommended pipeline after E018: construction -> sampler repair -> the wall sampler (lexpolish) for the budget;
    only if lateness is left, CP-SAT's deadline stage hinted with that plan, then a short polish of whichever is less late.
    (E018's first version ran CP-SAT before annealing; on 150-item instances it used the whole budget and helped nothing.
    E018b: on small packed instances the opposite order is better, so instances up to `small_items` items run CP-SAT first.)"""
    from .repair import ensure_deadlines, late_value

    t = time.perf_counter()
    if len(p.items) <= small_items:  # E018b: on small packed instances an exact deadline solve first is best
        rep = ensure_deadlines(pr, seed=seed, use_cpsat=True, cpsat_s=fallback_s)
        plan, info = tiered_budget(pr, max(0.5, budget_s - (time.perf_counter() - t)), seed, start=rep.owner,
                                   stages="lexpolish")
        info.update(repair_late=rep.late, fallback=f"first:{rep.stage}")
        return EngineResult(plan, time.perf_counter() - t, info)
    rep = ensure_deadlines(pr, seed=seed, use_cpsat=False)
    plan, info = tiered_budget(pr, max(0.5, budget_s - (time.perf_counter() - t)), seed, start=rep.owner, stages="lexpolish")
    owner = pr.c.owner_from_plan(plan)
    late = late_value(pr, owner)
    info.update(repair_late=rep.late, after_sampler_late=late, fallback="none")
    if late > 0:
        try:
            p.settings.workers = 8
            p.settings.det_time = (fallback_s * 3,) * 3
            res = GridModel(p).solve(stages=["deadlines"], time_limit_s=fallback_s / 0.4, workers=8, hint=plan, seed=seed)
            cand = pr.c.owner_from_plan(res.plan)
            if late_value(pr, cand) < late:
                plan, _ = tiered_budget(pr, 1.0, seed + 1, start=cand, stages="lexpolish")
                info["fallback"] = "cpsat"
        except (SolveTimeout, ModelInfeasible):
            info["fallback"] = "cpsat-failed"
    return EngineResult(plan, time.perf_counter() - t, info)


ENGINES["v3"] = run_v3
