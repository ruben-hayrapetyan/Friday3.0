"""Exhaustive solver for tiny instances: the ground truth for the evaluator, checker and CP-SAT."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from .evaluate import Evaluation, Plan, check, evaluate
from .problem import Problem


@dataclass
class BruteResult:
    best: Evaluation
    plans: list[dict[str, tuple[int, ...]]]  # every plan achieving the best lexicographic value
    n_valid: int


def to_plan(problem: Problem, assignment: tuple[str | None, ...], slot_ids: list[int]) -> dict[str, tuple[int, ...]]:
    plan: dict[str, list[int]] = {k: [] for k in problem.items}
    for s, k in zip(slot_ids, assignment):
        if k is not None:
            plan[k].append(s)
    return {k: tuple(v) for k, v in plan.items()}


def valid_plans(problem: Problem, limit: int = 2_000_000):
    """Yield every plan the hard-rule checker accepts."""
    owners_by_slot: dict[int, list[str | None]] = {}
    for it in problem.items.values():
        for s in it.allowed:
            owners_by_slot.setdefault(s, [None]).append(it.key)
    slot_ids = sorted(owners_by_slot)
    total = 1
    for s in slot_ids:
        total *= len(owners_by_slot[s])
        if total > limit:
            raise ValueError(f"instance too large for brute force ({total} > {limit})")
    for assignment in itertools.product(*(owners_by_slot[s] for s in slot_ids)):
        plan = to_plan(problem, assignment, slot_ids)
        if not check(problem, plan):
            yield plan


def brute_force(problem: Problem, limit: int = 2_000_000) -> BruteResult:
    best: Evaluation | None = None
    plans: list[dict[str, tuple[int, ...]]] = []
    n_valid = 0
    for plan in valid_plans(problem, limit):
        n_valid += 1
        ev = evaluate(problem, plan)
        if best is None or ev.lex() < best.lex():
            best, plans = ev, [plan]
        elif ev.lex() == best.lex():
            plans.append(plan)
    if best is None:
        raise RuntimeError("no valid plan: the empty plan should always be valid unless locks conflict")
    return BruteResult(best, plans, n_valid)
