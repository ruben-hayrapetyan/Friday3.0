"""The allocator (ENGINE_REFERENCE section 8): hours per item per day over `allocator_weeks`, then weekly quotas.

Day-resolution CP-SAT, two lexicographic stages (lateness, then pacing and shape). The reference breaks ties
towards *earlier* days (`tiebreak="earliest"`), which front-loads work whenever pacing deficits are free once
ahead of the line. Reference scenario 19 expects roughly the linear share, so the default here is
`tiebreak="pace"`: as late as the pacing line allows. Both are kept so the difference can be measured.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from ..core.edf import subtract
from ..core.generate import Scenario
from ..core.grid import planning_day_of, week_of
from ..core.problem import Problem
from ..core.rules import Reserve, TimePreference, parse_days
from ..core.settings import MINUTES_PER_DAY, UNIT_MIN

PACING_K = {"linear": 1.0, "front": 0.7, "back": 1.5}


@dataclass
class Allocation:
    y: dict[str, list[int]]  # item key -> units per day, days 0..A-1
    over: dict[str, int]
    capacity: list[int]
    quota: dict[str, dict[int, int]]
    days: int
    first_date: int
    status: str = ""


def day_capacities(sc: Scenario, problem: Problem, days: int) -> list[int]:
    """Units the allocator may fill each day: utilisation x free time, less what reserves and routines claim."""
    st = sc.settings
    now = problem.grid.now
    p0 = planning_day_of(now, st.day_start)
    from ..core.builder import make_nights

    nights = make_nights(st, p0 - 1, p0 + days + 1)
    busy = [(f.blocked_lo, f.blocked_hi) for f in problem.fixed if f.blocks_time]
    for s in sc.specs:  # fixed items beyond the scheduler's horizon
        if s.when == "fixed" and s.start is not None and s.start >= problem.grid.horizon_end:
            b, a = st.buffers.get(s.event_kind, (0, 0))
            busy.append((s.start - b, s.end + a))
    busy += [n.core for n in nights.values()]
    reserves = [r for r in problem.rules if isinstance(r, Reserve)]
    caps = []
    for d in range(days):
        date = p0 + d
        lo = max(now, date * MINUTES_PER_DAY + st.day_start)
        hi = (date + 1) * MINUTES_PER_DAY + st.day_start
        free = subtract([(lo, hi)], busy)
        free_units = sum(b - a for a, b in free) // UNIT_MIN
        scale = problem.scales[d] if d < len(problem.scales) else problem.scales[-1]
        for r in reserves:
            if date % 7 in r._days():
                free_units -= min(round(r.p.free * scale.rest), free_units)
        util = min(0.95, st.utilization * scale.capacity)
        caps.append(min(st.day_cap_units, int(math.floor(util * free_units))))
    return caps


def pacing(item, now: int, t: int) -> float:
    k = PACING_K.get(item_pacing(item), None)
    if k is None or item.due is None:
        return 0.0
    r = item.release if item.release is not None else now
    if item.due <= r:
        return 1.0
    return min(1.0, max(0.0, ((t - r) / (item.due - r)) ** k))


def item_pacing(item) -> str:
    return "linear" if item.preset == "project" else "none"


def allocate(sc: Scenario, problem: Problem, tiebreak: str = "pace", pacing_weight: float = 4.0,
             time_limit_s: float = 10.0) -> Allocation:
    st = sc.settings
    A = st.allocator_weeks * 7
    now = problem.grid.now
    p0 = planning_day_of(now, st.day_start)
    caps = day_capacities(sc, problem, A)
    # elastic ideals and target weekly amounts claim capacity before todo items are placed
    for it in problem.items.values():
        if it.amount == "elastic":
            d = max(0, (it.release or now) // MINUTES_PER_DAY - p0)
            if d < A:
                caps[d] = max(0, caps[d] - it.ideal)
        elif it.amount == "target" and it.release is not None and it.due is not None:
            d0 = max(0, planning_day_of(it.release, st.day_start) - p0)
            d1 = min(A, planning_day_of(it.due, st.day_start) - p0)
            if d1 > d0:
                per = it.target / (d1 - d0)
                for d in range(d0, d1):
                    caps[d] = max(0, caps[d] - int(round(per)))

    todo = [it for it in problem.items.values() if it.amount == "fixed" and it.need > 0]
    m = cp_model.CpModel()
    y: dict[tuple[str, int], cp_model.IntVar] = {}
    over = {}
    day_of = lambda t: planning_day_of(t, st.day_start) - p0  # noqa: E731
    for it in todo:
        rel = max(0, day_of(it.release)) if it.release is not None else 0
        for d in range(rel, A):
            if caps[d] > 0:
                y[it.key, d] = m.NewIntVar(0, min(caps[d], it.need), f"y_{it.key}_{d}")
        over[it.key] = m.NewIntVar(0, it.need, f"over_{it.key}")
        m.Add(sum(v for (k, _), v in y.items() if k == it.key) + over[it.key] == it.need)
    for d in range(A):
        terms = [v for (k, dd), v in y.items() if dd == d]
        if terms:
            m.Add(sum(terms) <= caps[d])

    # dependencies at day level: ok[A,d] <=> enough of A done before day d (minus lag)
    for it in todo:
        for dep in it.depends_on:
            other = next((o for o in todo if o.key == dep.key), None)
            if other is None or dep.required == 0:
                continue
            lag_days = math.ceil(dep.lag_min / MINUTES_PER_DAY)
            for d in range(A):
                if (it.key, d) not in y:
                    continue
                ok = m.NewBoolVar(f"ok_{other.key}_{it.key}_{d}")
                done = sum(v for (k, dd), v in y.items() if k == other.key and dd < d - lag_days)
                m.Add(dep.required * ok <= done)
                m.Add(y[it.key, d] <= it.need * ok)

    # stage 1: lateness
    late = []
    for it in todo:
        if it.firmness != "hard" or it.due is None:
            continue
        dd = day_of(it.due)
        for d in range(max(0, dd) + 1, A):
            if (it.key, d) in y:
                late.append(it.importance * (d - dd) * y[it.key, d])
        if dd <= A - 1:
            late.append(it.importance * (A - dd + 2) * over[it.key])
    # stage 2: pacing deficits at week boundaries, day prices, tie-break
    pace = []
    for it in todo:
        if item_pacing(it) == "none" or it.due is None:
            continue
        total = it.need + it.progress
        for b in range(7, A + 1, 7):
            t = (p0 + b) * MINUTES_PER_DAY + st.day_start
            target = pacing(it, now, t) * total
            done = it.progress + sum(v for (k, dd), v in y.items() if k == it.key and dd < b)
            deficit = m.NewIntVar(0, total, f"def_{it.key}_{b}")
            m.Add(deficit >= int(math.ceil(target)) - done)
            pace.append(int(round(pacing_weight * 100 * 0.25)) * deficit)
    day_price = []
    for r in problem.rules:
        if isinstance(r, TimePreference) and r.p.start is None and r.p.end is None and r.p.price != "forbid":
            days_ok = set(parse_days(r.p.days_except) or [])
            incl = parse_days(r.p.days)
            for (k, d), v in y.items():
                wd = (p0 + d) % 7
                hit = (incl is None or wd in incl) and wd not in days_ok
                if hit:
                    day_price.append(int(round(r.weight * float(r.p.price) * 0.25 * 100)) * v)
    eps = 1
    if tiebreak == "earliest":
        tie = [eps * d * v for (k, d), v in y.items()]
    else:  # as late as the pacing line allows; for items with no pacing line this is neutral
        tie = [-eps * d * v for (k, d), v in y.items() if item_pacing(next(i for i in todo if i.key == k)) != "none"] \
            + [eps * d * v for (k, d), v in y.items() if item_pacing(next(i for i in todo if i.key == k)) == "none"]

    def run(obj):
        m.Minimize(sum(obj) if obj else 0)
        s = cp_model.CpSolver()
        s.parameters.num_workers = st.workers
        s.parameters.random_seed = 0
        s.parameters.max_deterministic_time = 5.0
        s.parameters.max_time_in_seconds = time_limit_s
        status = s.Solve(m)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("allocator found no solution")
        return s, status

    s1, _ = run(late)
    if late:
        m.Add(sum(late) <= int(s1.ObjectiveValue()))
    s2, status = run(pace + day_price + tie)

    ys = {it.key: [int(s2.Value(y[it.key, d])) if (it.key, d) in y else 0 for d in range(A)] for it in todo}
    horizon_days = problem.grid.n_days
    quotas: dict[str, dict[int, int]] = {}
    for it in todo:
        if it.due is None or it.due <= problem.grid.horizon_end:
            continue  # due inside the horizon: late_work already handles it
        per_week: dict[int, int] = {}
        for d in range(horizon_days):
            u = ys[it.key][d]
            if u:
                w = week_of(p0 + d, st.week_start)
                per_week[w] = per_week.get(w, 0) + u
        if per_week:
            quotas[it.key] = per_week
    return Allocation(ys, {k: int(s2.Value(v)) for k, v in over.items()}, caps, quotas, A, p0,
                      s2.StatusName(status))


def apply_quotas(problem: Problem, alloc: Allocation) -> None:
    for it in problem.items.values():
        it.quotas = dict(alloc.quota.get(it.key, {}))
