"""A second, direct evaluator: every rule's cost from slot arrays, with no `Lin` and no model variables.

It re-derives each feature from the reference text so that `evaluate.py` (the shared `Lin` evaluator that
CP-SAT also uses) can be cross-checked against code that shares none of its structure. This is also the
shape the samplers' incremental energy deltas will take.
"""
from __future__ import annotations

import math

import numpy as np

from .evaluate import Plan, runs
from .problem import EngineItem, Problem
from .pwl import hinge_coeff
from .rules import (FORBID, Rule, _hour_window, parse_days)
from .settings import MINUTES_PER_DAY, STAGES


def _price_cost(p: Problem, rule: Rule, item: EngineItem, slots: tuple[int, ...], over: int) -> int:
    """sum over placed slots of round(w * price * hours * scale), plus the overflow slot per unit."""
    g, scale = p.grid, p.settings.scale
    price = _price_fn(p, rule, item)
    total = 0
    for s in slots:
        w = rule.weight * rule.day_mult(int(g.day[s]))
        total += round(w * price(s) * (g.units[s] * 0.25) * scale)
    if item.amount == "fixed" and over:
        total += round(rule.weight * price(g.S) * 0.25 * scale) * over
    return total


def _price_fn(p: Problem, rule: Rule, item: EngineItem):
    g = p.grid
    t = rule.type
    imp = item.importance
    if t in ("late_work", "soft_late"):
        extra = rule.p.overflow_extra_hours

        def f(s):
            if item.due is None:
                return 0.0
            if s == g.S:
                return imp * ((g.horizon_end - item.due) / 60 + extra) if item.due <= g.horizon_end else 0.0
            return imp * max(0.0, (g.end[s] - item.due) / 60)

        return f
    if t == "late_night":
        def f(s):
            if s == g.S:
                return 0.0
            sl = g.slots[s]
            n = p.nights[sl.date]
            tau = (sl.end - sl.date * MINUTES_PER_DAY) / 60
            bed = (n.bedtime - sl.date * MINUTES_PER_DAY) / 60
            m = 1 + rule.p.debt_factor * p.scales[sl.day].rest * n.debt_hours
            gs = rule.p.gradient_start / 60
            return rule.p.a * max(0.0, min(tau, bed) - gs) + rule.p.b * m * max(0.0, tau - bed)

        return f
    if t == "energy":
        return lambda s: 0.0 if s == g.S else float(p.energy_map[g.slots[s].weekday][g.slots[s].local_minute // 60])
    if t == "time_preference":
        incl, excl = parse_days(rule.p.days), parse_days(rule.p.days_except)

        def f(s):
            if s == g.S or rule.p.price == FORBID:
                return 0.0
            sl = g.slots[s]
            ok = (incl is None or sl.weekday in incl) and (excl is None or sl.weekday not in excl)
            return float(rule.p.price) if ok and _hour_window(sl.local_minute, rule.p.start, rule.p.end) else 0.0

        return f
    if t == "finish_early":
        def f(s):
            end = g.horizon_end if s == g.S else g.end[s]
            return min(rule.p.days, max(0.0, (end - (item.due - rule.p.days * MINUTES_PER_DAY)) / MINUTES_PER_DAY))

        return f
    if t == "unscheduled":
        return lambda s: rule.p.base * imp if s == g.S else 0.0
    if t == "after_event":
        return lambda s: rule.price(item, s)  # event bookkeeping is the same data, not a separate formula
    raise KeyError(t)


def _measure_cost(rule: Rule, items: list[EngineItem], p: Problem, X: dict[str, np.ndarray],
                  hinges: list[tuple[str, float, float, str, float, int]]) -> int:
    """hinges: (direction, theta, slope, unit, mult, value g)."""
    tot = 0
    for direction, theta, slope, unit, mult, g in hinges:
        th = math.floor(theta + 1e-9) if direction == "above" else math.ceil(theta - 1e-9)
        ex = max(0, g - th) if direction == "above" else max(0, th - g)
        tot += hinge_coeff(rule.weight, mult, slope, unit, p.settings.scale, rule.name) * ex
    return tot


def direct_rule_costs(p: Problem, plan: Plan) -> dict[str, int]:
    g, scale = p.grid, p.settings.scale
    U = g.units
    X = {k: np.zeros(g.S, dtype=bool) for k in p.items}
    for k, sl in plan.items():
        if k in X:
            X[k][list(sl)] = True
    placed = {k: int(U[:g.S][X[k]].sum()) for k in p.items}
    over = {k: (max(0, it.need - placed[k]) if it.amount == "fixed" else 0) for k, it in p.items.items()}
    out: dict[str, int] = {}

    def add(rule, v):
        out[rule.name] = out.get(rule.name, 0) + v

    for rule in p.rules:
        t = rule.type
        items = [i for i in p.items.values() if rule.applies(i)]
        out.setdefault(rule.name, 0)
        if rule.has_price:
            for it in items:
                add(rule, _price_cost(p, rule, it, tuple(np.flatnonzero(X[it.key]).tolist()), over[it.key]))
            continue

        def units_in(it, slots):
            return int(sum(U[s] for s in slots if X[it.key][s]))

        if t == "quota":
            for it in items:
                for w, q in sorted(it.quotas.items()):
                    if w in g.week_slots:
                        v = it.progress_by_week.get(w, 0) + units_in(it, g.week_slots[w])
                        add(rule, _measure_cost(rule, items, p, X, [("below", q, 1.0, "units", 1.0, v)]))
        elif t == "deep_run":
            usable = np.zeros(g.S, dtype=np.int64)
            for it in items:
                for s in it.allowed:
                    usable[s] = U[s]
            for a in range(g.S):
                k = max(4, round(rule.p.threshold * p.scale_of(a).capacity))
                u, b = 0, a
                while b < g.S and u < k + 1:
                    u += int(U[b])
                    b += 1
                if u < k + 1 or usable[a:b].sum() < k + 1:
                    continue
                if not any(s in it.allowed_set for it in items for s in range(a, b)):
                    continue
                v = sum(units_in(it, range(a, b)) for it in items)
                add(rule, _measure_cost(rule, items, p, X, [("above", k, 1.0, "units", 1.0, v)]))
        elif t == "reserve":
            incl, excl = parse_days(rule.p.days), parse_days(rule.p.days_except)
            for d in range(g.n_days):
                ix = g.day_slots[d]
                wd = g.slots[ix[0]].weekday
                if (incl is not None and wd not in incl) or (excl is not None and wd in excl):
                    continue
                win = [s for s in ix if _hour_window(g.slots[s].local_minute, rule.p.start, rule.p.end)]
                if not win:
                    continue
                free = sum(int(U[s]) for s in win if not (p.blocked[s] or p.core[s]))
                theta = max(0, free - round(rule.p.free * p.scales[d].rest))
                can = sum(int(U[s]) for s in win if any(s in i.allowed_set for i in p.items.values()))
                if can <= theta:
                    continue
                v = sum(int(U[s]) for s in win for i in p.items.values() if X[i.key][s])
                add(rule, _measure_cost(rule, items, p, X, [("above", theta, 1.0, "units", 1.0, v)]))
        elif t == "daily_load":
            for d in range(g.n_days):
                theta = round(rule.p.threshold * p.scales[d].capacity)
                reach = sum(int(U[s]) for it in items for s in g.day_slots[d] if s in it.allowed_set)
                if reach <= theta:
                    continue
                v = sum(units_in(it, g.day_slots[d]) for it in items)
                add(rule, _measure_cost(rule, items, p, X, [("above", theta, 1.0, "units", 1.0, v)]))
        elif t == "even_load":
            its = [i for i in items if i.due is not None and i.due <= g.horizon_end]
            if its:
                total = sum(i.need for i in its)
                latest = max(i.due for i in its)
                n = sum(1 for d in range(g.n_days)
                        if g.day_slots[d] and g.start[g.day_slots[d][0]] < latest
                        and any(not (p.blocked[s] or p.core[s]) for s in g.day_slots[d]))
                if n and total:
                    e = math.ceil(total / n)
                    for d in range(g.n_days):
                        reach = sum(int(U[s]) for it in its for s in g.day_slots[d] if s in it.allowed_set)
                        if reach <= e:
                            continue
                        v = sum(units_in(it, g.day_slots[d]) for it in its)
                        add(rule, _measure_cost(rule, items, p, X, [("above", e, 1.0, "units", p.scales[d].spread, v)]))
        elif t == "chunk_cost":
            for it in items:
                if not it.allowed:
                    continue
                n_chunks = len(runs(tuple(np.flatnonzero(X[it.key]).tolist())))
                add(rule, _measure_cost(rule, items, p, X, [("above", 1, it.chunk_cost * it.size_hours, "count", 1.0, n_chunks)]))
        elif t == "spread":
            for it in items:
                days = [d for d in range(g.n_days) if any(s in it.allowed_set for s in g.day_slots[d])]
                if not days:
                    continue
                e = math.ceil(it.need / len(days))
                for d in days:
                    reach = sum(int(U[s]) for s in g.day_slots[d] if s in it.allowed_set)
                    if reach <= e:
                        continue
                    add(rule, _measure_cost(rule, items, p, X, [("above", e, 1.0, "units", 1.0, units_in(it, g.day_slots[d]))]))
        elif t == "cluster":
            for it in items:
                used = sum(1 for d in range(g.n_days) if any(X[it.key][s] for s in g.day_slots[d]))
                if any(s in it.allowed_set for s in range(g.S)):
                    add(rule, _measure_cost(rule, items, p, X, [("above", 1, rule.p.per_day, "count", 1.0, used)]))
        elif t == "batch_by_day":
            groups: dict = {}
            for it in items:
                groups.setdefault(getattr(it, rule.p.by), []).append(it)
            for grp, members in groups.items():
                if len(members) < 2:
                    continue
                days_used = sum(1 for d in range(g.n_days) if any(X[m.key][s] for m in members for s in g.day_slots[d]))
                if any(s in m.allowed_set for m in members for s in range(g.S)):
                    add(rule, _measure_cost(rule, items, p, X, [("above", 1, 1.0, "count", 1.0, days_used)]))
        elif t == "target_shortfall":
            for it in items:
                from .rules import _window_growth

                share, growth = _window_growth(p, it)
                te = it.target * share * growth
                v = it.progress + placed[it.key]
                add(rule, _measure_cost(rule, items, p, X, [("below", f * te, s, "units", growth, v) for f, s in rule.p.curve]))
        elif t == "elastic_shortfall":
            for it in items:
                v = placed[it.key]
                add(rule, _measure_cost(rule, items, p, X, [("below", it.min, rule.p.steep, "units", 1.0, v),
                                                          ("below", it.ideal, rule.p.gentle, "units", 1.0, v)]))
        elif t == "open_value":
            for it in items:
                for d in range(g.n_days):
                    sl = [s for s in g.day_slots[d] if s in it.allowed_set]
                    if not sl:
                        continue
                    v = units_in(it, sl) + (it.progress_today if d == 0 else 0)
                    add(rule, _measure_cost(rule, items, p, X, [("below", f * it.daily_ceiling, s, "units", p.scales[d].growth, v)
                                                              for f, s in rule.p.curve]))
        elif t == "minimize_changes":
            for it in items:
                keep = [s for s in it.current if s in it.allowed_set]
                for slots, slope in (([s for s in keep if s not in it.preferred], 1.0),
                                     ([s for s in keep if s in it.preferred], rule.p.preferred_multiplier)):
                    if not slots:
                        continue
                    given_up = sum(int(U[s]) for s in slots if not X[it.key][s])
                    add(rule, _measure_cost(rule, items, p, X, [("above", 0, slope, "units", p.settings.minimize_changes_scale, given_up)]))
        else:
            raise KeyError(f"no direct evaluator for rule type {t}")
    return out


def direct_stage_values(p: Problem, plan: Plan) -> dict[str, int]:
    costs = direct_rule_costs(p, plan)
    stage = {r.name: r.stage for r in p.rules}
    out = {s: 0 for s in STAGES}
    for name, c in costs.items():
        out[stage[name]] += c
    return out
