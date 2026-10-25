"""The deadline fallback (DESIGN §11.10): CP-SAT on the deadlines stage only.

Used only while construction and repair leave lateness. Its objective is built from the same price rows and
measures the evaluator uses, so its value for a plan equals the evaluator's deadlines value. This is the one
place a plan can depend on time: it runs with a time limit, and the scheduler reports when it was used.
"""

import threading
from dataclasses import dataclass
from typing import Any

from ortools.sat.python import cp_model

from friday.engine.checker import lag_slot
from friday.engine.problem import EngineItem, Plan, Problem
from friday.engine.pwl import Lin, hinge_coefficient
from friday.engine.rules import BuildContext, price_row


@dataclass
class FallbackResult:
    plan: dict[str, tuple[int, ...]] | None
    status: str
    objective: int | None


class DeadlineModel:
    def __init__(self, problem: Problem, assume_locks: bool = False):
        self.p, self.g = problem, problem.grid
        self.m = cp_model.CpModel()
        self.assume_locks = assume_locks
        self.lock_literals: dict[str, Any] = {}
        self.x: dict[tuple[str, int], Any] = {}
        self.over: dict[str, Any] = {}
        self.start: dict[tuple[str, int], Any] = {}
        self.cum: dict[tuple[str, int], Any] = {}
        self.any: dict[str, Any] = {}
        self.objective: list[Any] = []
        self.solver: cp_model.CpSolver | None = None
        self.stopped = threading.Event()
        ctx = BuildContext(problem)
        self.measures = [(r, list(r.measures(ctx))) for r in problem.rules if r.stage == "deadlines"]
        self.ctx = ctx
        self.add_slots_and_locks()
        self.add_one_at_a_time_and_caps()
        self.add_amounts()
        self.add_chunks()
        self.add_dependencies()
        self.add_objective()
        if assume_locks:
            self.m.add_assumptions(list(self.lock_literals.values()))

    def placed(self, item: EngineItem, slots: Any = None) -> Any:
        slots = item.allowed if slots is None else slots
        return sum(int(self.g.units[s]) * self.x[item.key, s] for s in slots if (item.key, s) in self.x)

    def add_slots_and_locks(self) -> None:
        for item in self.p.items.values():
            for s in item.allowed:
                self.x[item.key, s] = self.m.new_bool_var(f"x_{item.key}_{s}")
            if item.locked and self.assume_locks:
                self.lock_literals[item.key] = self.m.new_bool_var(f"lock_{item.key}")
            for s in item.locked:  # C4
                held = self.m.add(self.x[item.key, s] == 1)
                if self.assume_locks:
                    held.only_enforce_if(self.lock_literals[item.key])
            if item.amount == "fixed":
                self.over[item.key] = self.m.new_int_var(0, item.need, f"over_{item.key}")

    def add_one_at_a_time_and_caps(self) -> None:
        by_slot: dict[int, list[Any]] = {}
        by_day: dict[int, list[Any]] = {}
        for (_, s), v in self.x.items():
            by_slot.setdefault(s, []).append(v)
            by_day.setdefault(self.g.slots[s].day, []).append(int(self.g.units[s]) * v)
        for owners in by_slot.values():  # C1
            if len(owners) > 1:
                self.m.add_at_most_one(owners)
        for d, terms in by_day.items():  # C5
            self.m.add(sum(terms) <= self.p.day_caps[d])

    def add_amounts(self) -> None:
        for item in self.p.items.values():
            placed = self.placed(item)
            if item.amount == "fixed":
                self.add_fixed_amount(item, placed)
            elif item.amount == "elastic":
                self.add_most(item, placed, item.max)
            elif item.amount == "target":
                self.m.add(placed <= item.cap)
            else:
                for d in range(self.g.n_days):
                    ceiling = item.daily_ceiling - (item.progress_today if d == 0 else 0)
                    slots = [s for s in self.g.day_slots[d] if s in item.allowed_set]
                    if slots:
                        self.m.add(self.placed(item, slots) <= max(0, ceiling))

    def add_most(self, item: EngineItem, placed: Any, most: int) -> None:
        """At most `most` units, and one more only when a 30-minute slot holds the last 15 minutes (W4)."""
        coarse = [self.x[item.key, s] for s in item.allowed if self.g.units[s] > 1]
        if coarse:
            uses_coarse = self.m.new_bool_var(f"coarse_max_{item.key}")
            self.m.add(uses_coarse <= sum(coarse))
            self.m.add(placed <= most + uses_coarse)
        else:
            self.m.add(placed <= most)

    def add_fixed_amount(self, item: EngineItem, placed: Any) -> None:
        over = self.over[item.key]
        self.m.add(placed + over >= item.need)  # C2
        # One extra unit only when a 30-minute slot holds a 15-minute remainder (W4).
        coarse = [self.x[item.key, s] for s in item.allowed if self.g.units[s] > 1]
        if coarse:
            uses_coarse = self.m.new_bool_var(f"coarse_{item.key}")
            self.m.add(uses_coarse <= sum(coarse))
            self.m.add(placed <= item.need + uses_coarse)
        else:
            self.m.add(placed <= item.need)
        if item.shape == "one_sitting":  # C6: all of it or none of it
            gone = self.m.new_bool_var(f"gone_{item.key}")
            self.m.add(over == item.need * gone)
            self.m.add(placed <= (item.need + 1) * (1 - gone))

    def add_chunks(self) -> None:
        for item in self.p.items.values():
            if item.shape == "one_sitting" or item.min_chunk > 1 or item.key in self.ctx.starts_requested:
                self.add_starts(item)
            if item.max_chunk is not None:
                self.add_max_chunk(item)

    def add_starts(self, item: EngineItem) -> None:
        for s in item.allowed:
            start = self.start[item.key, s] = self.m.new_bool_var(f"start_{item.key}_{s}")
            here, before = self.x[item.key, s], self.x.get((item.key, s - 1)) if s > 0 else None
            self.m.add(start <= here)
            if before is None:
                self.m.add(start == here)
            else:
                self.m.add(start >= here - before)
                self.m.add(start <= 1 - before)
        if item.shape == "one_sitting":
            self.m.add(sum(self.start[item.key, s] for s in item.allowed) <= 1)
        if item.min_chunk > 1:  # C7: a chunk that starts covers the minimum
            for s in item.allowed:
                units, j, run = 0, s, []
                while units < item.min_chunk and j < self.g.S and (item.key, j) in self.x:
                    units += int(self.g.units[j])
                    run.append(j)
                    j += 1
                if units < item.min_chunk:
                    self.m.add(self.start[item.key, s] == 0)
                else:
                    for j in run[1:]:
                        self.m.add(self.x[item.key, j] >= self.start[item.key, s])

    def add_max_chunk(self, item: EngineItem) -> None:
        for a in range(self.g.S):
            units, b = 0, a
            while b < self.g.S and units < item.max_chunk + 1:  # type: ignore[operator]
                units += int(self.g.units[b])
                b += 1
            if units < item.max_chunk + 1:  # type: ignore[operator]
                break
            slots = [s for s in range(a, b) if (item.key, s) in self.x]
            if sum(int(self.g.units[s]) for s in slots) >= item.max_chunk + 1:  # type: ignore[operator]
                self.m.add(self.placed(item, slots) <= item.max_chunk)

    def add_dependencies(self) -> None:
        """C8: (N_A − P_A) × x[B, s] ≤ cum[A, the slot holding start(s) − lag]."""
        for item in self.p.items.values():
            for dep in item.depends_on:
                if dep.required == 0 or dep.key not in self.p.items:
                    continue
                self.ensure_cum(self.p.items[dep.key])
                for s in item.allowed:
                    if s in item.locked:
                        continue
                    t = lag_slot(self.p, s, dep.lag_min)
                    if t <= 0:
                        self.m.add(self.x[item.key, s] == 0)
                    else:
                        self.m.add(dep.required * self.x[item.key, s] <= self.cum[dep.key, t])

    def ensure_cum(self, item: EngineItem) -> None:
        if (item.key, 1) in self.cum:
            return
        top = max(item.total_units, item.need) + 1
        before: Any = 0
        for t in range(1, self.g.S + 1):
            v = self.cum[item.key, t] = self.m.new_int_var(0, top, f"cum_{item.key}_{t}")
            step = int(self.g.units[t - 1]) * self.x[item.key, t - 1] if (item.key, t - 1) in self.x else 0
            self.m.add(v == before + step)
            before = v

    def variable(self, var: Any) -> Any:
        kind = var[0]
        if kind == "x":
            return self.x[var[1], var[2]]
        if kind == "over":
            return self.over[var[1]]
        if kind == "start":
            return self.start[var[1], var[2]]
        if kind == "cum":
            self.ensure_cum(self.p.items[var[1]])
            return self.cum[var[1], var[2]]
        if kind == "any":
            return self.any_variable(var[1])
        raise KeyError(var)

    def any_variable(self, group: str) -> Any:
        if group not in self.any:
            v = self.any[group] = self.m.new_bool_var(f"any_{group}")
            members = [self.x[k, s] for k, s in self.ctx.any_groups[group]]
            for member in members:
                self.m.add(v >= member)
            self.m.add(v <= sum(members))
        return self.any[group]

    def bounds(self, var: Any) -> tuple[int, int]:
        if var[0] == "over":
            return 0, self.p.items[var[1]].need
        if var[0] == "cum":
            item = self.p.items[var[1]]
            return 0, max(item.total_units, item.need) + 1
        return 0, 1

    def expression(self, lin: Lin) -> Any:
        return sum(c * self.variable(v) for v, c in lin.terms.items()) + lin.const

    def add_objective(self) -> None:
        g = self.g
        for rule, measures in self.measures:
            if rule.has_price:
                for item in self.p.items.values():
                    if not rule.applies(item):
                        continue
                    row = price_row(self.p, rule, item)
                    self.objective += [int(row[s]) * self.x[item.key, s] for s in item.allowed if row[s]]
                    if item.amount == "fixed" and row[g.S]:
                        self.objective.append(int(row[g.S]) * self.over[item.key])
            for measure in measures:
                self.add_hinges(rule, measure)
        self.m.minimize(sum(self.objective))

    def add_hinges(self, rule: Any, measure: Any) -> None:
        """Per hinge an integer z ≥ g − θ (or θ − g), costing its coefficient per unit."""
        value = self.expression(measure.expr)
        lo, hi = measure.expr.bounds(self.bounds)
        for h in measure.curve:
            coefficient = hinge_coefficient(rule.effective_weight, measure.mult, h.slope, measure.unit, self.p.scale)
            theta = h.whole_theta
            top = max(0, hi - theta) if h.direction == "above" else max(0, theta - lo)
            if coefficient == 0 or top == 0:
                continue
            z = self.m.new_int_var(0, top, f"z_{rule.name}_{measure.name}")
            self.m.add(z >= (value - theta if h.direction == "above" else theta - value))
            self.objective.append(coefficient * z)

    def hint(self, plan: Plan) -> None:
        self.m.clear_hints()
        chosen = {(k, s) for k, slots in plan.items() for s in slots}
        for (k, s), v in self.x.items():
            self.m.add_hint(v, int((k, s) in chosen))

    def solve(self, hint: Plan | None, seconds: float, workers: int, seed: int = 0) -> FallbackResult:
        if hint is not None:
            self.hint(hint)
        solver = self.solver = cp_model.CpSolver()
        solver.parameters.num_workers = workers
        solver.parameters.random_seed = seed
        solver.parameters.max_time_in_seconds = seconds
        if self.stopped.is_set():
            return FallbackResult(None, "CANCELLED", None)
        status = solver.solve(self.m)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return FallbackResult(self.plan_from(solver), solver.status_name(status), int(solver.objective_value))
        return FallbackResult(None, solver.status_name(status), None)

    def stop(self) -> None:
        """Called from another thread when a newer snapshot arrives."""
        self.stopped.set()
        if self.solver is not None:
            self.solver.stop_search()

    def plan_from(self, solver: cp_model.CpSolver) -> dict[str, tuple[int, ...]]:
        out: dict[str, list[int]] = {k: [] for k in self.p.items}
        for (k, s), v in self.x.items():
            if solver.value(v):
                out[k].append(s)
        return {k: tuple(sorted(v)) for k, v in out.items()}

    def lock_core(self, seconds: float = 30) -> list[str]:
        """Items whose locks together make the model infeasible; empty when it is feasible. Needs assume_locks."""
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.max_time_in_seconds = seconds
        if solver.solve(self.m) != cp_model.INFEASIBLE:
            return []
        core = set(solver.sufficient_assumptions_for_infeasibility())
        return [k for k, literal in self.lock_literals.items() if literal.index in core]
