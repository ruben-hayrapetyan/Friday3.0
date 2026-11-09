"""Measure rules (DESIGN §12.2): a linear quantity of the plan with a convex hinge curve."""

import math
from collections.abc import Iterator
from typing import Any, Literal

import numpy as np

from friday.engine.pwl import Hinge, Lin, Measure, curve_from_pairs, lin_sum
from friday.engine.rules import Clock, Rule, Units, in_hour_window, matching_weekdays, rule_type

ONE_HOUR_UNITS = 4


@rule_type("quota")
class Quota(Rule):
    default_stage = "deadlines"

    def applies_also(self, item):
        return bool(item.quotas)

    def measures(self, ctx):
        for item in self.scoped_items():
            for week, quota in sorted(item.quotas.items()):
                slots = ctx.grid.week_slots.get(week)
                if not slots:
                    continue
                expr = ctx.placed_in(item.key, slots) + item.progress_by_week.get(week, 0)
                yield Measure(f"{self.name}:{item.key}:w{week}", expr, "units", (Hinge("below", quota, 1.0),))


@rule_type("deep_run")
class DeepRun(Rule):
    default_stage = "wellbeing"
    default_scope = {"energy": "deep"}

    class Params(Rule.Params):
        threshold: Units = 12

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        items = self.scoped_items()
        if not items:
            return
        usable = np.zeros(grid.S, dtype=np.int64)  # in-scope units available per slot
        terms_at: list[list[tuple[tuple[str, str, int], int]]] = [[] for _ in range(grid.S)]
        for item in items:
            for s in item.allowed:
                usable[s] = grid.units[s]
                terms_at[s].append((("x", item.key, s), int(grid.units[s])))
        for a in range(grid.S):
            limit = max(ONE_HOUR_UNITS, round(self.p.threshold * problem.scale_of(a).deep_run_threshold))
            units, b = 0, a
            while b < grid.S and units < limit + 1:
                units += int(grid.units[b])
                b += 1
            if units < limit + 1 or usable[a:b].sum() < limit + 1:
                continue
            expr = Lin(dict(term for s in range(a, b) for term in terms_at[s]))
            if not expr.is_const():
                yield Measure(f"{self.name}@{a}", expr, "units", (Hinge("above", limit, 1.0),))


@rule_type("reserve")
class Reserve(Rule):
    default_stage = "wellbeing"

    class Params(Rule.Params):
        days: Any = None
        days_except: Any = None
        start: Clock | None = None
        end: Clock | None = None
        free: Units = 8

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        weekdays = matching_weekdays(self.p.days, self.p.days_except)
        for d in range(grid.n_days):
            slots = grid.day_slots[d]
            if not slots or grid.slots[slots[0]].weekday not in weekdays:
                continue
            window = [s for s in slots if in_hour_window(grid.slots[s].local_minute, self.p.start, self.p.end)]
            if not window:
                continue
            # An evening kept free until 11:59pm keeps the rest of that night too: otherwise the work it holds off
            # lands just past midnight, later than the evening it was kept from.
            night = []
            end = 1440 if self.p.end == 0 else self.p.end  # until midnight is the end of the evening, not its start
            if self.p.start is not None and end is not None and self.p.start < end >= NIGHT_FROM:
                night = [s for s in slots if grid.slots[s].day_minute >= end and s not in window]
            window += night
            free_units = sum(int(grid.units[s]) for s in window if not (problem.blocked[s] or problem.core[s]))
            free_night = sum(int(grid.units[s]) for s in night if not (problem.blocked[s] or problem.core[s]))
            theta = max(0, free_units - round(self.p.free * problem.scales[d].reserve_free) - free_night)
            items = self.scoped_items()  # all work by default; a meal in the evening isn't work taking the evening
            workable = sum(int(grid.units[s]) for s in window if any(s in it.allowed_set for it in items))
            if workable > theta:
                yield Measure(
                    f"{self.name}@d{d}", ctx.busy_units(window, items), "units", (Hinge("above", theta, 1.0),)
                )


NIGHT_FROM = 23 * 60 + 30  # a free window ending this late is an evening, which runs on into the night


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@rule_type("daily_load")
class DailyLoad(Rule):
    """At most `threshold` of work a day; with `days`, on those weekdays only (`at most 4h a day on weekends` held
    every day, 27 Oct)."""

    default_stage = "wellbeing"

    class Params(Rule.Params):
        threshold: Units = 32
        days: list[str] = []  # weekdays, "mon"…"sun"; none is every day

    def on(self, d: int) -> bool:
        day = self.problem.grid.day_date[d]
        return not self.p.days or (day is not None and WEEKDAYS[day.weekday()] in self.p.days)

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        items = self.scoped_items()
        for d in range(grid.n_days):
            if not self.on(d):
                continue
            theta = round(self.p.threshold * problem.scales[d].daily_load_threshold)
            expr = lin_sum(ctx.placed_in(item.key, grid.day_slots[d]) for item in items)
            if not expr.is_const() and sum(expr.terms.values()) > theta:
                yield Measure(f"{self.name}@d{d}", expr, "units", (Hinge("above", theta, 1.0),))


@rule_type("even_load")
class EvenLoad(Rule):
    default_stage = "wellbeing"
    default_scope = {"firmness": "hard"}
    applies_to = {"fixed"}

    class Params(Rule.Params):
        # Below this a day isn't heavy: evening it out cut a 2-hour assignment into half-hour pieces on three days,
        # which no chunk cost could undo (a preference, a stage below). 3 hours is one long sitting, as deep_run has.
        floor: Units = 12

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        items = [i for i in self.scoped_items() if i.due_utc is not None and i.due_utc <= grid.horizon_end]
        if not items:
            return
        total = sum(i.need for i in items)
        latest = max(i.due_utc for i in items)
        days_with_time = sum(
            1
            for d in range(grid.n_days)
            if grid.day_slots[d]
            and grid.start[grid.day_slots[d][0]] < latest
            and any(not (problem.blocked[s] or problem.core[s]) for s in grid.day_slots[d])
        )
        if days_with_time == 0 or total == 0:
            return
        share = max(math.ceil(total / days_with_time), self.p.floor)
        for d in range(grid.n_days):
            expr = lin_sum(ctx.placed_in(item.key, grid.day_slots[d]) for item in items)
            if not expr.is_const() and sum(expr.terms.values()) > share:
                yield Measure(f"{self.name}@d{d}", expr, "units", (Hinge("above", share, 1.0),),
                              mult=problem.scales[d].even_load_weight)  # fmt: skip


@rule_type("chunk_cost")
class ChunkCost(Rule):
    def applies_also(self, item):
        return item.shape == "split" and item.chunk_cost > 0

    def measures(self, ctx):
        for item in self.scoped_items():
            expr = lin_sum(ctx.start(item.key, s) for s in item.allowed)
            if not expr.is_const():
                curve = (Hinge("above", 1, item.chunk_cost * item.size_hours),)
                yield Measure(f"{self.name}:{item.key}", expr, "count", curve)


@rule_type("spread")
class Spread(Rule):
    applies_to = {"fixed"}

    def applies_also(self, item):
        return item.spread == "spread"

    def measures(self, ctx):
        grid = ctx.grid
        for item in self.scoped_items():
            days = [d for d in range(grid.n_days) if any(s in item.allowed_set for s in grid.day_slots[d])]
            if not days:
                continue
            share = math.ceil(item.need / len(days))
            for d in days:
                expr = ctx.placed_in(item.key, grid.day_slots[d])
                if sum(expr.terms.values()) > share:
                    yield Measure(f"{self.name}:{item.key}@d{d}", expr, "units", (Hinge("above", share, 1.0),))


@rule_type("cluster")
class Cluster(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        per_day: float = 2.0

    def applies_also(self, item):
        return item.spread == "cluster"

    def measures(self, ctx):
        grid = ctx.grid
        for item in self.scoped_items():
            days_used = lin_sum(
                ctx.any_of(f"cl:{item.key}:d{d}", [(item.key, s) for s in grid.day_slots[d]])
                for d in range(grid.n_days)
            )
            if not days_used.is_const():
                curve = (Hinge("above", 1, self.p.per_day),)
                yield Measure(f"{self.name}:{item.key}", days_used, "count", curve)


@rule_type("batch_by_day")
class BatchByDay(Rule):
    class Params(Rule.Params):
        by: Literal["area", "preset"] = "area"

    def measures(self, ctx):
        grid = ctx.grid
        groups: dict[Any, list[Any]] = {}
        for item in self.scoped_items():
            groups.setdefault(getattr(item, self.p.by), []).append(item)
        for group, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
            if len(members) < 2:
                continue
            days_used = lin_sum(
                ctx.any_of(f"bb:{self.name}:{group}:d{d}", [(m.key, s) for m in members for s in grid.day_slots[d]])
                for d in range(grid.n_days)
            )
            if not days_used.is_const():
                yield Measure(f"{self.name}:{group}", days_used, "count", (Hinge("above", 1, 1.0),))


def course_groups(items: list[Any]) -> dict[str, list[Any]]:
    """Work grouped by its subject (`EngineItem.course`, read from titles by the planner: core/guess.py `subjects`).
    Work without one (laundry, a meal) isn't in any group."""
    out: dict[str, list[Any]] = {}
    for item in items:
        if item.course:
            out.setdefault(item.course, []).append(item)
    return out


@rule_type("same_course")
class SameCourse(Rule):
    """One course for a stretch of work (8 Nov, the 5:15pm screenshot: "i would wanna do math for the entire time not
    3 different things"): each time the work goes straight on from one course to another costs one count. A slot of
    course c right after a slot of another course: (other course's work at s) + (c's work at s + 1) above 1. A free
    slot or an event between them isn't going straight on. A preference, so it never makes work late."""

    def measures(self, ctx):
        grid = ctx.grid
        groups = course_groups([i for i in self.scoped_items() if i.allowed])
        if len(groups) < 2:
            return
        course_at: dict[str, str] = {m.key: c for c, members in groups.items() for m in members}
        for s in range(grid.S - 1):
            if grid.end[s] != grid.start[s + 1]:
                continue
            here = [k for k, c in course_at.items() if s in ctx.problem.items[k].allowed_set]
            if not here:
                continue
            for course, members in sorted(groups.items()):
                into = Lin({("x", m.key, s + 1): 1 for m in members if s + 1 in m.allowed_set})
                if into.is_const():
                    continue
                before = [k for k in here if course_at[k] != course]
                if before:
                    expr = Lin({**{("x", k, s): 1 for k in before}, **into.terms})
                    yield Measure(f"{self.name}:{course}@{s}", expr, "count", (Hinge("above", 1, 1.0),))


def window_share_and_growth(problem: Any, item: Any) -> tuple[float, float, float]:
    """(share of the target's window inside the horizon, mean amount factor, mean weight factor) over its days."""
    grid = problem.grid
    release = grid.now if item.release_utc is None else max(item.release_utc, grid.now)
    end = grid.horizon_end if item.due_utc is None else min(item.due_utc, grid.horizon_end)
    full = None
    if item.due_utc is not None:
        full = item.due_utc - (item.release_utc if item.release_utc is not None else grid.now)
    share = 1.0 if not full or full <= 0 else max(0.0, min(1.0, (end - release) / full))
    days = {grid.slots[s].day for s in item.allowed} or {0}
    amount = float(np.mean([problem.scales[d].target_amount for d in days]))
    weight = float(np.mean([problem.scales[d].target_weight for d in days]))
    return share, amount, weight


@rule_type("target_shortfall")
class TargetShortfall(Rule):
    applies_to = {"target"}

    class Params(Rule.Params):
        curve: list[list[float]] = [[0.4, 8.0], [1.0, 3.0]]

    def measures(self, ctx):
        for item in self.scoped_items():
            share, amount, weight = window_share_and_growth(ctx.problem, item)
            expr = ctx.placed_in(item.key, item.allowed) + item.progress
            curve = curve_from_pairs("below", [tuple(p) for p in self.p.curve], item.target * share * amount)
            yield Measure(f"{self.name}:{item.key}", expr, "units", curve, mult=weight)


@rule_type("elastic_shortfall")
class ElasticShortfall(Rule):
    applies_to = {"elastic"}

    class Params(Rule.Params):
        steep: float = 20.0
        gentle: float = 2.0

    def measures(self, ctx):
        for item in self.scoped_items():
            expr = ctx.placed_in(item.key, item.allowed)
            pairs = ((item.min, self.p.steep), (item.ideal, self.p.gentle))
            curve = tuple(Hinge("below", at, slope) for at, slope in pairs if slope > 0)  # one stage's part only
            yield Measure(f"{self.name}:{item.key}", expr, "units", curve)


@rule_type("open_value")
class OpenValue(Rule):
    applies_to = {"open"}

    class Params(Rule.Params):
        curve: list[list[float]] = [[0.5, 1.0], [1.0, 0.5]]

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        for item in self.scoped_items():
            for d in range(grid.n_days):
                slots = [s for s in grid.day_slots[d] if s in item.allowed_set]
                if not slots:
                    continue
                expr = ctx.placed_in(item.key, slots) + (item.progress_today if d == 0 else 0)
                curve = curve_from_pairs("below", [tuple(p) for p in self.p.curve], item.daily_ceiling)
                yield Measure(f"{self.name}:{item.key}@d{d}", expr, "units", curve,
                              mult=problem.scales[d].open_value_slopes)  # fmt: skip


@rule_type("minimize_changes")
class MinimizeChanges(Rule):
    """Where work was planned stays, unless something matters more. `which` splits it (29 Oct: "why is friday
    scheduling 'Email professors for research opportunities' that doesn't have a deadline over something that has
    one"): "dated", work with a due, and any pinned or timed time; "undated", the rest of undated work's place, which
    the planner weighs among preferences, so work that's due takes that time first."""

    class Params(Rule.Params):
        preferred_multiplier: float = 10.0
        which: Literal["all", "dated", "undated"] = "all"

    def applies_also(self, item):
        if item.amount == "open" or item.tentative or not item.current:
            return False
        return self.p.which != "undated" or item.due_utc is None

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        for item in self.scoped_items():
            kept = [s for s in item.current if s in item.allowed_set]
            for tag, slots, slope in (
                ("n", [s for s in kept if s not in item.preferred and s not in item.held], 1.0),
                ("p", [s for s in kept if s in item.preferred or s in item.held], self.p.preferred_multiplier),
            ):
                if not slots or not self.holds(item, tag):
                    continue
                units = sum(int(grid.units[s]) for s in slots)
                given_up = lin_sum(ctx.placed_in(item.key, [s]) * -1 for s in slots) + units
                # A loosened replan (after a pace or rule change) lets go of where things were, not of your pins.
                mult = problem.minimize_changes_scale if tag == "n" else 1.0
                yield Measure(f"{self.name}:{item.key}:{tag}", given_up, "units", (Hinge("above", 0, slope),),
                              mult=mult)  # fmt: skip

    def holds(self, item, tag: str) -> bool:
        """Whether this rule holds `tag`'s slots ("n" planned, "p" pinned or timed) of `item`."""
        if self.p.which == "all":
            return True
        undated_plain = item.due_utc is None and tag == "n"
        return undated_plain if self.p.which == "undated" else not undated_plain


@rule_type("pin_hold")
class PinHold(Rule):
    """A pin holds (27 Oct: "my pinned timeslots keep moving"): each hour of a pin's time given up costs `price`. The
    planner builds it in beside your rules in the deadlines stage (planner/build.py), so a later evening or a heavy
    day never moves a pin, and work that would be late still does. The timer's hold is minimize_changes' alone."""

    default_stage = "wellbeing"

    class Params(Rule.Params):
        price: float = 100.0

    def measures(self, ctx):
        grid = ctx.grid
        for item in self.scoped_items():
            slots = [s for s in item.preferred if s in item.allowed_set]
            if not slots:
                continue
            units = sum(int(grid.units[s]) for s in slots)
            given_up = lin_sum(ctx.placed_in(item.key, [s]) * -1 for s in slots) + units
            yield Measure(f"{self.name}:{item.key}", given_up, "units", (Hinge("above", 0, self.p.price),))


@rule_type("buffer")
class Buffer(Rule):
    """Breathing room before a block: a chunk that starts right after other work or a fixed event costs, per unit of
    that work inside its buffer. An item's buffer is the largest of `minutes`, its area's and its preset's.

    An item's own travel (lunch: 15 minutes to get there and back) keeps other work out on both sides. A busy event
    counts before it, but not the event's own gap: the walk from a class to lunch is one walk, not two."""

    default_stage = "wellbeing"

    class Params(Rule.Params):
        minutes: Units = 0
        by_area: dict[str, Units] = {}
        by_preset: dict[str, Units] = {}

    def buffer_of(self, item: Any) -> int:
        return max(self.p.minutes, self.p.by_area.get(item.area or "", 0), self.p.by_preset.get(item.preset or "", 0))

    def measures(self, ctx):
        grid, problem = ctx.grid, ctx.problem
        groups: dict[int, list[Any]] = {}
        for item in self.scoped_items():
            if (b := self.buffer_of(item)) > 0:
                groups.setdefault(b, []).append(item)
        for b, members in sorted(groups.items()):
            for s in range(grid.S):
                starts = lin_sum(ctx.start(m.key, s) for m in members)
                window = before(grid, s, b)
                if starts.is_const() or not window:
                    continue
                # g = b × (a chunk starts here) + work in the buffer; above b only when something starts.
                fixed = sum(int(grid.units[w]) for w in window if problem.blocked[w] and not problem.core[w])
                expr = starts * b + ctx.busy_units(window) + fixed
                yield Measure(f"{self.name}:b{b}@{s}", expr, "units", (Hinge("above", b, 1.0),))
        yield from travel_measures(self, ctx, self.scoped_items(), 1.0)


@rule_type("travel_kept")
class TravelKept(Rule):
    """The time to get to and from what a rule keeps from work ("Never skip lunch or dinner"), kept from it too, in
    that rule's stage: a lunch you can't get to is a lunch skipped. The build adds one beside each such rule."""

    default_stage = "deadlines"
    applies_to = {"elastic"}

    class Params(Rule.Params):
        price: float = 10000.0  # a quarter hour of work in it costs what a kept meal a quarter hour short does

    def measures(self, ctx):
        yield from travel_measures(self, ctx, self.scoped_items(), self.p.price)


def travel_measures(rule: Rule, ctx: Any, scoped: list[Any], slope: float) -> Iterator[Measure]:
    """An item's own travel (lunch: 15 minutes to get there and back) kept clear of other work on both sides, and of
    events before it; `slope` per unit of them inside it."""
    grid, problem = ctx.grid, ctx.problem
    for side in ("before", "after"):
        groups: dict[int, list[Any]] = {}
        for item in scoped:
            if (b := getattr(item, f"travel_{side}")) > 0:
                groups.setdefault(b, []).append(item)
        for b, members in sorted(groups.items()):
            keys = {m.key for m in members}
            others = [i for i in problem.items.values() if i.key not in keys]
            for s in range(grid.S):
                window = before(grid, s, b)
                if not window:
                    continue
                if side == "before":
                    # A chunk starting at s, with other work or an event in the b units before it.
                    starts = lin_sum(ctx.start(m.key, s) for m in members)
                    if starts.is_const():
                        continue
                    events = sum(int(grid.units[w]) for w in window if problem.events[w])
                    expr, limit = starts * b + ctx.busy_units(window, others) + events, b
                else:
                    # Other work at s, with one of these in the b units before it: b × (work at s) + its units
                    # there, above b × (the slot's units) only when both.
                    mine = ctx.busy_units(window, members)
                    here = ctx.busy_units([s], others)
                    if mine.is_const() or here.is_const():
                        continue
                    expr, limit = here * b + mine, b * int(grid.units[s])
                yield Measure(f"{rule.name}:t{side[0]}{b}@{s}", expr, "units", (Hinge("above", limit, slope),))


def before(grid: Any, s: int, units: int) -> list[int]:
    """The slots just before s, back to `units` units, without a gap (a planning day's start isn't one)."""
    out, got, k = [], 0, s - 1
    while k >= 0 and got < units and grid.end[k] == grid.start[k + 1]:
        out.append(k)
        got += int(grid.units[k])
        k -= 1
    return out
