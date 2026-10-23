"""Random plans for tests: they exercise the evaluator and the kernel, not the checker."""

import numpy as np

from friday.engine.problem import Problem


def random_plan(problem: Problem, rng: np.random.Generator, fill: float = 0.5,
                prefer_energy: str | None = None) -> dict[str, tuple[int, ...]]:  # fmt: skip
    """Each allowed slot goes to a random eligible item with probability `fill`; locks are always kept.

    Not valid in general (chunk and dependency rules are ignored), on purpose.
    """
    owner: dict[int, str] = dict(problem.lock_owner)
    candidates: dict[int, list[str]] = {}
    for item in problem.items.values():
        for s in item.allowed:
            candidates.setdefault(s, []).append(item.key)
    for s, keys in candidates.items():
        if s in owner or rng.random() > fill:
            continue
        pool = keys
        if prefer_energy:
            pool = [k for k in keys if problem.items[k].energy == prefer_energy] or keys
        owner[s] = pool[int(rng.integers(0, len(pool)))]
    plan: dict[str, list[int]] = {k: [] for k in problem.items}
    for s, key in owner.items():
        plan[key].append(s)
    return {k: tuple(sorted(v)) for k, v in plan.items()}
