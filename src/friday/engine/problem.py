"""The frozen engine input (DESIGN §11.1) and `Solution`, which recomputes every model variable from a plan."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from friday.core.pace import DayScales
from friday.core.textnorm import TextRules, identity_text, norm
from friday.core.time import Grid

if TYPE_CHECKING:
    from friday.engine.rules import Rule

STAGES = ("deadlines", "wellbeing", "preferences")
Amount = Literal["fixed", "elastic", "target", "open"]
Plan = Mapping[str, tuple[int, ...]]  # item key → sorted slot indices
NEVER_LEARNED = frozenset({"late_work", "late_tasks", "quota"})


@dataclass(frozen=True)
class DepSpec:
    """This item may start once `fraction` of `key` is done, after `lag_min`."""

    key: str
    fraction: float = 1.0
    lag_min: int = 0
    total: int = 0  # the other item's full amount, in units
    progress: int = 0  # its recorded progress, in units

    @property
    def required(self) -> int:
        """Units of the other item still to be placed before this one may start (0 = already satisfied)."""
        return max(0, math.ceil(self.fraction * self.total - 1e-9) - self.progress)


@dataclass
class EngineItem:
    key: str
    title: str = ""
    norm_title: str = ""  # identity text (DESIGN §6.6), what title scopes compare
    area: str | None = None
    tags: tuple[str, ...] = ()
    preset: str | None = None
    energy: str | None = None
    importance: float = 3  # times its kind's place in `kind_order`
    firmness: Literal["hard", "soft", "none"] = "none"
    amount: Amount = "fixed"
    daily_ceiling: int = 12  # open: units per day; today's progress is `progress_today`
    progress_today: int = 0
    need: int = 0  # fixed: remaining units
    min: int = 0  # elastic, minus progress
    ideal: int = 0
    max: int = 0
    target: int = 0  # target: units in the window including neglect carry
    cap: int = 0
    progress: int = 0
    progress_by_week: dict[int, int] = field(default_factory=dict)
    release_utc: int | None = None  # None = now
    due_utc: int | None = None
    window_is_hard: bool = False
    shape: Literal["one_sitting", "split"] = "split"
    min_chunk: int = 1
    max_chunk: int | None = None
    chunk_cost: float = 0.0
    spread: Literal["none", "spread", "cluster"] = "none"
    size_hours: float = 0.0
    tentative: bool = False
    allowed: tuple[int, ...] = ()
    locked: frozenset[int] = frozenset()
    preferred: frozenset[int] = frozenset()
    current: frozenset[int] = frozenset()
    held: frozenset[int] = frozenset()  # the timer's hold: kept like a preferred pin, without being one
    depends_on: tuple[DepSpec, ...] = ()
    quotas: dict[int, int] = field(default_factory=dict)  # week → units, from the allocator
    pacing: Literal["linear", "front", "back", "none"] = "none"
    pacing_start_utc: int | None = None  # where the pacing line starts: the release, else creation, else now
    travel_before: int = 0  # units kept clear of other work before each chunk: getting to lunch
    travel_after: int = 0  # and after it: getting back to somewhere you can work

    def __post_init__(self) -> None:
        self.allowed_set: frozenset[int] = frozenset(self.allowed)
        if not self.norm_title:
            self.norm_title = identity_text(norm(self.title, TextRules()))

    def set_allowed(self, allowed: list[int]) -> None:
        self.allowed = tuple(sorted(set(allowed) | set(self.locked)))
        self.allowed_set = frozenset(self.allowed)

    @property
    def total_units(self) -> int:
        """The full amount, which dependencies on this item are sized by."""
        return {
            "fixed": self.need + self.progress,
            "elastic": self.ideal + self.progress,
            "target": self.target,
            "open": 0,
        }[self.amount]


@dataclass(frozen=True)
class FixedOcc:
    title: str
    kind: str  # class | meeting | shove | other
    start_utc: int
    end_utc: int
    tags: tuple[str, ...] = ()
    buffer_before: int = 0
    buffer_after: int = 0
    blocks_time: bool = True
    norm_title: str = ""
    skippable: bool = False  # optional (`skippable` rule): its time is priced, not walled off

    @property
    def blocked_lo(self) -> int:
        return self.start_utc - self.buffer_before

    @property
    def blocked_hi(self) -> int:
        return self.end_utc + self.buffer_after


@dataclass(frozen=True)
class Night:
    """The night that begins on one planning date."""

    bedtime_utc: int
    wake_utc: int
    margin_min: int = 60
    debt_hours: float = 0.0  # sleep debt D_n from the previous nights (DESIGN §12.3)
    routine_min: int | None = None  # the next morning's routine, learned from tracked sleep; None: late_night's own

    @property
    def core(self) -> tuple[int, int]:
        return self.bedtime_utc + self.margin_min, self.wake_utc


@dataclass
class Problem:
    grid: Grid
    items: dict[str, EngineItem]
    fixed: list[FixedOcc]
    nights: dict[date, Night]
    day_caps: list[int]
    rules: list["Rule"]
    scales: list[DayScales]
    energy_map: tuple[tuple[float, ...], ...]  # 7 weekdays × 48 half-hour cells, points per hour
    multipliers: dict[str, float] = field(default_factory=dict)  # learned θ per rule name (section 21)
    scale: int = 100
    minimize_changes_scale: float = 1.0
    text: TextRules = field(default_factory=TextRules)
    # Locks put where an event holds the time: (item key, the event's title, the lock's start, UTC minutes). They can't
    # be kept there, so they plan as preferred pins, and the plan says so.
    locks_over_events: list[tuple[str, str, int]] = field(default_factory=list)
    blocked: np.ndarray = field(default=None)  # type: ignore[assignment]
    core: np.ndarray = field(default=None)  # type: ignore[assignment]
    events: np.ndarray = field(default=None)  # type: ignore[assignment]  # busy events themselves, not their gaps
    lock_owner: dict[int, str] = field(default_factory=dict)
    price_cache: dict[tuple[str, str], np.ndarray] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.blocked is None:
            self.blocked = self.slots_covered((f.blocked_lo, f.blocked_hi) for f in self.fixed if f.blocks_time)
        if self.core is None:
            self.core = self.slots_covered(n.core for n in self.nights.values())
        if self.events is None:
            self.events = self.slots_covered(
                (f.start_utc, f.end_utc) for f in self.fixed if f.blocks_time and f.kind != "shove"
            )
        self.refresh_locks()

    def slots_covered(self, ranges: Any) -> np.ndarray:
        covered = np.zeros(self.grid.S, dtype=bool)
        for lo, hi in ranges:
            for s in self.grid.slots_overlapping(lo, hi):
                covered[s] = True
        return covered

    def refresh_locks(self) -> None:
        self.lock_owner = {s: it.key for it in self.items.values() for s in it.locked}

    def scale_of(self, s: int) -> DayScales:
        return self.scales[self.grid.slots[s].day]

    def multiplier(self, rule_name: str, rule_type: str) -> float:
        return 1.0 if rule_type in NEVER_LEARNED else self.multipliers.get(rule_name, 1.0)


class Solution:
    """A plan plus the arithmetic that recomputes every model variable from its slots alone (DESIGN §11.12)."""

    def __init__(self, problem: Problem, plan: Plan, any_groups: dict[str, tuple[tuple[str, int], ...]] | None = None):
        self.problem = problem
        self.slots = {k: tuple(sorted(plan.get(k, ()))) for k in problem.items}
        self.sets = {k: frozenset(v) for k, v in self.slots.items()}
        self.any_groups = any_groups if any_groups is not None else {}
        self.prefixes: dict[str, np.ndarray] = {}

    def placed(self, key: str) -> int:
        units = self.problem.grid.units
        return int(sum(units[s] for s in self.slots[key]))

    def over(self, key: str) -> int:
        item = self.problem.items[key]
        return max(0, item.need - self.placed(key)) if item.amount == "fixed" else 0

    def prefix(self, key: str) -> np.ndarray:
        """prefix[t] = units of `key` placed strictly before slot t."""
        if key not in self.prefixes:
            grid = self.problem.grid
            per_slot = np.zeros(grid.S + 1, dtype=np.int64)
            for s in self.slots[key]:
                per_slot[s + 1] = grid.units[s]
            self.prefixes[key] = np.cumsum(per_slot)
        return self.prefixes[key]

    def value(self, var: Any) -> int:
        kind = var[0]
        if kind == "x":
            return int(var[2] in self.sets[var[1]])
        if kind == "over":
            return self.over(var[1])
        if kind == "start":
            _, key, s = var
            return int(s in self.sets[key] and (s - 1) not in self.sets[key])
        if kind == "cum":
            return int(self.prefix(var[1])[var[2]])
        if kind == "any":
            return int(any(s in self.sets[k] for k, s in self.any_groups[var[1]]))
        raise KeyError(var)
