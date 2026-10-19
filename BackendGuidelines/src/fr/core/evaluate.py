"""The one shared evaluator and hard-rule checker (RESEARCH_PROMPT section 7).

Every plan from every engine is scored here, by stage and by rule, in integer scaled points
(1 point = `settings.scale` units). A plan with any hard violation is invalid whatever its energy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from .context import BuildContext
from .problem import EngineItem, Problem
from .pwl import measure_cost
from .rules import price_row
from .settings import STAGES

Plan = Mapping[str, tuple[int, ...]]  # item key -> sorted slot indices


class Solution:
    """A plan plus the arithmetic that recomputes every model variable from the slots alone (6A.7)."""

    def __init__(self, problem: Problem, plan: Plan, any_defs: dict | None = None):
        self.problem = problem
        self.slots: dict[str, tuple[int, ...]] = {k: tuple(sorted(plan.get(k, ()))) for k in problem.items}
        self.sets = {k: frozenset(v) for k, v in self.slots.items()}
        self.any_defs = any_defs if any_defs is not None else {}
        self._prefix: dict[str, np.ndarray] = {}

    def placed(self, key: str) -> int:
        u = self.problem.grid.units
        return int(sum(u[s] for s in self.slots[key]))

    def over(self, key: str) -> int:
        it = self.problem.items[key]
        return max(0, it.need - self.placed(key)) if it.amount == "fixed" else 0

    def prefix(self, key: str) -> np.ndarray:
        """prefix[t] = units of `key` placed strictly before slot t."""
        p = self._prefix.get(key)
        if p is None:
            g = self.problem.grid
            vec = np.zeros(g.S + 1, dtype=np.int64)
            for s in self.slots[key]:
                vec[s + 1] = g.units[s]
            p = np.cumsum(vec)
            self._prefix[key] = p
        return p

    def value(self, var) -> int:
        kind = var[0]
        if kind == "x":
            return int(var[2] in self.sets[var[1]])
        if kind == "over":
            return self.over(var[1])
        if kind == "start":
            _, key, s = var
            sset = self.sets[key]
            return int(s in sset and (s - 1) not in sset)
        if kind == "cum":
            return int(self.prefix(var[1])[var[2]])
        if kind == "any":
            return int(any(s in self.sets[k] for k, s in self.any_defs[var[1]]))
        raise KeyError(var)


@dataclass
class Evaluation:
    stage_values: dict[str, int]
    rule_totals: dict[str, int]
    rule_stage: dict[str, str]
    item_rule: dict[tuple[str, str], int]  # (rule, item) price costs only
    placed_units: dict[str, int]
    over_units: dict[str, int]
    late_hours: float
    overflow_hours: float
    deadline_misses: list[str]  # hard items due inside the horizon that are late or overflow
    measure_values: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.stage_values.values())

    def lex(self) -> tuple[int, ...]:
        return tuple(self.stage_values[s] for s in STAGES)


def evaluate(problem: Problem, plan: Plan) -> Evaluation:
    sol = Solution(problem, plan)
    ctx = BuildContext(problem)
    sol.any_defs = ctx.any_defs
    g = problem.grid
    totals: dict[str, int] = {}
    stage_of: dict[str, str] = {}
    item_rule: dict[tuple[str, str], int] = {}
    meas_vals: dict[str, int] = {}
    for rule in problem.rules:
        total = 0
        if rule.has_price:
            for item in problem.items.values():
                if not rule.applies(item):
                    continue
                row = price_row(problem, rule, item)
                c = int(sum(row[s] for s in sol.slots[item.key]))
                if item.amount == "fixed":
                    c += int(row[g.S]) * sol.over(item.key)
                if c:
                    item_rule[(rule.name, item.key)] = c
                total += c
        for m in rule.measures(ctx):
            val = m.expr.eval(sol.value)
            meas_vals[f"{rule.name}/{m.name}"] = val
            total += measure_cost(m, val, rule.weight, problem.settings.scale, rule.name)
        totals[rule.name] = totals.get(rule.name, 0) + total
        stage_of[rule.name] = rule.stage
    stage_values = {s: 0 for s in STAGES}
    for name, t in totals.items():
        stage_values[stage_of[name]] += t

    placed = {k: sol.placed(k) for k in problem.items}
    over = {k: sol.over(k) for k in problem.items}
    late = 0.0
    misses: list[str] = []
    for it in problem.items.values():
        if it.firmness != "hard" or it.due is None or it.amount != "fixed":
            continue
        slots = sol.slots[it.key]
        lateness = max(0.0, (g.end[slots[-1]] - it.due) / 60) if slots else 0.0
        late += lateness
        if it.due <= g.horizon_end and (lateness > 0 or over[it.key] > 0):
            misses.append(it.key)
    return Evaluation(stage_values, totals, stage_of, item_rule, placed, over, late,
                      sum(over.values()) * 0.25, misses, meas_vals)


# ---------------------------------------------------------------- hard-rule checker


@dataclass(frozen=True)
class Violation:
    code: str
    key: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.code}[{self.key}] {self.detail}"


def runs(slots: tuple[int, ...]) -> list[tuple[int, int]]:
    """Maximal runs of consecutive slot indices as (first, last)."""
    out: list[tuple[int, int]] = []
    for s in slots:
        if out and out[-1][1] == s - 1:
            out[-1] = (out[-1][0], s)
        else:
            out.append((s, s))
    return out


def lag_slot(problem: Problem, s: int, lag_min: int) -> int:
    """Slot t such that cum is read before t: the slot containing (start(s) - lag); <= 0 means nothing yet."""
    g = problem.grid
    if lag_min == 0:
        return s
    t = int(g.start[s]) - lag_min
    if t < g.slots[0].start:
        return 0
    return g.slot_at(t)


def check(problem: Problem, plan: Plan) -> list[Violation]:
    g = problem.grid
    out: list[Violation] = []
    sol = Solution(problem, plan)
    u = g.units
    for k in plan:
        if k not in problem.items:
            out.append(Violation("unknown_item", k))
    owner: dict[int, str] = {}
    for k, slots in sol.slots.items():
        it = problem.items[k]
        if len(set(slots)) != len(slots):
            out.append(Violation("duplicate_slot", k))
        for s in slots:
            if not 0 <= s < g.S:
                out.append(Violation("bad_slot", k, str(s)))
                continue
            if s in owner and owner[s] != k:
                out.append(Violation("double_booked", k, f"slot {s} also {owner[s]}"))
            owner[s] = k
            if s not in it.allowed_set:
                out.append(Violation("pruned_slot", k, f"slot {s}"))
        miss = it.locked - sol.sets[k]
        if miss:
            out.append(Violation("lock_dropped", k, f"{sorted(miss)}"))

        placed = sol.placed(k)
        if it.amount == "fixed" and placed > it.need:
            # one extra unit is allowed only to fill a coarse slot (see RESEARCH_LOG: tightened C2)
            if placed > it.need + 1 or not any(u[s] > 1 for s in slots):
                out.append(Violation("over_placed", k, f"{placed} > {it.need}"))
        if it.amount == "elastic" and placed > it.max:
            out.append(Violation("over_max", k, f"{placed} > {it.max}"))
        if it.amount == "target" and placed > it.cap:
            out.append(Violation("over_cap", k, f"{placed} > {it.cap}"))
        if it.amount == "open":
            for d in range(g.n_days):
                ceil = it.daily_ceiling - (it.progress_today if d == 0 else 0)
                got = sum(int(u[s]) for s in slots if g.slots[s].day == d)
                if got > ceil:
                    out.append(Violation("over_ceiling", k, f"day {d}: {got} > {ceil}"))

        rs = runs(sol.slots[k])
        if it.shape == "one_sitting":
            if len(rs) > 1:
                out.append(Violation("not_one_sitting", k, f"{len(rs)} chunks"))
            if it.amount == "fixed" and 0 < placed < it.need:
                out.append(Violation("partial_one_sitting", k, f"{placed} of {it.need}"))
        for a, b in rs:
            run_units = int(u[a : b + 1].sum())
            if run_units < it.min_chunk:
                out.append(Violation("short_chunk", k, f"slots {a}-{b}: {run_units} < {it.min_chunk}"))
            if it.max_chunk is not None and run_units > it.max_chunk:
                out.append(Violation("long_chunk", k, f"slots {a}-{b}: {run_units} > {it.max_chunk}"))

        for dep in it.depends_on:
            need = dep.required
            if need == 0 or dep.key not in problem.items:
                continue
            pre = sol.prefix(dep.key)
            for s in slots:
                if s in it.locked:
                    continue
                t = lag_slot(problem, s, dep.lag_min)
                done = 0 if t <= 0 else int(pre[t])
                if done < need:
                    out.append(Violation("dependency", k, f"slot {s} before {dep.key} reached {need} units"))
                    break

    for d in range(g.n_days):
        day_units = sum(int(u[s]) for s in owner if g.slots[s].day == d)
        if day_units > problem.day_caps[d]:
            out.append(Violation("day_cap", f"d{d}", f"{day_units} > {problem.day_caps[d]}"))
    return out
