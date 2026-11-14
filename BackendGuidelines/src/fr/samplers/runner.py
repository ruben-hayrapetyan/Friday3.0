"""Tiered optimisation with any sampler from `chains`, on a wall-clock budget.

Tier 1 minimizes wellbeing (deadlines are a wall), tier 2 minimizes preferences with wellbeing capped at the tier-1
value. Temperatures are calibrated per tier from the median |energy change| of random valid moves.
"""
from __future__ import annotations

import time

import numpy as np

from ..engines.prepare import Prepared
from .anneal import SAConfig, calibrate, protected
from .chains import (CONSTANT, GEOMETRIC, HEATBATH, LINEAR, METROPOLIS, Replica, Spec, multistart,
                     parallel_tempering, population_annealing, run, run_tabu)
from .tiered import W_DEADLINE

METHODS = ("sa_geo", "sa_lin", "fixed_T", "greedy", "heatbath", "pt1", "pt8", "pa8", "ms8", "sa_tabu")


def rate(pr: Prepared, prot, seed: int = 0, probe: int = 50_000) -> float:
    rep = Replica.make(pr.c, pr.owner)
    t = time.perf_counter()
    run(pr.c, rep, prot, Spec(np.array([W_DEADLINE, 1.0, 0.0])), probe, 50.0, 1.0, seed)
    return probe / max(1e-3, time.perf_counter() - t)


def _tier(pr: Prepared, owner: np.ndarray, prot, spec: Spec, method: str, steps: int, seed: int, t0s: float = 0.1,
          t1s: float = 0.003) -> np.ndarray:
    c = pr.c
    med, _ = calibrate(c, owner, prot, SAConfig(wts=spec.wts, t0_scale=1.0, seed=seed, probs=spec.probs), n=1500)
    T0, T1 = t0s * med, t1s * med
    if method in ("sa_geo", "sa_lin", "heatbath", "greedy", "fixed_T", "sa_tabu"):
        rep = Replica.make(c, owner)
        sched = LINEAR if method == "sa_lin" else GEOMETRIC
        acc = HEATBATH if method == "heatbath" else METROPOLIS
        if method == "greedy":
            run(c, rep, prot, spec, steps, 0.0, 0.0, seed, CONSTANT)
        elif method == "fixed_T":
            Tm = float(np.sqrt(T0 * T1))  # one moderate temperature, no annealing
            run(c, rep, prot, spec, steps, Tm, Tm, seed, CONSTANT)
        elif method == "sa_tabu":
            run(c, rep, prot, spec, int(steps * 0.8), T0, T1, seed, sched, acc)
            run_tabu(c, rep, prot, spec, max(1, int(steps * 0.2) // 25), 25, 8, seed + 3)
        else:
            run(c, rep, prot, spec, steps, T0, T1, seed, sched, acc)
        return rep.best.copy()
    if method in ("pt1", "pt8"):
        n_rep, rounds = 8, 40
        temps = T1 * (T0 / T1) ** (np.arange(n_rep) / (n_rep - 1))
        per = max(100, steps // rounds) if method == "pt8" else max(100, steps // (rounds * n_rep))
        best, _, _, _ = parallel_tempering(c, owner, prot, spec, temps, rounds, per, seed,
                                           threads=8 if method == "pt8" else 1, anneal_ladder=0.97)
        return best
    if method == "pa8":
        n_pop, n_t = 32, 20
        per = max(100, (steps * 8) // (n_pop * n_t))
        best, _, _ = population_annealing(c, owner, prot, spec, n_pop, T0, T1, n_t, per, seed, threads=8)
        return best
    if method == "ms8":
        best, _, _ = multistart(c, owner, prot, spec, 8, steps, T0, T1, seed, threads=8)
        return best
    raise KeyError(method)


def solve_sampler(pr: Prepared, budget_s: float, method: str = "sa_geo", seed: int = 0, start: np.ndarray | None = None,
                  split: float = 0.35, steps_per_s: float | None = None, probs: np.ndarray | None = None,
                  prot: np.ndarray | None = None, t0s: float = 0.1, t1s: float = 0.003) -> tuple[np.ndarray, dict]:
    """`steps` are sized for single-thread wall clock; the 8-thread methods use 8x the steps in the same time."""
    t = time.perf_counter()
    owner = pr.owner if start is None else start
    prot = protected(pr.c, owner) if prot is None else prot
    kw = {} if probs is None else dict(probs=np.asarray(probs, dtype=np.float64))
    r = steps_per_s or rate(pr, prot, seed)
    left = max(0.05, budget_s - (time.perf_counter() - t)) * 0.85  # calibration of each tier takes a little
    n1, n2 = int(r * left * split), int(r * left * (1 - split))
    o1 = _tier(pr, owner, prot, Spec(np.array([W_DEADLINE, 1.0, 0.0]), **kw), method, n1, seed, t0s, t1s)
    wb = int(_stage(pr, o1, 1))
    o2 = _tier(pr, o1, prot, Spec(np.array([W_DEADLINE, 0.0, 1.0]), cap=(-1, wb, -1), **kw), method, n2, seed + 1, t0s, t1s)
    return o2, dict(rate=r, steps=(n1, n2), seconds=time.perf_counter() - t)


def _stage(pr: Prepared, owner: np.ndarray, k: int) -> int:
    from ..engines.kernel import init_state, new_state

    st = new_state(pr.c.m)
    init_state(pr.c.m, st, owner)
    return int(st.sv[k])
