"""Price and forbid rules (DESIGN §12.2): a cost per hour of an item in a slot, or a ban."""

import math
from datetime import timedelta
from typing import Any, Literal

from friday.core.time import MINUTES_PER_DAY, local_midnight, planning_date, to_local
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
        waking = self.p.morning if wake is not None and slot.start_utc < wake + self.p.morning_min else 0.0
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
