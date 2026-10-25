"""Price and forbid rules (DESIGN §12.2): a cost per hour of an item in a slot, or a ban."""

import math
from datetime import timedelta
from typing import Any, Literal

from friday.core.textnorm import identity_text, norm
from friday.core.time import MINUTES_PER_DAY, UNIT_MIN, local_midnight, planning_date, to_local
from friday.engine.pwl import Hinge, Measure
from friday.engine.rules import (
    FORBID,
    Clock,
    EventScope,
    Rule,
    in_hour_window,
    matching_weekdays,
    rule_type,
)


def lateness_price(rule: Rule, item: Any, s: int, extra_hours: float) -> float:
    grid = rule.problem.grid
    if item.due_utc is None:
        return 0.0
    if s == grid.S:
        if item.due_utc <= grid.horizon_end:
            return item.importance * (max(0.0, (grid.horizon_end - item.due_utc) / 60) + extra_hours)
        return 0.0
    return item.importance * max(0.0, (int(grid.end[s]) - item.due_utc) / 60)


@rule_type("late_work")
class LateWork(Rule):
    default_stage = "deadlines"
    applies_to = {"fixed"}

    class Params(Rule.Params):
        overflow_extra_hours: float = 48

    def applies_also(self, item):
        return item.firmness == "hard"

    def price(self, item, s):
        return lateness_price(self, item, s, self.p.overflow_extra_hours)


@rule_type("late_tasks")
class LateTasks(Rule):
    """personal's lateness (COMBINED.md 49, its decisions 38–39), on top of late_work: a fixed cost for each hard task
    that is late at all, since people count late tasks and late_work alone prefers many tasks a little late to one;
    and a price that grows with the square of the hours late, so one task very late costs more than several a little.
    `hours`: what a late task costs, in hours late of one unit of its work; `square_hours`: h² / square_hours per unit
    (0 switches it off). Work left unplaced counts as late, so leaving it off the plan never dodges the count."""

    default_stage = "deadlines"
    applies_to = {"fixed"}

    class Params(Rule.Params):
        hours: float = 48
        square_hours: float = 96

    def applies_also(self, item):
        return item.firmness == "hard" and item.due_utc is not None

    def price(self, item, s):
        if not self.p.square_hours or item.due_utc is None:
            return 0.0
        grid = self.problem.grid
        if s == grid.S and item.due_utc > grid.horizon_end:
            return 0.0  # due after the horizon: unplaced isn't late yet
        end = grid.horizon_end + 48 * 60 if s == grid.S else int(grid.end[s])  # unplaced: the horizon and two days
        hours = max(0.0, (end - item.due_utc) / 60)
        return item.importance * hours * hours / self.p.square_hours

    def measures(self, ctx):
        grid = ctx.grid
        for item in self.scoped_items():
            if item.due_utc > grid.horizon_end:
                continue
            late = [(item.key, s) for s in item.allowed if int(grid.end[s]) > item.due_utc]
            expr = ctx.any_of(f"lt:{self.name}:{item.key}", late)
            if not expr.is_const():
                yield Measure(f"{item.key}", expr, "count", (Hinge("above", 0, item.importance * self.p.hours),))
            yield Measure(f"{item.key}:over", ctx.over(item.key), "units",
                          (Hinge("above", 0, 4 * item.importance * self.p.hours),))  # fmt: skip


@rule_type("soft_late")
class SoftLate(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        overflow_extra_hours: float = 48

    def applies_also(self, item):
        return item.firmness == "soft"

    def price(self, item, s):
        return lateness_price(self, item, s, self.p.overflow_extra_hours)


@rule_type("late_night")
class LateNight(Rule):
    default_stage = "wellbeing"

    class Params(Rule.Params):
        gradient_start: Clock = 22 * 60
        a: float = 2
        b: float = 20
        debt_factor: float = 0.5
        # The first hour after waking costs what 23:00 does: free time isn't a reason to start homework at 07:00.
        morning: float = 2
        morning_min: int = 60

    def prepare(self, problem):
        super().prepare(problem)
        tz = problem.grid.spec.timezone
        # Local clock hours since the planning date's midnight, so a DST night is priced by the clock.
        self.slot_end_hours = [
            (to_local(slot.end_utc, tz) - local_midnight(slot.date)).total_seconds() / 3600
            for slot in problem.grid.slots
        ]
        self.bed_hours = {
            day: (to_local(night.bedtime_utc, tz) - local_midnight(day)).total_seconds() / 3600
            for day, night in problem.nights.items()
        }
        self.wake_on = {day + timedelta(days=1): night.wake_utc for day, night in problem.nights.items()}
        # Tracked sleep's learned routine (0 once you're ready to work) in place of the hour after waking.
        self.routine_on = {day + timedelta(days=1): night.routine_min for day, night in problem.nights.items()}

    def day_mult(self, day):
        return self.problem.scales[day].late_night_weight

    def price(self, item, s):
        grid = self.problem.grid
        if s == grid.S:
            return 0.0
        slot = grid.slots[s]
        tau, bed = self.slot_end_hours[s], self.bed_hours[slot.date]
        debt = self.problem.nights[slot.date].debt_hours
        multiplier = 1 + self.p.debt_factor * self.problem.scales[slot.day].debt_factor * debt
        gradient = self.p.gradient_start / 60
        wake = self.wake_on.get(slot.date)
        routine = self.routine_on.get(slot.date)
        morning = self.p.morning_min if routine is None else routine
        waking = self.p.morning if wake is not None and slot.start_utc < wake + morning else 0.0
        return self.p.a * max(0.0, min(tau, bed) - gradient) + self.p.b * multiplier * max(0.0, tau - bed) + waking


@rule_type("time_preference")
class TimePreference(Rule):
    class Params(Rule.Params):
        days: Any = None
        days_except: Any = None
        start: Clock | None = None
        end: Clock | None = None
        price: float | Literal["forbid"] = 1.0

    def prepare(self, problem):
        super().prepare(problem)
        self.weekdays = matching_weekdays(self.p.days, self.p.days_except)

    def matches(self, s: int) -> bool:
        slot = self.problem.grid.slots[s]
        return slot.weekday in self.weekdays and in_hour_window(slot.local_minute, self.p.start, self.p.end)

    def price(self, item, s):
        if s == self.problem.grid.S or self.p.price == FORBID:
            return 0.0
        return float(self.p.price) if self.matches(s) else 0.0

    def forbids(self, item, s):
        return self.p.price == FORBID and self.matches(s)

    def day_price(self, day):
        if self.p.start is not None or self.p.end is not None or day.weekday() not in self.weekdays:
            return 0.0
        return math.inf if self.p.price == FORBID else float(self.p.price)


def titled(problem: Any, titles: list[str]) -> Any:
    """The events whose title has one of these in it ("gym" finds "Gym" and "Gym with Sam"), as `scope` reads titles."""
    wanted = [identity_text(norm(t, problem.text)) for t in titles if t.strip()]
    return [f for f in problem.fixed if f.kind != "shove" and any(w and w in f.norm_title for w in wanted)]


@rule_type("skippable")
class Skippable(Rule):
    """`Gym and climbing club are optional`: their time isn't walled off (build leaves it free), but work there costs
    in the wellbeing stage, so Friday plans around them as around any event and uses their time only when work would
    otherwise be late; the plan then says which one gives way. `Climbing club only if I'm ahead` is the other way
    round (`ahead`, priced in the preferences stage): work takes that time before a late night or a broken rule, so
    it stays free only in weeks the work fits without it, and the plan says go."""

    default_stage = "wellbeing"

    class Params(Rule.Params):
        titles: list[str] = []
        price: float = 4.0
        ahead: bool = False  # you go only when you're ahead: said in the plan as "go" when its time is left free

    def prepare(self, problem):
        super().prepare(problem)
        self.covered = problem.slots_covered((f.blocked_lo, f.blocked_hi) for f in titled(problem, self.p.titles))

    def price(self, item, s):
        return float(self.p.price) if s < self.problem.grid.S and self.covered[s] else 0.0


@rule_type("before_event")
class BeforeEvent(Rule):
    """`No work after 10pm the night before climbing club`: on each planning day before one of its events, work from
    `after` until the day ends costs (or, Always, is ruled out). The event's planning day is the one it starts in, so a
    6am club on Wednesday makes Tuesday night early."""

    class Params(Rule.Params):
        titles: list[str] = []
        after: Clock = 22 * 60
        price: float | Literal["forbid"] = 2.0

    def prepare(self, problem):
        super().prepare(problem)
        spec = problem.grid.spec
        days = {planning_date(f.start_utc, spec.timezone, spec.day_start) for f in titled(problem, self.p.titles)}
        self.nights = {d - timedelta(days=1) for d in days}

    def matches(self, s: int) -> bool:
        slot = self.problem.grid.slots[s]
        return slot.date in self.nights and slot.day_minute + slot.units * UNIT_MIN > self.p.after

    def price(self, item, s):
        if s == self.problem.grid.S or self.p.price == FORBID:
            return 0.0
        return float(self.p.price) if self.matches(s) else 0.0

    def forbids(self, item, s):
        return self.p.price == FORBID and self.matches(s)


@rule_type("energy")
class Energy(Rule):
    default_scope = {"energy": "deep"}

    def price(self, item, s):
        grid = self.problem.grid
        if s == grid.S:
            return 0.0
        slot = grid.slots[s]
        return float(self.problem.energy_map[slot.weekday][slot.local_minute // 30])


@rule_type("finish_early")
class FinishEarly(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        days: float = 2.0

    def applies_also(self, item):
        return item.due_utc is not None

    def price(self, item, s):
        grid = self.problem.grid
        end = grid.horizon_end if s == grid.S else int(grid.end[s])
        lead = self.p.days
        return min(lead, max(0.0, (end - (item.due_utc - lead * MINUTES_PER_DAY)) / MINUTES_PER_DAY))


@rule_type("unscheduled")
class Unscheduled(Rule):
    applies_to = {"fixed"}

    class Params(Rule.Params):
        base: float = 1.0

    def applies_also(self, item):
        # Work due after the horizon is paced by the allocator's quotas; pulling all of it in now would front-load it.
        if item.due_utc is None:
            return True
        due_inside = item.due_utc <= self.problem.grid.horizon_end
        return due_inside and item.firmness != "hard"

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
        scope = EventScope(**self.p.events) if isinstance(self.p.events, dict) else self.p.events
        spec = problem.grid.spec
        self.ends: dict[Any, list[int]] = {}
        for event in problem.fixed:
            if scope is None or scope.matches(event, problem):
                day = planning_date(event.start_utc, spec.timezone, spec.day_start)
                self.ends.setdefault(day, []).append(event.blocked_hi)
        for ends in self.ends.values():
            ends.sort()

    def price(self, item, s):
        grid = self.problem.grid
        if s == grid.S:
            return 0.0
        slot = grid.slots[s]
        ends = self.ends.get(slot.date)
        if not ends:
            return self.p.cap if self.p.on_days_without == "cap" else 0.0
        if self.p.measure_from == "last":
            reference = ends[-1]
        else:
            earlier = [e for e in ends if e <= slot.start_utc]
            if not earlier:
                return self.p.cap
            reference = earlier[-1]
        if slot.start_utc < reference:
            return self.p.cap
        return min(self.p.cap, self.p.slope * (slot.start_utc - reference) / 60)
