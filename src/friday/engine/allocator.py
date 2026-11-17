"""The allocator (DESIGN §13): how much of each item happens on which day over the coming weeks, and weekly quotas.

A linear program at day resolution, solved in two stages: lateness first, then pacing, whole-day prices and a
tie-break. Ties go as late as each paced item's pacing line and due date allow; work with no pace of its own
(`soon`) and items with no due date go as early as possible. Dependencies are handled outside the LP: a dependent
item's first day moves to the day its source is far enough along, and the LP is solved again until nothing moves.
GLOP's simplex is single-threaded and deterministic, so the same input gives the same allocation.
"""

import math
from bisect import bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date

from ortools.linear_solver import pywraplp

from friday.core.pace import DayScales, budget_factor
from friday.core.time import WEEKDAYS
from friday.engine.problem import EngineItem
from friday.engine.rules import Rule, matching_weekdays
from friday.engine.rules.measures import Reserve, pacing_fraction
from friday.engine.rules.prices import soon_urgency

POINTS_PER_UNIT = 25  # the engine's 100 points per hour, over four 15-minute units
OVERFLOW_POINTS = 100_000  # per unit left unallocated: worse than any placement
DEPTH_LEAN = 0.01  # how much later, per link of a chain of waits, an item leans in the tie-break
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
    capacity: list[int]  # what fixed work may fill each day: the room less what elastic and target items claim
    quotas: dict[str, dict[int, int]]  # item key → week → units
    # The room before those claims (the smaller of the daily cap and utilization × free time): the load ahead weighs
    # every block against it, meals and goals too (15 Nov: a client's week read 1 h over with nothing late, their meals'
    # and goals' blocks counted in its hours and taken off its room as well).
    room: list[int]
    # Work the allocator can't finish by its due (some of it on later days or left over): its quotas stay a must.
    tight: frozenset[str] = frozenset()

    def claimed(self) -> list[int]:
        """Per day, what elastic and target items took from the room before fixed work was placed."""
        return [r - c for r, c in zip(self.room, self.capacity, strict=True)]

    def day_totals(self) -> list[float]:
        """The planned load per day, shown in the weekly view."""
        return [sum(units[d] for units in self.units.values()) for d in range(len(self.capacity))]


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


def day_due(day_of: DayIndex, due_utc: int) -> int:
    """The day work must be done by: the one holding the due's last minute before it. Due as a day begins (4am), the
    day before; read as the day it begins, that whole day after the due counted as on time."""
    return day_of(due_utc - 1)


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
                share = item.target / (last - first) * budget_factor(inp.days[d].scales.target_amount, item.priority)
                caps[d] = max(0, caps[d] - round(share))


def allocate(inp: AllocatorInput) -> Allocation:
    caps = day_capacities(inp)
    room = list(caps)
    day_of = DayIndex(inp.days)
    claim_reserved_time(inp, caps, day_of)
    todo = [it for it in inp.items if it.amount == "fixed" and it.need > 0]
    ready: dict[str, int] = {}
    units: dict[str, list[float]] = {}
    over: dict[str, float] = {}
    # A ready day only ever moves later, so this settles; each round can delay at most one more chain link.
    for _ in range(len(todo) + 1):
        units, over = AllocatorLP(
            inp, caps, day_of, todo, ready, [r - c for r, c in zip(room, caps, strict=True)]
        ).solve()
        later = ready_days(todo, units, ready)
        if later == ready:
            break
        ready = later
    return Allocation(units, over, caps, quotas(inp, todo, units), room, tight(todo, units, over, day_of))


def tight(
    todo: list[EngineItem], units: dict[str, list[float]], over: dict[str, float], day_of: DayIndex
) -> frozenset[str]:
    """Items with work allocated after their due day, or left over."""
    out = set()
    for item in todo:
        if over.get(item.key, 0.0) > TOLERANCE:
            out.add(item.key)
        elif item.due_utc is not None:
            due = day_due(day_of, item.due_utc)
            if any(amount > TOLERANCE for amount in units[item.key][max(0, due + 1) :]):
                out.add(item.key)
    return frozenset(out)


def chain_depths(todo: list[EngineItem]) -> dict[str, int]:
    """How many links each item is down its chain of waits (0: it waits on nothing here)."""
    keys = {it.key: it for it in todo}
    depth: dict[str, int] = {}

    def of(key: str, seen: frozenset[str]) -> int:
        if key not in depth:
            sources = [d.key for d in keys[key].depends_on if d.key in keys and d.key not in seen]
            depth[key] = 1 + max((of(s, seen | {key}) for s in sources), default=-1)
        return depth[key]

    for key in keys:
        of(key, frozenset())
    return depth


def ready_days(todo: list[EngineItem], units: dict[str, list[float]], ready: dict[str, int]) -> dict[str, int]:
    """For each item that waits with a lag ("a day after"), the first day after its sources are far enough along,
    plus the lag. Waits without one aren't held to days here (17 Nov: a day for each link of a chain of short steps
    stretched it past its due): keep_behind_sources keeps them behind, and the scheduler after."""
    out = dict(ready)
    for item in todo:
        for dep in item.depends_on:
            if dep.key not in units or dep.required == 0 or dep.lag_min == 0:
                continue  # without a lag, keep_behind_sources holds the order and the scheduler the rest (17 Nov)
            done, day = 0.0, len(units[dep.key])
            for d, amount in enumerate(units[dep.key]):
                done += amount
                if done >= dep.required - TOLERANCE:
                    day = d + 1  # the source may end late in its day: the lag counts from the next
                    break
            day += math.ceil(dep.lag_min / 1440)
            out[item.key] = max(out.get(item.key, 0), day)
    return out


def effective_due_days(todo: list[EngineItem], day_of: DayIndex, caps: list[int]) -> dict[str, int | None]:
    """Due days, with a dependency source due early enough for its dependents to follow (after the lag) in time."""
    due = {it.key: day_due(day_of, it.due_utc) if it.due_utc is not None else None for it in todo}
    typical_cap = max(1.0, sum(caps) / len(caps))
    for _ in range(len(todo)):
        changed = False
        for item in todo:
            for dep in item.depends_on:
                own = due[item.key]
                if dep.key not in due or own is None:
                    continue
                # whole days the dependent needs after it: a dependent can start the day its source ends, so a
                # short step costs its source no day of its own (17 Nov: a chain of 45-minute steps "due" a week early)
                needed = own - math.ceil(dep.lag_min / 1440) - math.floor(item.need / typical_cap)
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
                 ready: dict[str, int], claimed: list[int] | None = None):  # fmt: skip
        self.inp, self.caps, self.day_of, self.todo = inp, caps, day_of, todo
        self.claimed = claimed if claimed is not None else [0] * len(caps)  # what goals and meals took, by day
        self.A = len(caps)
        self.lp = pywraplp.Solver.CreateSolver("GLOP")
        self.effective_due = self.aimed_for(effective_due_days(todo, day_of, caps))
        self.day_prices = self.whole_day_prices()
        self.y: dict[tuple[str, int], pywraplp.Variable] = {}
        self.over: dict[str, pywraplp.Variable] = {}
        for item in todo:
            self.add_item(item, ready.get(item.key, 0))
        self.keep_behind_sources()
        for d in range(self.A):
            today = [v for (_, dd), v in self.y.items() if dd == d]
            if today:
                self.lp.Add(self.lp.Sum(today) <= caps[d])

    def aimed_for(self, due: dict[str, int | None]) -> dict[str, int | None]:
        """Work you aim to finish some days early (a project's Finish early) aims for that day here, so the days are
        laid out to meet it when there's room; its due still bounds the hard lateness (17 Nov, the sweep: 3 hours
        planned after the aim with Monday left empty: only the scheduler's small price knew of it)."""
        early = [r for r in self.inp.rules if getattr(r, "type", None) == "finish_early"]  # those built are on
        out = dict(due)
        for item in self.todo:
            days = max((r.p.days for r in early if r.applies(item)), default=0)
            if days and out.get(item.key) is not None:
                out[item.key] = max(0, int(out[item.key]) - math.ceil(days))  # type: ignore[arg-type]
        return out

    def keep_behind_sources(self) -> None:
        """A dependent is never further along, as a share of its work, than what it waits on, day by day. The ready
        days only ever move later, so without this a source first placed on its due day pinned its dependents after
        the due, with weeks of room before it (17 Nov: a chain due after a busy weekend came out late)."""
        needs = {it.key: it.need for it in self.todo}
        for item in self.todo:
            for dep in item.depends_on:
                if dep.key not in needs or dep.required == 0 or needs[dep.key] <= 0 or dep.lag_min > 0:
                    continue  # a wait with a lag (spacing) is held by its ready day instead
                for d in range(self.A):
                    mine, theirs = self.days_of(item.key, before=d + 1), self.days_of(dep.key, before=d + 1)
                    if mine:
                        self.lp.Add(self.lp.Sum(mine) * needs[dep.key] <= self.lp.Sum(theirs) * item.need if theirs else
                                    self.lp.Sum(mine) <= 0)  # fmt: skip

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
            due_day = day_due(self.day_of, item.due_utc)
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
        terms |= self.heavy_days()
        depth = chain_depths(self.todo)
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
                # as late as the due date and pacing allow; what waits on more, a little later still, so what waits on
                # nothing (a free step, a chain's first) fills a pace first (17 Nov: free steps were left for last).
                # Work with no pace of its own as early as there's room, what's due first first (`soon`, 17 Nov: "by
                # default, friday should use all time that it can"); work with no due early too.
                lean = 1 + DEPTH_LEAN * depth[item.key]
                if item.soon and item.due_utc is not None:
                    terms[v] = price + d * soon_urgency(item.due_utc, self.inp.now_utc) * lean
                else:
                    terms[v] = price + (-d * lean if due_day is not None else d)
        return terms

    def heavy_days(self) -> dict[pywraplp.Variable, float]:
        """Units past a day's most (a daily_load rule's threshold, less what goals and meals claim), at that rule's
        price: work there as soon as it can be (`soon`) filled each day to the cap, and the scheduler, holding days
        to the threshold, left the rest of what the allocator gave the plan's days unplanned and uncounted (17 Nov:
        a 40-hour thesis read 31 hours in the load ahead)."""
        loads = [r for r in self.inp.rules if r.type == "daily_load"]
        out: dict[pywraplp.Variable, float] = {}
        for d, day in enumerate(self.inp.days):
            on = [r for r in loads if not r.p.days or WEEKDAYS[day.date.weekday()] in r.p.days]
            today = [v for (_, dd), v in self.y.items() if dd == d]
            if not on or not today:
                continue
            rule = min(on, key=lambda r: r.p.threshold)
            most = round(rule.p.threshold * day.scales.daily_load_threshold) - self.claimed[d]
            if sum(v.ub() for v in today) <= most:
                continue
            excess = self.lp.NumVar(0, self.lp.infinity(), "")
            self.lp.Add(excess >= self.lp.Sum(today) - most)
            out[excess] = rule.effective_weight * POINTS_PER_UNIT
        return out

    def pacing(self) -> list[pywraplp.Variable]:
        """Units behind each pacing line at every seventh day boundary: a project's steps on one line together, from
        the first's start to the last due, so steps that wait follow it with the rest (17 Nov: a line per step left a
        chain's later steps nothing to follow); other items on their own."""
        groups: dict[object, list[EngineItem]] = {}
        for item in self.todo:
            if item.pacing != "none" and item.due_utc is not None:
                groups.setdefault(
                    ("project", item.project, item.pacing) if item.project is not None else item.key, []
                ).append(item)
        deficits = []
        for members in groups.values():
            total = sum(it.need + it.progress for it in members)
            done = sum(it.progress for it in members)
            starts = [it.pacing_start_utc if it.pacing_start_utc is not None else self.inp.now_utc for it in members]
            due = max(it.due_utc for it in members if it.due_utc is not None)
            for b in range(7, self.A + 1, 7):
                t = self.inp.days[b].start_utc if b < self.A else self.inp.days[-1].end_utc
                behind = pacing_fraction(members[0].pacing, min(starts), due, t) * total - done
                if behind <= 0:
                    continue
                deficit = self.lp.NumVar(0, total, "")
                placed = [v for it in members for v in self.days_of(it.key, before=b)]
                self.lp.Add(deficit >= behind - self.lp.Sum(placed))
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
            if item.soon and item.key not in allocation.tight:
                # As soon as there's time, its quotas are what it may take, not what it must: held to them (the quota
                # rule, beside lateness), a week packed with far-off work skipped meals and left readings late, as
                # the allocator's days don't know them (17 Nov). Its own price (`soon`) fills the time there is.
                # Work that can't all be done by its due is held to them still: its lateness is at stake.
                item.quotas = {}
