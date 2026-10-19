"""Stage handling for the sampler: tiered (lexicographic) annealing and plain weighted sums."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, replace

import numpy as np

from ..engines.compile import Compiled
from ..engines.construct import construct
from .anneal import SAConfig, SAResult, anneal, protected

W_DEADLINE = 1e6


@dataclass
class TieredResult:
    owner: np.ndarray
    sv: tuple[int, int, int]
    seconds: float
    tiers: list[SAResult] = field(default_factory=list)
    violations: int = 0


def tiered(c: Compiled, owner0: np.ndarray | None = None, steps: tuple[int, int] = (500_000, 1_500_000), seed: int = 0,
           wall: bool = True, t0_scale: float = 0.1, t1_scale: float = 0.003, eps: float = 0.0,
           probs: np.ndarray | None = None) -> TieredResult:
    """Tier 1 minimises wellbeing; tier 2 minimises preferences with wellbeing capped at the tier-1 value.

    The deadline stage is a wall (protected items never get late); with wall=False it is a heavy weight instead.
    """
    t = time.perf_counter()
    owner = construct(c) if owner0 is None else owner0
    prot = protected(c, owner) if wall else None
    base = SAConfig(wall=wall, seed=seed, t0_scale=t0_scale, t1_scale=t1_scale)
    if probs is not None:
        base = replace(base, probs=probs)
    r1 = anneal(c, owner, replace(base, steps=steps[0], wts=np.array([W_DEADLINE, 1.0, eps])), prot)
    cap = (-1, r1.sv[1], -1)
    r2 = anneal(c, r1.owner, replace(base, steps=steps[1], wts=np.array([W_DEADLINE, 0.0, 1.0]), cap=cap, seed=seed + 1), prot)
    return TieredResult(r2.owner, r2.sv, time.perf_counter() - t, [r1, r2], r2.violations)
