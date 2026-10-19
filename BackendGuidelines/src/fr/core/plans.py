"""Plan helpers: random plans for tests and as sampler starting points."""
from __future__ import annotations

import numpy as np

from .problem import Problem


def random_plan(problem: Problem, rng: np.random.Generator, fill: float = 0.5, prefer_energy: str | None = None) -> dict[str, tuple[int, ...]]:
    """Each allowed slot goes to a random eligible item with probability `fill`; locks are always kept.
    With `prefer_energy`, items of that energy are chosen whenever one is eligible.

    Not guaranteed valid (chunk and dependency rules are ignored): it exercises the evaluator, not the checker.
    """
    g = problem.grid
    owner: dict[int, str] = dict(problem.lock_owner)
    by_slot: dict[int, list[str]] = {}
    for it in problem.items.values():
        for s in it.allowed:
            by_slot.setdefault(s, []).append(it.key)
    for s, keys in by_slot.items():
        if s in owner or rng.random() > fill:
            continue
        pool = [k for k in keys if problem.items[k].energy == prefer_energy] or keys if prefer_energy else keys
        owner[s] = pool[int(rng.integers(0, len(pool)))]
    plan: dict[str, list[int]] = {k: [] for k in problem.items}
    for s, k in owner.items():
        plan[k].append(s)
    return {k: tuple(sorted(v)) for k, v in plan.items()}
