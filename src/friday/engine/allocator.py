"""The allocator (DESIGN §13): how much of each item happens on which day over the coming weeks, and weekly quotas.

A linear program at day resolution, solved in two stages: lateness first, then pacing, whole-day prices and a
tie-break. Ties go as late as each item's pacing line and due date allow, so distant work isn't front-loaded into
this week; items with no due date go as early as possible. Dependencies are handled outside the LP: a dependent
item's first day moves to the day its source is far enough along, and the LP is solved again until nothing moves.
GLOP's simplex is single-threaded and deterministic, so the same input gives the same allocation.
"""

import math
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from ortools.linear_solver import pywraplp

from friday.core.pace import DayScales
from friday.engine.problem import EngineItem
from friday.engine.rules import Rule, matching_weekdays
from friday.engine.rules.measures import Reserve

PACING_EXPONENT = {"linear": 1.0, "front": 0.7, "back": 1.5}
POINTS_PER_UNIT = 25  # the engine's 100 points per hour, over four 15-minute units
OVERFLOW_POINTS = 100_000  # per unit left unallocated: worse than any placement
TOLERANCE = 1e-6


@dataclass(frozen=True)
class AllocDay:
    date: date
    start_utc: int
    end_utc: int
    free_units: int  # the day minus blocking fixed items (with buffers) and the sleep core
    cap_units: int
    week: int
    scales: DayScales = field(default_factory=DayScales)


@dataclass(frozen=True)
class AllocatorInput:
    days: list[AllocDay]
    items: list[EngineItem]
    rules: list[Rule]  # prepared on the scheduler's problem, so scopes match as they do there
    now_utc: int
    horizon_days: int  # the scheduler's horizon; quotas cover its weeks
    horizon_end_utc: int
    utilization: float = 0.8
    pacing_weight: float = 2.0  # points per hour behind the pacing line, at each week boundary


@dataclass
class Allocation:
    units: dict[str, list[float]]  # item key → units per day
    over: dict[str, float]
    capacity: list[int]
    quotas: dict[str, dict[int, int]]  # item key → week → units

    def day_totals(self) -> list[float]:
        """The planned load per day, shown in the weekly view."""
        return [sum(units[d] for units in self.units.values()) for d in range(len(self.capacity))]


def pacing_fraction(curve: str, start: int, due: int, t: int) -> float:
    """The share of an item that should be done by t: ((t − r) / (D − r))^k, clipped to [0, 1]."""
    if due <= start:
        return 1.0
    return min(1.0, max(0.0, (t - start) / (due - start))) ** PACING_EXPONENT[curve]


def day_capacities(inp: AllocatorInput) -> list[int]:
    """Units the allocator may fill each day: utilization × free time, less what reserves keep free."""
    reserves = [r for r in inp.rules if isinstance(r, Reserve)]
    caps = []
    for day in inp.days:
        free = day.free_units
        for rule in reserves:
            if day.date.weekday() in matching_weekdays(rule.p.days, rule.p.days_except):
                free -= min(round(rule.p.free * day.scales.reserve_free), free)
        utilization = min(0.95, inp.utilization * day.scales.utilization)
        caps.append(min(day.cap_units, math.floor(utilization * free)))
    return caps


class DayIndex:
    def __init__(self, days: list[AllocDay]):
        self.starts = [d.start_utc for d in days]
        self.end = days[-1].end_utc

    def __call__(self, t: int) -> int:
        """The day containing t: −1 before the first day, len(days) after the last."""
        return len(self.starts) if t >= self.end else bisect_right(self.starts, t) - 1


def claim_reserved_time(inp: AllocatorInput, caps: list[int], day_of: DayIndex) -> None:
    """Elastic items take their ideal amount and target items their target before fixed work is placed."""
    days = len(caps)
    for item in inp.items:
        first = max(0, day_of(item.release_utc if item.release_utc is not None else inp.now_utc))
        if item.amount == "elastic" and first < days:
            caps[first] = max(0, caps[first] - item.ideal)
        elif item.amount == "target" and item.due_utc is not None:
            last = min(days, day_of(item.due_utc - 1) + 1)
            for d in range(first, last):
                share = item.target / (last - first) * inp.days[d].scales.target_amount
                caps[d] = max(0, caps[d] - round(share))


def allocate(inp: AllocatorInput) -> Allocation:
    caps = day_capacities(inp)
    day_of = DayIndex(inp.days)
    claim_reserved_time(inp, caps, day_of)
    todo = [it for it in inp.items if it.amount == "fixed" and it.need > 0]
    ready: dict[str, int] = {}
    units: dict[str, list[float]] = {}
    over: dict[str, float] = {}
    # A ready day only ever moves later, so this settles; each round can delay at most one more chain link.
    for _ in range(len(todo) + 1):
        units, over = AllocatorLP(inp, caps, day_of, todo, ready).solve()
        later = ready_days(todo, units, ready)
        if later == ready:
            break
        ready = later
    return Allocation(units, over, caps, quotas(inp, todo, units))


def ready_days(todo: list[EngineItem], units: dict[str, list[float]], ready: dict[str, int]) -> dict[str, int]:
    """For each dependent item, the first day after its sources are far enough along (plus the lag)."""
    out = dict(ready)
    for item in todo:
        for dep in item.depends_on:
            if dep.key not in units or dep.required == 0:
                continue
            done, day = 0.0, len(units[dep.key])
            for d, amount in enumerate(units[dep.key]):
                done += amount
                if done >= dep.required - TOLERANCE:
                    day = d + 1
                    break
            day += math.ceil(dep.lag_min / 1440)
            out[item.key] = max(out.get(item.key, 0), day)
    return out


def effective_due_days(todo: list[EngineItem], day_of: DayIndex, caps: list[int]) -> dict[str, int | None]:
    """Due days, with a dependency source due early enough for its dependents to follow (after the lag) in time."""
    due = {it.key: day_of(it.due_utc) if it.due_utc is not None else None for it in todo}
    typical_cap = max(1.0, sum(caps) / len(caps))
    for _ in range(len(todo)):
        changed = False
        for item in todo:
            for dep in item.depends_on:
                own = due[item.key]
                if dep.key not in due or own is None:
                    continue
                needed = own - math.ceil(dep.lag_min / 1440) - math.ceil(item.need / typical_cap)
                current = due[dep.key]
                if current is None or needed < current:
                    due[dep.key] = needed
                    changed = True
        if not changed:
            break
    return due


def quotas(inp: AllocatorInput, todo: list[EngineItem], units: dict[str, list[float]]) -> dict[str, dict[int, int]]:
    """Weekly quotas inside the scheduler's horizon, for items due after it; due inside, `late_work` acts."""
    out: dict[str, dict[int, int]] = {}
    for item in todo:
        if item.due_utc is None or item.due_utc <= inp.horizon_end_utc:
            continue
        per_week: dict[int, float] = {}
        for d in range(min(inp.horizon_days, len(inp.days))):
            week = inp.days[d].week
            per_week[week] = per_week.get(week, 0.0) + units[item.key][d]
        rounded = {week: round(amount) for week, amount in per_week.items() if round(amount) > 0}
        if rounded:
            out[item.key] = rounded
    return out


class AllocatorLP:
    def __init__(self, inp: AllocatorInput, caps: list[int], day_of: DayIndex, todo: list[EngineItem],
                 ready: dict[str, int]):  # fmt: skip
        self.inp, self.caps, self.day_of, self.todo = inp, caps, day_of, todo
        self.A = len(caps)
        self.lp = pywraplp.Solver.CreateSolver("GLOP")
        self.effective_due = effective_due_days(todo, day_of, caps)
        self.day_prices = self.whole_day_prices()
        self.y: dict[tuple[str, int], pywraplp.Variable] = {}
        self.over: dict[str, pywraplp.Variable] = {}
        for item in todo:
            self.add_item(item, ready.get(item.key, 0))
        for d in range(self.A):
            today = [v for (_, dd), v in self.y.items() if dd == d]
            if today:
                self.lp.Add(self.lp.Sum(today) <= caps[d])

    def whole_day_prices(self) -> dict[str, list[float]]:
        """Per item, the summed points per unit on each day from rules with a whole-day price (inf = forbidden)."""
        priced = [(r, [r.day_price(day.date) for day in self.inp.days]) for r in self.inp.rules]
        priced = [(r, prices) for r, prices in priced if any(prices)]
        out = {}
        for item in self.todo:
            row = [0.0] * self.A
            for rule, prices in priced:
                if rule.applies(item):
                    row = [a + rule.effective_weight * p * POINTS_PER_UNIT for a, p in zip(row, prices, strict=True)]
            out[item.key] = row
        return out

    def add_item(self, item: EngineItem, ready_day: int) -> None:
        released = max(0, self.day_of(item.release_utc)) if item.release_utc is not None else 0
        last = self.A if item.cutoff_utc is None else min(self.A, self.day_of(item.cutoff_utc - 1) + 1)
        for d in range(max(released, ready_day), last):
            if self.caps[d] > 0 and self.day_prices[item.key][d] != math.inf:
                self.y[item.key, d] = self.lp.NumVar(0, min(self.caps[d], item.need), "")
        self.over[item.key] = self.lp.NumVar(0, item.need, "")
        self.lp.Add(self.lp.Sum(self.days_of(item.key)) + self.over[item.key] == item.need)

    def days_of(self, key: str, before: int | None = None) -> list[pywraplp.Variable]:
        stop = self.A if before is None else max(0, min(before, self.A))
        return [self.y[key, d] for d in range(stop) if (key, d) in self.y]

    def lateness(self) -> dict[pywraplp.Variable, float]:
        """Stage 1: hard work on days after its due day, and overflow of items due inside the window."""
        terms: dict[pywraplp.Variable, float] = {}
        for item in self.todo:
            if item.firmness != "hard" or item.due_utc is None:
                continue
            due_day = self.day_of(item.due_utc)
            for d in range(max(0, due_day) + 1, self.A):
                if (item.key, d) in self.y:
                    terms[self.y[item.key, d]] = item.importance * (d - due_day)
            if due_day < self.A:
                terms[self.over[item.key]] = item.importance * (self.A - due_day + 2)
        return terms

    def shape(self) -> dict[pywraplp.Variable, float]:
        """Stage 2: pacing deficits, soft lateness, whole-day prices, overflow and the tie-break."""
        points = self.inp.pacing_weight * POINTS_PER_UNIT
        terms = dict.fromkeys(self.pacing(), points)
        for item in self.todo:
            due_day = self.effective_due[item.key]
            terms[self.over[item.key]] = OVERFLOW_POINTS
            for d in range(self.A):
                v = self.y.get((item.key, d))
                if v is None:
                    continue
                price = self.day_prices[item.key][d]
                if due_day is not None and d > due_day:
                    price += POINTS_PER_UNIT * item.importance * (d - due_day)
                terms[v] = price + (-d if due_day is not None else d)  # as late as the due date and pacing allow
        return terms

    def pacing(self) -> list[pywraplp.Variable]:
        """Units behind each item's pacing line at every seventh day boundary."""
        deficits = []
        for item in self.todo:
            if item.pacing == "none" or item.due_utc is None:
                continue
            total = item.need + item.progress
            start = item.pacing_start_utc if item.pacing_start_utc is not None else self.inp.now_utc
            for b in range(7, self.A + 1, 7):
                t = self.inp.days[b].start_utc if b < self.A else self.inp.days[-1].end_utc
                behind = pacing_fraction(item.pacing, start, item.due_utc, t) * total - item.progress
                if behind <= 0:
                    continue
                deficit = self.lp.NumVar(0, total, "")
                self.lp.Add(deficit >= behind - self.lp.Sum(self.days_of(item.key, before=b)))
                deficits.append(deficit)
        return deficits

    def minimize(self, terms: dict[pywraplp.Variable, float]) -> float:
        objective = self.lp.Objective()
        objective.Clear()
        for v, coefficient in terms.items():
            objective.SetCoefficient(v, coefficient)
        objective.SetMinimization()
        status = self.lp.Solve()
        if status != pywraplp.Solver.OPTIMAL:
            raise RuntimeError(f"the allocator's LP ended with status {status}")
        return objective.Value()

    def solve(self) -> tuple[dict[str, list[float]], dict[str, float]]:
        late = self.lateness()
        if late:
            least = self.minimize(late)
            self.lp.Add(self.lp.Sum([c * v for v, c in late.items()]) <= least + TOLERANCE * max(1.0, least))
        self.minimize(self.shape())
        units = {it.key: [self.y[it.key, d].solution_value() if (it.key, d) in self.y else 0.0 for d in range(self.A)]
                 for it in self.todo}  # fmt: skip
        return units, {k: v.solution_value() for k, v in self.over.items()}


def apply_quotas(
    items: Iterable[EngineItem], allocation: Allocation, horizon_end_utc: int, units: Sequence[int] | None = None
) -> None:
    """Each item's quotas; work due past the horizon is capped at them. `units` (the grid's, per slot) counts locks."""
    for item in items:
        item.quotas = dict(allocation.quotas.get(item.key, {}))
        if item.amount == "fixed" and item.due_utc is not None and item.due_utc > horizon_end_utc:
            # Work due after the horizon goes in only as its quotas say: costing nothing either way, the rest
            # turned up as stray half hours of readings due three weeks later (M15).
            quota = sum(item.quotas.values())
            room = max(quota, item.min_chunk) if quota else 0
            # What's locked stays: a timer started on next week's paper is work now (its lock had been dropped).
            locked = int(sum(units[s] for s in item.locked)) if units is not None else 0
            item.need = min(item.need, max(room, locked))
