"""Rule types (ENGINE_REFERENCE section 7).

Every rule is a slot price, a ban, or a linear measure with a convex hinge curve. The same objects feed
the evaluator and the CP-SAT baseline, so what a model optimises is what the evaluator reports.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Iterable, Literal

import numpy as np
from pydantic import BaseModel, BeforeValidator, ConfigDict

from .context import BuildContext
from .grid import planning_day_of
from .problem import EngineItem, FixedOcc, Problem
from .pwl import Hinge, Measure, curve_from_pairs
from .settings import MINUTES_PER_DAY, UNIT_MIN, WEEKDAYS

# ---------------------------------------------------------------- parsing helpers

_DUR = re.compile(r"^\s*(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*$")


def parse_units(v: Any) -> int:
    """'3h' / '40m' / '1h30m' -> units (rounded up); a bare number is already units."""
    if isinstance(v, (int, float)):
        return int(v)
    m = _DUR.match(str(v))
    if not m or not (m.group(1) or m.group(2)):
        raise ValueError(f"not a duration: {v!r}")
    minutes = float(m.group(1) or 0) * 60 + float(m.group(2) or 0)
    return math.ceil(minutes / UNIT_MIN - 1e-9)


def parse_clock(v: Any) -> int:
    if isinstance(v, int):
        return v
    h, m = str(v).split(":")
    return int(h) * 60 + int(m)


def parse_days(v: Any) -> tuple[int, ...] | None:
    if v is None:
        return None
    return tuple(WEEKDAYS.index(d.lower()[:3]) if isinstance(d, str) else int(d) for d in v)


Units = Annotated[int, BeforeValidator(parse_units)]
Clock = Annotated[int, BeforeValidator(parse_clock)]


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def _as_list(v: Any) -> list | None:
    if v is None:
        return None
    return list(v) if isinstance(v, (list, tuple, set)) else [v]


@dataclass
class Scope:
    area: Any = None
    tags: Any = None  # any of
    preset: Any = None
    energy: Any = None
    firmness: Any = None
    amount: Any = None
    title: Any = None
    title_regex: Any = None

    def matches(self, item: EngineItem) -> bool:
        def one(field_value: Any, wanted: Any) -> bool:
            w = _as_list(wanted)
            return w is None or field_value in w

        if not (one(item.area, self.area) and one(item.preset, self.preset) and one(item.energy, self.energy)
                and one(item.firmness, self.firmness) and one(item.amount, self.amount)):
            return False
        tags = _as_list(self.tags)
        if tags is not None and not any(t in item.tags for t in tags):
            return False
        titles = _as_list(self.title)
        if titles is not None and norm_title(item.title) not in [norm_title(t) for t in titles]:
            return False
        rx = _as_list(self.title_regex)
        if rx is not None and not any(re.search(r, item.title) for r in rx):
            return False
        return True


@dataclass
class EventScope:
    event_kind: Any = None
    title: Any = None
    tags: Any = None

    def matches(self, ev: FixedOcc) -> bool:
        k, t, tg = _as_list(self.event_kind), _as_list(self.title), _as_list(self.tags)
        if k is not None and ev.kind not in k:
            return False
        if t is not None and norm_title(ev.title) not in [norm_title(x) for x in t]:
            return False
        if tg is not None and not any(x in ev.tags for x in tg):
            return False
        return True


# ---------------------------------------------------------------- base class

RULE_TYPES: dict[str, type["Rule"]] = {}
FORBID = "forbid"


def rule_type(name: str):
    def deco(cls: type["Rule"]) -> type["Rule"]:
        cls.type = name
        RULE_TYPES[name] = cls
        return cls

    return deco


class Rule:
    type: ClassVar[str]
    default_stage: ClassVar[str] = "preferences"
    applies_to: ClassVar[set[str]] = {"fixed", "elastic", "target", "open"}

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    def __init__(self, name: str, *, weight: float = 1.0, stage: str | None = None,
                 scope: Scope | dict | None = None, reason: str | None = None, **params: Any):
        if weight < 0:
            raise ValueError("weights must be >= 0")
        self.name = name
        self.weight = weight
        self.stage = stage or self.default_stage
        self.scope = Scope(**scope) if isinstance(scope, dict) else scope
        self.reason = reason or name
        self.p = self.Params(**params)
        self.problem: Problem = None  # type: ignore[assignment]

    # -- hooks
    def prepare(self, problem: Problem) -> None:
        self.problem = problem

    def price(self, item: EngineItem, s: int) -> float:
        return 0.0

    def forbids(self, item: EngineItem, s: int) -> bool:
        return False

    def measures(self, ctx: BuildContext) -> Iterable[Measure]:
        return ()

    def day_mult(self, day: int) -> float:
        """Factor the day's dials put on this rule's weight (1 unless a dial touches it)."""
        return 1.0

    # -- applicability
    def _extra(self, item: EngineItem) -> bool:
        return True

    def applies(self, item: EngineItem) -> bool:
        return (item.amount in self.applies_to and (self.scope is None or self.scope.matches(item))
                and self._extra(item))

    @property
    def has_price(self) -> bool:
        return type(self).price is not Rule.price

    def scoped_items(self) -> list[EngineItem]:
        return [i for i in self.problem.items.values() if self.applies(i)]

    def __repr__(self) -> str:
        return f"{self.type}({self.name}, w={self.weight}, {self.stage})"


# ---------------------------------------------------------------- helpers shared by rules


def _lateness_price(rule: Rule, item: EngineItem, s: int, extra_hours: float) -> float:
    g = rule.problem.grid
    if item.due is None:
        return 0.0
    if s == g.S:
        if item.due <= g.horizon_end:
            return item.importance * (max(0.0, (g.horizon_end - item.due) / 60) + extra_hours)
        return 0.0
    return item.importance * max(0.0, (g.end[s] - item.due) / 60)


def _hour_window(local_minute: int, start: int | None, end: int | None) -> bool:
    """Is a minute-of-day inside [start, end), where the window may wrap midnight?"""
    if start is None and end is None:
        return True
    lo = 0 if start is None else start
    hi = MINUTES_PER_DAY if end is None else end
    if lo <= hi:
        return lo <= local_minute < hi
    return local_minute >= lo or local_minute < hi


# ---------------------------------------------------------------- deadlines stage


@rule_type("late_work")
class LateWork(Rule):
    default_stage = "deadlines"
    applies_to = {"fixed"}

    class Params(Rule.Params):
        overflow_extra_hours: float = 48

    def _extra(self, item):
        return item.firmness == "hard"

    def price(self, item, s):
        return _lateness_price(self, item, s, self.p.overflow_extra_hours)


@rule_type("late_tasks")
class LateTasks(Rule):
    """A fixed cost for each task that is late at all, on top of late_work's cost per unit and hour late. late_work alone
    prefers many tasks a little late to one task late; people count late tasks. Not in the reference rule set: the
    Friday app adds it (decision 38). `hours`: what a late task costs, in hours late of one unit of its work."""

    default_stage = "deadlines"
    applies_to = {"fixed"}

    class Params(Rule.Params):
        hours: float = 48
        # on top of late_work's cost per hour late, one that grows with the square, h^2 / square_hours per unit: four
        # days late costs twice what late_work alone charges, twelve days four times (0 = off). Chosen on the user's
        # week (decision 39): the latest task no later than it must be, urgent work first, total lateness near the least
        square_hours: float = 96

    def _extra(self, item):
        return item.firmness == "hard" and item.due is not None

    def price(self, item, s):
        if not self.p.square_hours or item.due is None:
            return 0.0
        g = self.problem.grid
        end = g.horizon_end + 48 * 60 if s == g.S else g.end[s]  # unplaced: as late as the horizon and two days more
        h = max(0.0, (end - item.due) / 60)
        return item.importance * h * h / self.p.square_hours

    def measures(self, ctx):
        g = ctx.grid
        for it in self.scoped_items():
            late = [(it.key, s) for s in it.allowed if s < g.S and g.end[s] > it.due]
            expr = ctx.any_of(f"lt:{it.key}", late)
            if not expr.is_const():
                yield Measure(f"{self.name}:{it.key}", expr, "count", (Hinge("above", 0, it.importance * self.p.hours),))
            # work left unplaced is late too: each unit costs as much as a late task, so leaving it off the plan never
            # dodges the count
            yield Measure(f"{self.name}:{it.key}:over", ctx.over(it.key), "units",
                          (Hinge("above", 0, 4 * it.importance * self.p.hours),))


@rule_type("quota")
class Quota(Rule):
    default_stage = "deadlines"

    def _extra(self, item):
        return bool(item.quotas)

    def measures(self, ctx):
        g = ctx.grid
        for item in self.scoped_items():
            for week, q in sorted(item.quotas.items()):
                slots = g.week_slots.get(week)
                if not slots:
                    continue
                expr = ctx.placed_in(item.key, slots) + item.progress_by_week.get(week, 0)
                yield Measure(f"{self.name}:{item.key}:w{week}", expr, "units", (Hinge("below", q, 1.0),))


# ---------------------------------------------------------------- wellbeing stage


@rule_type("late_night")
class LateNight(Rule):
    default_stage = "wellbeing"

    class Params(Rule.Params):
        gradient_start: Clock = 22 * 60
        a: float = 2
        b: float = 20
        debt_factor: float = 0.5

    def day_mult(self, day):
        return self.problem.scales[day].rest

    def price(self, item, s):
        g = self.problem.grid
        if s == g.S:
            return 0.0
        slot = g.slots[s]
        night = self.problem.nights[slot.date]
        tau = (slot.end - slot.date * MINUTES_PER_DAY) / 60
        bed = (night.bedtime - slot.date * MINUTES_PER_DAY) / 60
        grad = self.p.gradient_start / 60
        m = 1 + self.p.debt_factor * self.problem.scales[slot.day].rest * night.debt_hours
        return self.p.a * max(0.0, min(tau, bed) - grad) + self.p.b * m * max(0.0, tau - bed)


@rule_type("deep_run")
class DeepRun(Rule):
    default_stage = "wellbeing"

    class Params(Rule.Params):
        threshold: Units = 12

    def __init__(self, name, **kw):
        kw.setdefault("scope", Scope(energy="deep"))
        super().__init__(name, **kw)

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        items = self.scoped_items()
        if not items:
            return
        usable = np.zeros(g.S, dtype=np.int64)  # in-scope units available per slot
        for it in items:
            for s in it.allowed:
                usable[s] = g.units[s]
        for a in range(g.S):
            k = max(4, round(self.p.threshold * prob.scale_of(a).capacity))
            u, b = 0, a
            while b < g.S and u < k + 1:
                u += int(g.units[b])
                b += 1
            if u < k + 1:
                continue
            if usable[a:b].sum() < k + 1:
                continue
            expr = Lin_sum(ctx.placed_in(it.key, range(a, b)) for it in items)
            if expr.is_const():
                continue
            yield Measure(f"{self.name}@{a}", expr, "units", (Hinge("above", k, 1.0),))


def Lin_sum(parts: Iterable):
    from .pwl import Lin

    out = Lin()
    for p in parts:
        out += p
    return out


@rule_type("reserve")
class Reserve(Rule):
    default_stage = "wellbeing"

    class Params(Rule.Params):
        days: Any = None
        days_except: Any = None
        start: Clock | None = None
        end: Clock | None = None
        free: Units = 8

    def _days(self) -> set[int]:
        incl, excl = parse_days(self.p.days), parse_days(self.p.days_except)
        return {d for d in range(7) if (incl is None or d in incl) and (excl is None or d not in excl)}

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        days = self._days()
        for d in range(g.n_days):
            ix = g.day_slots[d]
            if not ix or g.slots[ix[0]].weekday not in days:
                continue
            win = [s for s in ix if _hour_window(g.slots[s].local_minute, self.p.start, self.p.end)]
            if not win:
                continue
            free_units = sum(int(g.units[s]) for s in win if not (prob.blocked[s] or prob.core[s]))
            keep = round(self.p.free * prob.scales[d].rest)
            theta = max(0, free_units - keep)
            can_work = sum(int(g.units[s]) for s in win if any(s in it.allowed_set for it in prob.items.values()))
            if can_work <= theta:
                continue
            yield Measure(f"{self.name}@d{d}", ctx.busy_units(win), "units", (Hinge("above", theta, 1.0),))


@rule_type("daily_load")
class DailyLoad(Rule):
    default_stage = "wellbeing"

    class Params(Rule.Params):
        threshold: Units = 32

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        items = self.scoped_items()
        for d in range(g.n_days):
            theta = round(self.p.threshold * prob.scales[d].capacity)
            slots = g.day_slots[d]
            expr = Lin_sum(ctx.placed_in(it.key, slots) for it in items)
            if expr.is_const() or sum(expr.terms.values()) <= theta:
                continue
            yield Measure(f"{self.name}@d{d}", expr, "units", (Hinge("above", theta, 1.0),))


@rule_type("even_load")
class EvenLoad(Rule):
    default_stage = "wellbeing"
    applies_to = {"fixed"}

    def __init__(self, name, **kw):
        kw.setdefault("scope", Scope(firmness="hard"))
        super().__init__(name, **kw)

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        items = [i for i in self.scoped_items() if i.due is not None and i.due <= g.horizon_end]
        if not items:
            return
        total = sum(i.need for i in items)
        latest = max(i.due for i in items)
        n = 0
        for d in range(g.n_days):
            ix = g.day_slots[d]
            if ix and g.start[ix[0]] < latest and any(not (prob.blocked[s] or prob.core[s]) for s in ix):
                n += 1
        if n == 0 or total == 0:
            return
        e = math.ceil(total / n)
        for d in range(g.n_days):
            expr = Lin_sum(ctx.placed_in(it.key, g.day_slots[d]) for it in items)
            if expr.is_const() or sum(expr.terms.values()) <= e:
                continue
            yield Measure(f"{self.name}@d{d}", expr, "units", (Hinge("above", e, 1.0),),
                          mult=prob.scales[d].spread)


# ---------------------------------------------------------------- preferences stage


@rule_type("time_preference")
class TimePreference(Rule):
    default_stage = "preferences"

    class Params(Rule.Params):
        days: Any = None
        days_except: Any = None
        start: Clock | None = None
        end: Clock | None = None
        price: float | Literal["forbid"] = 1.0

    def prepare(self, problem):
        super().prepare(problem)
        incl, excl = parse_days(self.p.days), parse_days(self.p.days_except)
        self._days = {d for d in range(7) if (incl is None or d in incl) and (excl is None or d not in excl)}

    def _match(self, s: int) -> bool:
        slot = self.problem.grid.slots[s]
        return slot.weekday in self._days and _hour_window(slot.local_minute, self.p.start, self.p.end)

    def price(self, item, s):
        if s == self.problem.grid.S or self.p.price == FORBID:
            return 0.0
        return float(self.p.price) if self._match(s) else 0.0

    def forbids(self, item, s):
        return self.p.price == FORBID and self._match(s)


@rule_type("energy")
class Energy(Rule):
    def __init__(self, name, **kw):
        kw.setdefault("scope", Scope(energy="deep"))
        super().__init__(name, **kw)

    def price(self, item, s):
        g = self.problem.grid
        if s == g.S:
            return 0.0
        slot = g.slots[s]
        return float(self.problem.energy_map[slot.weekday][slot.local_minute // 60])


@rule_type("soft_late")
class SoftLate(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        overflow_extra_hours: float = 48

    def _extra(self, item):
        return item.firmness == "soft"

    def price(self, item, s):
        return _lateness_price(self, item, s, self.p.overflow_extra_hours)


@rule_type("finish_early")
class FinishEarly(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        days: float = 2.0

    def _extra(self, item):
        return item.due is not None

    def price(self, item, s):
        g = self.problem.grid
        end = g.horizon_end if s == g.S else int(g.end[s])
        lead = self.p.days
        return min(lead, max(0.0, (end - (item.due - lead * MINUTES_PER_DAY)) / MINUTES_PER_DAY))


@rule_type("unscheduled")
class Unscheduled(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        base: float = 1.0

    def _extra(self, item):
        g = self.problem.grid
        return not (item.firmness == "hard" and item.due is not None and item.due <= g.horizon_end)

    def price(self, item, s):
        return self.p.base * item.importance if s == self.problem.grid.S else 0.0


@rule_type("after_event")
class AfterEvent(Rule):
    class Params(Rule.Params):
        events: Any = None
        measure_from: Literal["last", "any"] = "last"
        slope: float = 1.0
        cap: float = 4.0
        on_days_without: Literal["ignore", "cap"] = "ignore"

    def prepare(self, problem):
        super().prepare(problem)
        es = EventScope(**self.p.events) if isinstance(self.p.events, dict) else self.p.events
        self._ends: dict[int, list[int]] = {}
        for ev in problem.fixed:
            if es is None or es.matches(ev):
                day = planning_day_of(ev.start, problem.settings.day_start)
                self._ends.setdefault(day, []).append(ev.blocked_hi)
        for v in self._ends.values():
            v.sort()

    def price(self, item, s):
        g = self.problem.grid
        if s == g.S:
            return 0.0
        slot = g.slots[s]
        ends = self._ends.get(slot.date)
        if not ends:
            return self.p.cap if self.p.on_days_without == "cap" else 0.0
        if self.p.measure_from == "last":
            ref = ends[-1]
        else:
            before = [e for e in ends if e <= slot.start]
            if not before:
                return self.p.cap
            ref = before[-1]
        if slot.start < ref:
            return self.p.cap
        return min(self.p.cap, self.p.slope * (slot.start - ref) / 60)


@rule_type("chunk_cost")
class ChunkCost(Rule):
    def _extra(self, item):
        return item.shape == "split" and item.chunk_cost > 0

    def measures(self, ctx):
        g = ctx.grid
        for it in self.scoped_items():
            expr = Lin_sum(ctx.start(it.key, s) for s in it.allowed)
            if expr.is_const():
                continue
            yield Measure(f"{self.name}:{it.key}", expr, "count",
                          (Hinge("above", 1, it.chunk_cost * it.size_hours),))


@rule_type("spread")
class Spread(Rule):
    applies_to = {"fixed"}

    def _extra(self, item):
        return item.spread == "spread"

    def measures(self, ctx):
        g = ctx.grid
        for it in self.scoped_items():
            days = [d for d in range(g.n_days) if any(s in it.allowed_set for s in g.day_slots[d])]
            if not days:
                continue
            e = math.ceil(it.need / len(days))
            for d in days:
                expr = ctx.placed_in(it.key, g.day_slots[d])
                if sum(expr.terms.values()) <= e:
                    continue
                yield Measure(f"{self.name}:{it.key}@d{d}", expr, "units", (Hinge("above", e, 1.0),))


@rule_type("cluster")
class Cluster(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        per_day: float = 2.0

    def _extra(self, item):
        return item.spread == "cluster"

    def measures(self, ctx):
        g = ctx.grid
        for it in self.scoped_items():
            expr = Lin_sum(
                ctx.any_of(f"cl:{it.key}:d{d}", [(it.key, s) for s in g.day_slots[d]]) for d in range(g.n_days)
            )
            if expr.is_const():
                continue
            yield Measure(f"{self.name}:{it.key}", expr, "count", (Hinge("above", 1, self.p.per_day),))


@rule_type("batch_by_day")
class BatchByDay(Rule):
    class Params(Rule.Params):
        by: Literal["area", "preset"] = "area"

    def measures(self, ctx):
        g = ctx.grid
        groups: dict[Any, list[EngineItem]] = {}
        for it in self.scoped_items():
            groups.setdefault(getattr(it, self.p.by), []).append(it)
        for grp, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
            if len(members) < 2:
                continue
            expr = Lin_sum(
                ctx.any_of(f"bb:{self.name}:{grp}:d{d}", [(m.key, s) for m in members for s in g.day_slots[d]])
                for d in range(g.n_days)
            )
            if expr.is_const():
                continue
            yield Measure(f"{self.name}:{grp}", expr, "count", (Hinge("above", 1, 1.0),))


def _window_growth(prob: Problem, item: EngineItem) -> tuple[float, float]:
    """(share of the window inside the horizon, mean growth dial over the window's days)."""
    g = prob.grid
    rel = g.now if item.release is None else max(item.release, g.now)
    hi = g.horizon_end if item.due is None else min(item.due, g.horizon_end)
    full = (item.due - (item.release if item.release is not None else g.now)) if item.due is not None else None
    share = 1.0 if not full or full <= 0 else max(0.0, min(1.0, (hi - rel) / full))
    days = {g.slots[s].day for s in item.allowed} or {0}
    return share, float(np.mean([prob.scales[d].growth for d in days]))


@rule_type("target_shortfall")
class TargetShortfall(Rule):
    applies_to = {"target"}

    class Params(Rule.Params):
        curve: list[list[float]] = [[0.4, 8.0], [1.0, 3.0]]

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        for it in self.scoped_items():
            share, growth = _window_growth(prob, it)
            t_eff = it.target * share * growth
            expr = ctx.placed_in(it.key, it.allowed) + it.progress
            curve = curve_from_pairs("below", [tuple(p) for p in self.p.curve], t_eff)
            yield Measure(f"{self.name}:{it.key}", expr, "units", curve, mult=growth)


@rule_type("elastic_shortfall")
class ElasticShortfall(Rule):
    applies_to = {"elastic"}

    class Params(Rule.Params):
        steep: float = 20.0
        gentle: float = 2.0

    def measures(self, ctx):
        for it in self.scoped_items():
            expr = ctx.placed_in(it.key, it.allowed)
            yield Measure(f"{self.name}:{it.key}", expr, "units",
                          (Hinge("below", it.min, self.p.steep), Hinge("below", it.ideal, self.p.gentle)))


@rule_type("open_value")
class OpenValue(Rule):
    applies_to = {"open"}

    class Params(Rule.Params):
        curve: list[list[float]] = [[0.5, 1.0], [1.0, 0.5]]

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        for it in self.scoped_items():
            for d in range(g.n_days):
                slots = [s for s in g.day_slots[d] if s in it.allowed_set]
                if not slots:
                    continue
                expr = ctx.placed_in(it.key, slots) + (it.progress_today if d == 0 else 0)
                curve = curve_from_pairs("below", [tuple(p) for p in self.p.curve], it.daily_ceiling)
                yield Measure(f"{self.name}:{it.key}@d{d}", expr, "units", curve, mult=prob.scales[d].growth)


@rule_type("minimize_changes")
class MinimizeChanges(Rule):
    class Params(Rule.Params):
        preferred_multiplier: float = 10.0

    def _extra(self, item):
        return item.amount != "open" and not item.tentative and bool(item.current)

    def measures(self, ctx):
        g, prob = ctx.grid, ctx.problem
        mult = prob.settings.minimize_changes_scale
        for it in self.scoped_items():
            keep = [s for s in it.current if s in it.allowed_set]
            for tag, slots, slope in (
                ("n", [s for s in keep if s not in it.preferred], 1.0),
                ("p", [s for s in keep if s in it.preferred], self.p.preferred_multiplier),
            ):
                if not slots:
                    continue
                units = sum(int(g.units[s]) for s in slots)
                expr = Lin_sum(ctx.placed_in(it.key, [s]) * -1 for s in slots) + units
                yield Measure(f"{self.name}:{it.key}:{tag}", expr, "units", (Hinge("above", 0, slope),), mult=mult)


# ---------------------------------------------------------------- price tables


def price_row(problem: Problem, rule: Rule, item: EngineItem) -> np.ndarray:
    """Integer cost (scaled points) of item occupying each slot; entry S is the cost per overflow unit.

    round(weight * dial * price * hours(s) * scale) per slot, and round(weight * price(S) * 0.25 * scale)
    per overflow unit, exactly as the reference's price table (6A.5).
    """
    key = (rule.name, item.key)
    cached = problem._price_cache.get(key)
    if cached is not None:
        return cached
    g, scale = problem.grid, problem.settings.scale
    row = np.zeros(g.S + 1, dtype=np.int64)
    for s in item.allowed:
        w = rule.weight * rule.day_mult(g.slots[s].day)
        row[s] = round(w * rule.price(item, s) * 0.25 * int(g.units[s]) * scale)
    row[g.S] = round(rule.weight * rule.price(item, g.S) * 0.25 * scale)
    problem._price_cache[key] = row
    return row
