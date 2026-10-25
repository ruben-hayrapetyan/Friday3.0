"""Learning from your sleep (Settings → Schedule → Track my sleep): the nights your "Going to bed", "I'm up" and "Ready
to work" taps make, and what they say. Pure: no database.

- A night belongs to the evening's planning day: bed at 1am Tuesday is Monday's night. Its morning is the next
  calendar day's first "I'm up", and "Ready to work" that morning's first, else the first timer started after it.
- Your bedtime and wake time per weekday are the median of that weekday's nights once it has three, else of its group
  (school nights Sunday to Thursday, weekend nights Friday and Saturday; weekday and weekend mornings) once that has
  `min_nights`. Times are kept to the quarter hour. A weekday whose learned time is half an hour or more off the one
  set is offered as a change, never made without a yes.
- The morning routine is the median minutes from up to ready, by the same groups; the planner keeps it light.
- Sleep debt: the hours a night fell short of the sleep you plan for.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SCHOOL_NIGHTS = ("sun", "mon", "tue", "wed", "thu")  # evenings before a weekday morning
WEEKDAY_MORNINGS = ("mon", "tue", "wed", "thu", "fri")
OWN = 3  # a weekday's own nights that are enough without its group
OFF_BY = 30  # minutes a learned time must differ from the one set to be worth offering
QUARTER = 15


@dataclass(frozen=True)
class Mark:
    id: int
    kind: str  # bed, up or ready
    at: datetime  # local


@dataclass(frozen=True)
class Night:
    date: date  # the evening's planning day
    bed: Mark | None = None
    up: Mark | None = None  # the next morning
    ready: Mark | None = None  # that morning; None when neither tapped nor timed
    ready_from_timer: datetime | None = None

    @property
    def slept_min(self) -> int | None:
        if self.bed is None or self.up is None:
            return None
        minutes = int((self.up.at - self.bed.at).total_seconds() // 60)
        return minutes if 0 < minutes < 16 * 60 else None

    @property
    def ready_at(self) -> datetime | None:
        return self.ready.at if self.ready else self.ready_from_timer

    @property
    def routine_min(self) -> int | None:
        if self.up is None or self.ready_at is None:
            return None
        minutes = int((self.ready_at - self.up.at).total_seconds() // 60)
        return minutes if 0 <= minutes < 6 * 60 else None


def evening_of(at: datetime, day_start_min: int) -> date:
    """The planning day a bedtime belongs to: until the day starts (4am), it's still the night before."""
    return (at - timedelta(minutes=day_start_min)).date()


def nights_from(marks: Iterable[Mark], timer_starts: Iterable[datetime], day_start_min: int) -> dict[date, Night]:
    """Each night with anything recorded, by its evening: the last bed mark, then the next morning's first up and
    first ready (or first timer after waking)."""
    beds: dict[date, Mark] = {}
    ups: dict[date, Mark] = {}
    readies: dict[date, Mark] = {}
    for mark in sorted(marks, key=lambda m: m.at):
        if mark.kind == "bed":
            beds[evening_of(mark.at, day_start_min)] = mark  # the last one: back up and to bed again
        elif mark.kind == "up":
            ups.setdefault(mark.at.date(), mark)
        elif mark.kind == "ready":
            readies.setdefault(mark.at.date(), mark)
    starts = sorted(timer_starts)
    out = {}
    for evening in sorted(set(beds) | {d - timedelta(days=1) for d in ups} | {d - timedelta(days=1) for d in readies}):
        morning = evening + timedelta(days=1)
        up = ups.get(morning)
        timed = next((s for s in starts if up is not None and s.date() == morning and s >= up.at), None)
        out[evening] = Night(evening, beds.get(evening), up, readies.get(morning), timed)
    return out


def since_noon(at: datetime, evening: date) -> int:
    """A bedtime as minutes after the evening's noon, so 11pm and 1am average to midnight."""
    return int((at - datetime(evening.year, evening.month, evening.day, 12)).total_seconds() // 60)


def clock(minutes: int) -> str:
    minutes = round(minutes / QUARTER) * QUARTER % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def minutes_of(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def by_weekday(samples: Mapping[str, list[int]], groups: tuple[tuple[str, ...], ...], least: int) -> dict[str, int]:
    """Each weekday's median: its own once it has `OWN`, else its group's once that has `least`."""
    out = {}
    for day in WEEKDAYS:
        own = samples.get(day, [])
        group = next(g for g in groups if day in g)
        pooled = [v for d in group for v in samples.get(d, [])]
        if len(own) >= OWN:
            out[day] = round(median(own))
        elif len(pooled) >= least:
            out[day] = round(median(pooled))
    return out


@dataclass(frozen=True)
class Learned:
    bedtime: dict[str, str]  # weekday (of the evening) → HH:MM
    wake: dict[str, str]  # weekday (of the morning) → HH:MM
    routine_min: dict[str, int]  # weekday (of the morning) → minutes from up to ready
    nights: int  # nights with a bedtime and a wake time


def learn(nights: Iterable[Night], least: int) -> Learned:
    beds: dict[str, list[int]] = {}
    wakes: dict[str, list[int]] = {}
    routines: dict[str, list[int]] = {}
    complete = 0
    for night in nights:
        evening, morning = WEEKDAYS[night.date.weekday()], WEEKDAYS[(night.date.weekday() + 1) % 7]
        if night.bed:
            beds.setdefault(evening, []).append(since_noon(night.bed.at, night.date))
        if night.up:
            wakes.setdefault(morning, []).append(night.up.at.hour * 60 + night.up.at.minute)
        if night.routine_min is not None:
            routines.setdefault(morning, []).append(night.routine_min)
        complete += night.slept_min is not None
    weekend_nights = tuple(d for d in WEEKDAYS if d not in SCHOOL_NIGHTS)
    weekend_mornings = tuple(d for d in WEEKDAYS if d not in WEEKDAY_MORNINGS)
    bed = by_weekday(beds, (SCHOOL_NIGHTS, weekend_nights), least)
    wake = by_weekday(wakes, (WEEKDAY_MORNINGS, weekend_mornings), least)
    routine = by_weekday(routines, (WEEKDAY_MORNINGS, weekend_mornings), least)
    return Learned(
        bedtime={d: clock(12 * 60 + m) for d, m in bed.items()},
        wake={d: clock(m) for d, m in wake.items()},
        routine_min={d: max(QUARTER, round(m / QUARTER) * QUARTER) for d, m in routine.items()},
        nights=complete,
    )


@dataclass(frozen=True)
class Change:
    days: tuple[str, ...]
    field: str  # bedtime or wake
    now: str
    learned: str


def changes(learned: Learned, sleep: Mapping[str, Any]) -> list[Change]:
    """Weekdays whose learned bedtime or wake time is half an hour or more off the one set, grouped where alike."""
    found: dict[tuple[str, str, str], list[str]] = {}
    for field, times in (("bedtime", learned.bedtime), ("wake", learned.wake)):
        for day, at in times.items():
            now = sleep[day][field] if isinstance(sleep[day], Mapping) else getattr(sleep[day], field)
            gap = abs(((minutes_of(at) - minutes_of(now)) + 12 * 60) % (24 * 60) - 12 * 60)
            if gap >= OFF_BY:
                found.setdefault((field, now, at), []).append(day)
    return [Change(tuple(days), field, now, at) for (field, now, at), days in found.items()]


def shortfall_hours(night: Night, planned_min: int) -> float:
    """How far a night fell short of the sleep you plan for, in hours; 0 for a full night or one not recorded."""
    slept = night.slept_min
    return max(0.0, (planned_min - slept) / 60) if slept is not None else 0.0
