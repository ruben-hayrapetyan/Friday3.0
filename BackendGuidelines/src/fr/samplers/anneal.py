"""Simulated annealing over the compiled energy: walls (reject infeasible moves) or penalties."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..engines.compile import Compiled
from ..engines.construct import construct
from ..engines.kernel import N_MOVES, init_state, new_state, run_chain, sample_deltas, seed_rng, total_violations

DEFAULT_PROBS = np.array([3.0, 1.0, 1.0, 0.5, 1.0, 1.0, 1.0, 1.5, 1.0, 0.3])
LEX = np.array([1e6, 1e3, 1.0])  # deadlines >> wellbeing >> preferences, as plain weights


@dataclass
class SAConfig:
    steps: int = 200_000
    t0: float | None = None  # None: calibrated from sampled move deltas
    t1: float | None = None
    t0_scale: float = 1.0  # multiples of the median |delta| when calibrated
    t1_scale: float = 0.01
    wall: bool = True
    lam: float = 1e6
    wts: np.ndarray = field(default_factory=lambda: LEX.copy())
    cap: tuple[int, int, int] = (-1, -1, -1)
    probs: np.ndarray = field(default_factory=lambda: DEFAULT_PROBS.copy())
    seed: int = 0


@dataclass
class SAResult:
    owner: np.ndarray
    sv: tuple[int, int, int]
    energy: float
    violations: int
    seconds: float
    stats: np.ndarray
    t0: float
    t1: float
    best_step: int


def protected(c: Compiled, owner: np.ndarray) -> np.ndarray:
    """Hard-deadline items that are complete and on time in `owner`: the wall keeps them that way."""
    M = c.m
    prot = np.zeros(M.I, dtype=bool)
    placed = np.zeros(M.I, dtype=np.int64)
    ok = np.ones(M.I, dtype=bool)
    for s in range(M.S):
        i = owner[s]
        if i >= 0:
            placed[i] += M.units[s]
            if not M.wall_ok[i, s]:
                ok[i] = False
    for i in range(M.I):
        prot[i] = bool(M.hard_due[i]) and ok[i] and placed[i] >= M.need[i]
    return prot


def calibrate(c: Compiled, owner: np.ndarray, prot: np.ndarray, cfg: SAConfig, n: int = 3000) -> tuple[float, float]:
    st = new_state(c.m)
    init_state(c.m, st, owner)
    out = np.zeros((n, 3), dtype=np.int64)
    k = sample_deltas(c.m, st, prot, np.asarray(cfg.wts, dtype=np.float64), np.cumsum(cfg.probs), np.zeros(64, dtype=np.int64),
                      np.zeros(64, dtype=np.int64), n, cfg.seed + 7919, out)
    out = out[:k]
    w = np.asarray(cfg.wts, dtype=np.float64)
    live = out[out[:, 0] == 0] if w[0] >= 1e5 else out  # moves that touch a walled stage do not set the scale
    d = np.abs(live[:, 1:] @ w[1:])
    d = d[d > 0]
    med = float(np.median(d)) if len(d) else 1.0
    return med * cfg.t0_scale, med * cfg.t1_scale


def anneal(c: Compiled, owner0: np.ndarray | None = None, cfg: SAConfig | None = None,
           prot: np.ndarray | None = None) -> SAResult:
    cfg = cfg or SAConfig()
    owner0 = construct(c) if owner0 is None else owner0
    if prot is None:
        prot = protected(c, owner0) if cfg.wall else np.zeros(c.m.I, dtype=bool)
    t0, t1 = cfg.t0, cfg.t1
    if t0 is None or t1 is None:
        c0, c1 = calibrate(c, owner0, prot, cfg)
        t0 = c0 if t0 is None else t0
        t1 = c1 if t1 is None else t1
    st = new_state(c.m)
    init_state(c.m, st, owner0)
    best = owner0.copy()
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    info = np.full(3, np.inf)
    t = time.perf_counter()
    e = run_chain(c.m, st, prot, np.asarray(cfg.wts, dtype=np.float64), np.array(cfg.cap, dtype=np.int64),
                  np.cumsum(cfg.probs), np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64),
                  cfg.steps, float(t0), float(t1), 1 if cfg.wall else 0, float(cfg.lam), cfg.seed, best, stats, info)
    dt = time.perf_counter() - t
    bst = new_state(c.m)
    init_state(c.m, bst, best)
    return SAResult(best, tuple(int(x) for x in bst.sv), float(info[0]), int(total_violations(c.m, bst)), dt, stats,
                    float(t0), float(t1), int(info[1]) if np.isfinite(info[1]) else -1)
