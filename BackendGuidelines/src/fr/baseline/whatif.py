"""what_if and lock conflicts (ENGINE_REFERENCE 8.2): solve the deadlines stage only, before and after a change."""
from __future__ import annotations

from dataclasses import replace

from ..core.builder import Pin
from ..core.evaluate import Plan
from ..core.generate import Scenario
from ..core.problem import Problem
from .cpsat import GridModel


def late_hours(problem: Problem, plan: Plan) -> dict[str, float]:
    """Hours each hard item finishes after its due date; overflow counts until the horizon end."""
    g = problem.grid
    out: dict[str, float] = {}
    for it in problem.items.values():
        if it.firmness != "hard" or it.due is None or it.amount != "fixed":
            continue
        slots = plan.get(it.key, ())
        placed = sum(int(g.units[s]) for s in slots)
        h = max(0.0, (g.end[slots[-1]] - it.due) / 60) if slots else 0.0
        h += max(0, it.need - placed) * 0.25
        if h > 0:
            out[it.key] = round(h, 4)
    return out


def deadlines_only(problem: Problem, **kw):
    return GridModel(problem).solve(stages=["deadlines"], **kw)


def what_if(before: Problem, after: Problem, **kw) -> dict[str, float]:
    """{item: extra late hours} caused by going from `before` to `after` (deadlines stage only)."""
    a = deadlines_only(before, **kw)
    b = deadlines_only(after, **kw)
    la, lb = late_hours(before, a.plan), late_hours(after, b.plan)
    return {k: round(lb.get(k, 0.0) - la.get(k, 0.0), 4) for k in set(la) | set(lb)
            if abs(lb.get(k, 0.0) - la.get(k, 0.0)) > 1e-9}


def lock_conflicts(sc: Scenario, **kw) -> list[tuple[Pin, dict[str, float]]]:
    """Locks that cost deadline slack: [(pin, {item: extra late hours})]. At most 10 single-pin probes."""
    locked = [p for p in sc.pins if p.kind == "locked"]
    if not locked:
        return []
    with_locks = sc.build()
    base = deadlines_only(with_locks, **kw)
    if base.evaluation.stage_values["deadlines"] == 0:
        return []
    relaxed = sc.copy()
    relaxed.pins = [replace(p, kind="preferred") if p.kind == "locked" else p for p in sc.pins]
    saved = deadlines_only(relaxed.build(), **kw)
    if base.evaluation.stage_values["deadlines"] - saved.evaluation.stage_values["deadlines"] <= sc.settings.scale:
        return []  # lateness drops by <= 1 point: not worth blaming a lock
    out = []
    la = late_hours(with_locks, base.plan)
    for pin in locked[:10]:
        one = sc.copy()
        one.pins = [replace(p, kind="preferred") if p == pin else p for p in sc.pins]
        pr = one.build()
        lb = late_hours(pr, deadlines_only(pr, **kw).plan)
        diff = {k: round(la.get(k, 0.0) - lb.get(k, 0.0), 4) for k in set(la) | set(lb)
                if la.get(k, 0.0) - lb.get(k, 0.0) > 1e-9}
        if diff:
            out.append((pin, diff))
    return out
