"""Problem data (ENGINE_REFERENCE 6A.1): the frozen input every engine solves and the evaluator scores."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np

from .grid import Grid
from .settings import Settings

if TYPE_CHECKING:
    from .rules import Rule

Amount = Literal["fixed", "elastic", "target", "open"]


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
        """N_A - P_A: units of the other item that must be placed first (0 = already satisfied)."""
        import math

        return max(0, math.ceil(self.fraction * self.total - 1e-9) - self.progress)


@dataclass
class EngineItem:
    key: str
    title: str = ""
    area: str | None = None
    tags: tuple[str, ...] = ()
    preset: str = "assignment"
    energy: str | None = None
    importance: int = 3
    firmness: Literal["hard", "soft", "none"] = "none"
    amount: Amount = "fixed"
    daily_ceiling: int = 12  # open: units per day (full; today's progress is `progress_today`)
    progress_today: int = 0
    need: int = 0  # fixed: remaining units
    min: int = 0  # elastic, minus progress
    ideal: int = 0
    max: int = 0
    target: int = 0  # target: units in the window incl. neglect carry
    cap: int = 0
    progress: int = 0
    progress_by_week: dict[int, int] = field(default_factory=dict)
    release: int | None = None  # absolute minutes; None = now
    due: int | None = None
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
    depends_on: tuple[DepSpec, ...] = ()
    quotas: dict[int, int] = field(default_factory=dict)  # week -> units, from the allocator

    def __post_init__(self) -> None:
        self.allowed_set: frozenset[int] = frozenset(self.allowed)

    def set_allowed(self, allowed: list[int]) -> None:
        self.allowed = tuple(sorted(set(allowed) | set(self.locked)))
        self.allowed_set = frozenset(self.allowed)

    @property
    def total_units(self) -> int:
        """Full amount used to size dependencies (what others wait on)."""
        return {"fixed": self.need + self.progress, "elastic": self.ideal + self.progress,
                "target": self.target, "open": 0}[self.amount]


@dataclass(frozen=True)
class FixedOcc:
    title: str
    kind: str  # class | meeting | shove | other
    start: int
    end: int
    tags: tuple[str, ...] = ()
    buf_before: int = 0
    buf_after: int = 0
    blocks_time: bool = True

    @property
    def blocked_lo(self) -> int:
        return self.start - self.buf_before

    @property
    def blocked_hi(self) -> int:
        return self.end + self.buf_after


@dataclass(frozen=True)
class Night:
    """The night that begins on planning-day date `date`."""

    bedtime: int  # absolute minutes
    wake: int
    margin: int = 60
    debt_hours: float = 0.0  # sleep debt D_n; the multiplier is 1 + debt_factor * rest * D_n

    @property
    def core(self) -> tuple[int, int]:
        return self.bedtime + self.margin, self.wake


@dataclass(frozen=True)
class DayScales:
    """The four dials for one planning day (section 10). 1.0 everywhere is Normal."""

    capacity: float = 1.0
    rest: float = 1.0
    spread: float = 1.0
    growth: float = 1.0


NORMAL = DayScales()
EASY = DayScales(0.6, 2.0, 3.0, 0.0)
PUSH = DayScales(1.2, 0.5, 1.0, 2.0)


@dataclass
class Problem:
    grid: Grid
    settings: Settings
    items: dict[str, EngineItem]
    fixed: list[FixedOcc]
    nights: dict[int, Night]
    day_caps: list[int]
    rules: list["Rule"]
    scales: list[DayScales]
    energy_map: dict[int, list[float]]
    blocked: np.ndarray = field(default=None)  # type: ignore[assignment]
    core: np.ndarray = field(default=None)  # type: ignore[assignment]
    lock_owner: dict[int, str] = field(default_factory=dict)
    _price_cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        g = self.grid
        if self.blocked is None:
            self.blocked = np.zeros(g.S, dtype=bool)
            for f in self.fixed:
                if f.blocks_time:
                    for s in g.slots_overlapping(f.blocked_lo, f.blocked_hi):
                        self.blocked[s] = True
        if self.core is None:
            self.core = np.zeros(g.S, dtype=bool)
            for n in self.nights.values():
                lo, hi = n.core
                for s in g.slots_overlapping(lo, hi):
                    self.core[s] = True
        self.lock_owner = {s: it.key for it in self.items.values() for s in it.locked}

    def scale_of(self, s: int) -> DayScales:
        return self.scales[self.grid.slots[s].day]

    @property
    def flexible(self) -> list[EngineItem]:
        return list(self.items.values())

    def night_of_date(self, date: int) -> Night:
        return self.nights[date]
