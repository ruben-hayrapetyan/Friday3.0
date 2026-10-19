"""The scheduler grid (ENGINE_REFERENCE section 3).

Time is integer minutes from an epoch that is a Monday 00:00, wall-clock only.
Simplification (logged in RESEARCH_LOG.md): no daylight-saving changes, so a planning day is
always 24 h and a fine day always has 96 slots. Everything else follows the reference.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .settings import MINUTES_PER_DAY, UNIT_MIN, Settings


@dataclass(frozen=True)
class Slot:
    index: int
    start: int
    end: int
    units: int
    day: int  # planning-day index from now
    date: int  # calendar date on which the planning day begins
    weekday: int  # 0 = Monday
    day_minute: int  # minutes since midnight of `date`; 240..1679, so 01:00 work is 1500
    local_minute: int  # minutes since midnight of the slot's own calendar day
    week: int


class Grid:
    """Contiguous slots covering planning days 0..H-1. Index `S` is the overflow slot."""

    def __init__(self, slots: list[Slot], now: int, horizon_end: int, settings: Settings):
        self.slots = tuple(slots)
        self.S = len(slots)
        self.now = now
        self.horizon_end = horizon_end
        self.settings = settings
        self.start = np.array([s.start for s in slots] + [horizon_end], dtype=np.int64)
        self.end = np.array([s.end for s in slots] + [horizon_end], dtype=np.int64)
        self.units = np.array([s.units for s in slots] + [0], dtype=np.int64)
        self.day = np.array([s.day for s in slots] + [-1], dtype=np.int64)
        self.n_days = (slots[-1].day + 1) if slots else 0
        self.day_slots: list[list[int]] = [[] for _ in range(self.n_days)]
        self.week_slots: dict[int, list[int]] = {}
        for s in slots:
            self.day_slots[s.day].append(s.index)
            self.week_slots.setdefault(s.week, []).append(s.index)
        self.day_date = [self.slots[ix[0]].date if ix else None for ix in self.day_slots]

    def hours(self, s: int) -> float:
        return self.units[s] * 0.25

    def slot_at(self, t: int) -> int:
        """Index of the slot containing minute t, or -1 when t is outside the grid."""
        if t < self.slots[0].start or t >= self.horizon_end:
            return -1
        i = int(np.searchsorted(self.start[: self.S], t, side="right")) - 1
        return i

    def slots_in(self, lo: int, hi: int) -> list[int]:
        """Slots lying entirely inside [lo, hi)."""
        return [s.index for s in self.slots if s.start >= lo and s.end <= hi]

    def slots_overlapping(self, lo: int, hi: int) -> list[int]:
        return [s.index for s in self.slots if s.start < hi and s.end > lo]

    def contiguous(self, a: int, b: int) -> bool:
        return self.end[a] == self.start[b]


def planning_day_of(t: int, day_start: int) -> int:
    """Absolute planning-day number (= the calendar date it begins on) containing minute t."""
    return (t - day_start) // MINUTES_PER_DAY


def week_of(date: int, week_start: int) -> int:
    return (date - week_start) // 7


def make_grid(now: int, settings: Settings, end: int | None = None) -> Grid:
    """Grid starting at `now` rounded up to a unit boundary. `end` truncates it (tests, brute force)."""
    t0 = -(-now // UNIT_MIN) * UNIT_MIN
    p0 = planning_day_of(t0, settings.day_start)
    slots: list[Slot] = []
    for d in range(settings.horizon_days):
        date = p0 + d
        lo = max(t0, date * MINUTES_PER_DAY + settings.day_start)
        hi = (date + 1) * MINUTES_PER_DAY + settings.day_start
        step = UNIT_MIN if d < settings.fine_days else 2 * UNIT_MIN
        t = lo
        while t < hi:
            e = min(t + step, hi)
            if end is not None and t >= end:
                break
            if end is not None:
                e = min(e, end)
            slots.append(
                Slot(
                    index=len(slots),
                    start=t,
                    end=e,
                    units=(e - t) // UNIT_MIN,
                    day=d,
                    date=date,
                    weekday=date % 7,
                    day_minute=t - date * MINUTES_PER_DAY,
                    local_minute=t % MINUTES_PER_DAY,
                    week=week_of(date, settings.week_start),
                )
            )
            t = e
    horizon_end = slots[-1].end
    return Grid(slots, t0, horizon_end, settings)
