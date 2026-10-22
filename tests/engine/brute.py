"""Exhaustive search on tiny instances: the ground truth for the evaluator and the checker."""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass

from friday.engine.checker import check
from friday.engine.evaluate import Evaluation, evaluate
from friday.engine.problem import Problem


@dataclass
class BruteResult:
    best: Evaluation
    plans: list[dict[str, tuple[int, ...]]]  # every plan with the best (deadlines, wellbeing, preferences)
    n_valid: int


def every_assignment(problem: Problem, limit: int = 2_000_000) -> Iterator[dict[str, tuple[int, ...]]]:
    owners: dict[int, list[str | None]] = {}
    for item in problem.items.values():
        for s in item.allowed:
            owners.setdefault(s, [None]).append(item.key)
    slots = sorted(owners)
    total = 1
    for s in slots:
        total *= len(owners[s])
        if total > limit:
            raise ValueError(f"instance too large for brute force ({total} > {limit})")
    for assignment in itertools.product(*(owners[s] for s in slots)):
        plan: dict[str, list[int]] = {k: [] for k in problem.items}
        for s, key in zip(slots, assignment, strict=True):
            if key is not None:
                plan[key].append(s)
        yield {k: tuple(v) for k, v in plan.items()}


def brute_force(problem: Problem, limit: int = 2_000_000) -> BruteResult:
    best: Evaluation | None = None
    plans: list[dict[str, tuple[int, ...]]] = []
    n_valid = 0
    for plan in every_assignment(problem, limit):
        if check(problem, plan):
            continue
        n_valid += 1
        ev = evaluate(problem, plan)
        if best is None or ev.lex() < best.lex():
            best, plans = ev, [plan]
        elif ev.lex() == best.lex():
            plans.append(plan)
    if best is None:
        raise RuntimeError("no valid plan; the empty plan is always valid unless locks conflict")
    return BruteResult(best, plans, n_valid)
