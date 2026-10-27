"""A second evaluator for tests: every rule's cost from slot arrays, with no `Lin` and no model variables.

It re-derives each rule from DESIGN §12.2, sharing none of `evaluate()`'s structure, so the two can check
each other. Ported from the research's direct evaluator.
"""

import math
from collections.abc import Callable

import numpy as np

from friday.engine.checker import runs
from friday.engine.problem import STAGES, EngineItem, Plan, Problem
from friday.engine.pwl import hinge_coefficient
from friday.engine.rules import FORBID, Rule, in_hour_window, matching_weekdays
from friday.engine.rules.measures import window_share_and_growth

Hinge = tuple[str, float, float, str, float, int]  # direction, theta, slope, unit, mult, value


def price_function(p: Problem, rule: Rule, item: EngineItem) -> Callable[[int], float]:
    grid, kind, importance = p.grid, rule.type, item.importance
    if kind in ("late_work", "soft_late"):
        extra = rule.p.overflow_extra_hours

        def lateness(s: int) -> float:
            if item.due_utc is None:
                return 0.0
            if s == grid.S:
                inside = item.due_utc <= grid.horizon_end
                return importance * ((grid.horizon_end - item.due_utc) / 60 + extra) if inside else 0.0
            return importance * max(0.0, (int(grid.end[s]) - item.due_utc) / 60)

        return lateness
    if kind == "time_preference":
        days = matching_weekdays(rule.p.days, rule.p.days_except)

        def preference(s: int) -> float:
            if s == grid.S or rule.p.price == FORBID:
                return 0.0
            slot = grid.slots[s]
            hit = slot.weekday in days and in_hour_window(slot.local_minute, rule.p.start, rule.p.end)
            return float(rule.p.price) if hit else 0.0

        return preference
    if kind == "energy":
        return lambda s: (
            0.0 if s == grid.S else float(p.energy_map[grid.slots[s].weekday][grid.slots[s].local_minute // 30])
        )
    if kind == "finish_early":

        def early(s: int) -> float:
            end = grid.horizon_end if s == grid.S else int(grid.end[s])
            assert item.due_utc is not None
            return min(rule.p.days, max(0.0, (end - (item.due_utc - rule.p.days * 1440)) / 1440))

        return early
    if kind == "unscheduled":
        return lambda s: rule.p.base * importance if s == grid.S else 0.0
    if kind == "late_tasks":

        def squared(s: int) -> float:
            assert item.due_utc is not None
            if not rule.p.square_hours or (s == grid.S and item.due_utc > grid.horizon_end):
                return 0.0
            end = grid.horizon_end + 2880 if s == grid.S else int(grid.end[s])
            return importance * max(0.0, (end - item.due_utc) / 60) ** 2 / rule.p.square_hours

        return squared
    # late_night and after_event read per-night and per-event data the rule prepares; the formula is the rule's.
    return lambda s: rule.price(item, s)


def price_cost(p: Problem, rule: Rule, item: EngineItem, slots: list[int], over: int) -> int:
    grid, price = p.grid, price_function(p, rule, item)
    weight = rule.weight * p.multiplier(rule.name, rule.type)
    total = sum(
        round(weight * rule.day_mult(int(grid.day[s])) * price(s) * grid.units[s] * 0.25 * p.scale) for s in slots
    )
    if item.amount == "fixed" and over:
        total += round(weight * price(grid.S) * 0.25 * p.scale) * over
    return int(total)


def hinge_cost(p: Problem, rule: Rule, hinges: list[Hinge]) -> int:
    weight = rule.weight * p.multiplier(rule.name, rule.type)
    total = 0
    for direction, theta, slope, unit, mult, value in hinges:
        whole = math.floor(theta + 1e-9) if direction == "above" else math.ceil(theta - 1e-9)
        excess = max(0, value - whole) if direction == "above" else max(0, whole - value)
        total += hinge_coefficient(weight, mult, slope, unit, p.scale, rule.name) * excess
    return total


def direct_rule_costs(p: Problem, plan: Plan) -> dict[str, int]:
    grid = p.grid
    U = grid.units
    X = {k: np.zeros(grid.S, dtype=bool) for k in p.items}
    for key, slots in plan.items():
        X[key][list(slots)] = True
    placed = {k: int(U[: grid.S][X[k]].sum()) for k in p.items}
    over = {k: max(0, it.need - placed[k]) if it.amount == "fixed" else 0 for k, it in p.items.items()}
    out: dict[str, int] = {}
    for rule in p.rules:
        items = [i for i in p.items.values() if rule.applies(i)]
        if rule.has_price:
            cost = sum(price_cost(p, rule, it, np.flatnonzero(X[it.key]).tolist(), over[it.key]) for it in items)
            if rule.type == "late_tasks":
                cost += late_task_counts(p, rule, items, X, over)
        else:
            cost = measure_rule_cost(p, rule, items, X, placed)
        out[rule.name] = out.get(rule.name, 0) + cost
    return out


def late_task_counts(p: Problem, rule: Rule, items: list[EngineItem], X: dict[str, np.ndarray],
                     over: dict[str, int]) -> int:  # fmt: skip
    """late_tasks' counts: each task with any work after its due (or left unplaced) costs `hours` of one unit's."""
    grid, hinges = p.grid, []
    for it in items:
        assert it.due_utc is not None
        if it.due_utc > grid.horizon_end:
            continue
        late_slots = [s for s in it.allowed if int(grid.end[s]) > it.due_utc]
        if late_slots:
            hinges.append(("above", 0, it.importance * rule.p.hours, "count", 1.0, int(any(X[it.key][late_slots]))))
        hinges.append(("above", 0, 4 * it.importance * rule.p.hours, "units", 1.0, over[it.key]))
    return hinge_cost(p, rule, hinges)


def units_in(U: np.ndarray, X: dict[str, np.ndarray], item: EngineItem, slots) -> int:  # noqa: ANN001
    return int(sum(U[s] for s in slots if X[item.key][s]))


def measure_rule_cost(p: Problem, rule: Rule, items: list[EngineItem], X: dict[str, np.ndarray],
                      placed: dict[str, int]) -> int:  # fmt: skip
    grid, U, kind = p.grid, p.grid.units, rule.type
    reach = lambda slots, its: sum(int(U[s]) for it in its for s in slots if s in it.allowed_set)  # noqa: E731
    hinges: list[Hinge] = []
    if kind == "quota":
        for it in items:
            for week, quota in sorted(it.quotas.items()):
                if week in grid.week_slots:
                    value = it.progress_by_week.get(week, 0) + units_in(U, X, it, grid.week_slots[week])
                    hinges.append(("below", quota, 1.0, "units", 1.0, value))
    elif kind == "deep_run":
        usable = np.zeros(grid.S, dtype=np.int64)
        for it in items:
            usable[list(it.allowed)] = U[list(it.allowed)]
        for a in range(grid.S):
            limit = max(4, round(rule.p.threshold * p.scale_of(a).deep_run_threshold))
            got, b = 0, a
            while b < grid.S and got < limit + 1:
                got, b = got + int(U[b]), b + 1
            if got < limit + 1 or usable[a:b].sum() < limit + 1:
                continue
            if any(s in it.allowed_set for it in items for s in range(a, b)):
                hinges.append(("above", limit, 1.0, "units", 1.0, sum(units_in(U, X, it, range(a, b)) for it in items)))
    elif kind == "reserve":
        days = matching_weekdays(rule.p.days, rule.p.days_except)
        for d in range(grid.n_days):
            day_slots = grid.day_slots[d]
            if grid.slots[day_slots[0]].weekday not in days:
                continue
            window = [s for s in day_slots if in_hour_window(grid.slots[s].local_minute, rule.p.start, rule.p.end)]
            if not window:
                continue
            free = sum(int(U[s]) for s in window if not (p.blocked[s] or p.core[s]))
            theta = max(0, free - round(rule.p.free * p.scales[d].reserve_free))
            if reach(window, items) <= theta:
                continue
            busy = sum(int(U[s]) for s in window for it in items if X[it.key][s])
            hinges.append(("above", theta, 1.0, "units", 1.0, busy))
    elif kind == "daily_load":
        for d in range(grid.n_days):
            if (
                rule.p.days
                and ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[grid.day_date[d].weekday()] not in rule.p.days
            ):
                continue
            theta = round(rule.p.threshold * p.scales[d].daily_load_threshold)
            if reach(grid.day_slots[d], items) > theta:
                hinges.append(("above", theta, 1.0, "units", 1.0,
                               sum(units_in(U, X, it, grid.day_slots[d]) for it in items)))  # fmt: skip
    elif kind == "even_load":
        due_inside = [i for i in items if i.due_utc is not None and i.due_utc <= grid.horizon_end]
        if due_inside:
            total, latest = sum(i.need for i in due_inside), max(i.due_utc for i in due_inside)  # type: ignore[type-var]
            n = sum(
                1 for d in range(grid.n_days)
                if grid.day_slots[d] and grid.start[grid.day_slots[d][0]] < latest
                and any(not (p.blocked[s] or p.core[s]) for s in grid.day_slots[d])
            )  # fmt: skip
            if n and total:
                share = max(math.ceil(total / n), rule.p.floor)
                for d in range(grid.n_days):
                    if reach(grid.day_slots[d], due_inside) > share:
                        value = sum(units_in(U, X, it, grid.day_slots[d]) for it in due_inside)
                        hinges.append(("above", share, 1.0, "units", p.scales[d].even_load_weight, value))
    elif kind == "chunk_cost":
        for it in items:
            if it.allowed:
                chunks = len(runs(tuple(np.flatnonzero(X[it.key]).tolist())))
                hinges.append(("above", 1, it.chunk_cost * it.size_hours, "count", 1.0, chunks))
    elif kind == "spread":
        for it in items:
            days = [d for d in range(grid.n_days) if any(s in it.allowed_set for s in grid.day_slots[d])]
            for d in days:
                share = math.ceil(it.need / len(days))
                if reach(grid.day_slots[d], [it]) > share:
                    hinges.append(("above", share, 1.0, "units", 1.0, units_in(U, X, it, grid.day_slots[d])))
    elif kind == "cluster":
        for it in items:
            if it.allowed:
                used = sum(1 for d in range(grid.n_days) if any(X[it.key][s] for s in grid.day_slots[d]))
                hinges.append(("above", 1, rule.p.per_day, "count", 1.0, used))
    elif kind == "batch_by_day":
        groups: dict = {}
        for it in items:
            groups.setdefault(getattr(it, rule.p.by), []).append(it)
        for members in groups.values():
            if len(members) >= 2 and any(m.allowed for m in members):
                used = sum(
                    1 for d in range(grid.n_days) if any(X[m.key][s] for m in members for s in grid.day_slots[d])
                )
                hinges.append(("above", 1, 1.0, "count", 1.0, used))
    elif kind == "target_shortfall":
        for it in items:
            share, amount, weight = window_share_and_growth(p, it)
            target = it.target * share * amount
            value = it.progress + placed[it.key]
            hinges += [("below", f * target, slope, "units", weight, value) for f, slope in rule.p.curve]
    elif kind == "elastic_shortfall":
        for it in items:
            hinges += [("below", it.min, rule.p.steep, "units", 1.0, placed[it.key]),
                       ("below", it.ideal, rule.p.gentle, "units", 1.0, placed[it.key])]  # fmt: skip
    elif kind == "open_value":
        for it in items:
            for d in range(grid.n_days):
                slots = [s for s in grid.day_slots[d] if s in it.allowed_set]
                if slots:
                    value = units_in(U, X, it, slots) + (it.progress_today if d == 0 else 0)
                    hinges += [("below", f * it.daily_ceiling, slope, "units", p.scales[d].open_value_slopes, value)
                               for f, slope in rule.p.curve]  # fmt: skip
    elif kind == "minimize_changes":
        for it in items:
            kept = [s for s in it.current if s in it.allowed_set]
            loose = [s for s in kept if s not in it.preferred and s not in it.held]
            pinned = [s for s in kept if s in it.preferred or s in it.held]
            for slots, slope, mult in ((loose, 1.0, p.minimize_changes_scale),
                                       (pinned, rule.p.preferred_multiplier, 1.0)):  # fmt: skip
                if slots:
                    given_up = sum(int(U[s]) for s in slots if not X[it.key][s])
                    hinges.append(("above", 0, slope, "units", mult, given_up))
    elif kind == "pin_hold":
        for it in items:
            pinned = [s for s in it.preferred if s in it.allowed_set]
            if pinned:
                given_up = sum(int(U[s]) for s in pinned if not X[it.key][s])
                hinges.append(("above", 0, rule.p.price, "units", 1.0, given_up))
    elif kind == "buffer":
        sizes: dict = {}
        for it in items:
            b = max(rule.p.minutes, rule.p.by_area.get(it.area or "", 0), rule.p.by_preset.get(it.preset or "", 0))
            if b > 0:
                sizes.setdefault(b, []).append(it)
        for b, members in sorted(sizes.items()):
            for s in range(grid.S):
                window, got, k = [], 0, s - 1
                while k >= 0 and got < b and grid.end[k] == grid.start[k + 1]:
                    window, got, k = [*window, k], got + int(U[k]), k - 1
                if not window or not any(s in m.allowed_set for m in members):
                    continue
                started = any(X[m.key][s] and not (s > 0 and X[m.key][s - 1]) for m in members)
                busy = sum(int(U[w]) for w in window for it in p.items.values() if X[it.key][w])
                fixed = sum(int(U[w]) for w in window if p.blocked[w] and not p.core[w])
                hinges.append(("above", b, 1.0, "units", 1.0, b * started + busy + fixed))
    elif kind == "travel_kept":
        # Its items' own travel kept clear: before a sitting, other work or an event in the b units before its start;
        # after one, other work in a slot with one of its units in the b before it.
        slope = rule.p.price
        for side in ("before", "after"):
            sizes = {}
            for it in items:
                if (b := getattr(it, f"travel_{side}")) > 0:
                    sizes.setdefault(b, []).append(it)
            for b, members in sorted(sizes.items()):
                keys = {m.key for m in members}
                for s in range(grid.S):
                    window, got, k = [], 0, s - 1
                    while k >= 0 and got < b and grid.end[k] == grid.start[k + 1]:
                        window, got, k = [*window, k], got + int(U[k]), k - 1
                    if not window:
                        continue
                    other = lambda w, keys=keys: any(X[i.key][w] for i in p.items.values() if i.key not in keys)  # noqa: E731
                    mine = lambda w, members=members: any(X[m.key][w] for m in members)  # noqa: E731
                    if side == "before":
                        if not any(s in m.allowed_set for m in members):
                            continue
                        started = any(X[m.key][s] and not (s > 0 and X[m.key][s - 1]) for m in members)
                        busy = sum(int(U[w]) for w in window if other(w))
                        events = sum(int(U[w]) for w in window if p.events[w])
                        hinges.append(("above", b, slope, "units", 1.0, b * started + busy + events))
                    else:
                        if not any(w in m.allowed_set for m in members for w in window):
                            continue
                        here = int(U[s]) if other(s) else 0
                        hinges.append(
                            (
                                "above",
                                b * int(U[s]),
                                slope,
                                "units",
                                1.0,
                                here * b + sum(int(U[w]) for w in window if mine(w)),
                            )
                        )
    else:
        raise KeyError(f"no direct evaluator for rule type {kind}")
    return hinge_cost(p, rule, hinges)


def direct_stage_values(p: Problem, plan: Plan) -> dict[str, int]:
    costs = direct_rule_costs(p, plan)
    out = dict.fromkeys(STAGES, 0)
    for rule in p.rules:
        out[rule.stage] += costs[rule.name]
    return out
