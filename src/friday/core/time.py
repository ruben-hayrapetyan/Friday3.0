"""Time: UTC minutes, planning days and weeks, and the scheduler grid.

Inside Friday a moment is an int: minutes since the Unix epoch, in UTC. Storage uses ISO strings ending in Z,
and the API speaks local `YYYY-MM-DDTHH:MM`; both convert here.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import numpy as np

UNIT_MIN = 15
MINUTES_PER_DAY = 1440
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
EPOCH = datetime(1970, 1, 1)


@cache
def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def parse_utc(text: str) -> int:
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"{text!r} has no timezone; stored times end in Z")
    return _naive(moment.astimezone(UTC).replace(tzinfo=None))


def format_utc(minutes: int) -> str:
    return (EPOCH + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%MZ")


def _naive(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(minutes=1)


def to_utc(local: datetime, tz: str) -> int:
    # fold=0 picks the first of two ambiguous times. For a time inside a gap it uses the offset from before
    # the change, which lands after the gap: 02:30 on a spring-forward night becomes 03:30.
    aware = local.replace(tzinfo=zone(tz), fold=0)
    return _naive(aware.astimezone(UTC).replace(tzinfo=None))


def to_local(minutes: int, tz: str) -> datetime:
    utc = (EPOCH + timedelta(minutes=minutes)).replace(tzinfo=UTC)
    return utc.astimezone(zone(tz)).replace(tzinfo=None)


def parse_local(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M")


def format_local(local: datetime) -> str:
    return local.strftime("%Y-%m-%dT%H:%M")


def ampm(time: str | datetime) -> str:
    """A time the way you read it, on a 12-hour clock: "14:30" is "2:30pm", "14:00" is "2pm", "00:00" is "12am".
    Takes "HH:MM", a local "YYYY-MM-DDTHH:MM" or a datetime; only words for you use it, never stored times."""
    hour, minute = (time.hour, time.minute) if isinstance(time, datetime) else map(int, time[-5:].split(":"))
    return f"{(hour - 1) % 12 + 1}{f':{minute:02d}' if minute else ''}{'am' if hour % 24 < 12 else 'pm'}"


TIMES = re.compile(r"(?<![\dT:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:]|\s?[ap]m)")  # "8:30pm" is already on 12 hours


def ampm_in(text: str) -> str:
    """A sentence with its 24-hour times ("No work after 22:00") on a 12-hour clock ("No work after 10pm")."""
    return TIMES.sub(lambda m: ampm(f"{int(m[1]):02d}:{m[2]}"), text)


def utc_offset(minutes: int, tz: str) -> timedelta:
    utc = (EPOCH + timedelta(minutes=minutes)).replace(tzinfo=UTC)
    return utc.astimezone(zone(tz)).utcoffset() or timedelta(0)


def local_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)


def planning_date(minutes: int, tz: str, day_start: int) -> date:
    return (to_local(minutes, tz) - timedelta(minutes=day_start)).date()


def planning_day_start_utc(day: date, tz: str, day_start: int) -> int:
    return to_utc(local_midnight(day) + timedelta(minutes=day_start), tz)


def night_utc(day: date, bedtime: int, tz: str) -> int:
    """Bedtime of the night that begins on planning date `day`; `bedtime` may pass 1440 (after midnight)."""
    return to_utc(local_midnight(day) + timedelta(minutes=bedtime), tz)


def wake_utc(day: date, wake: int, tz: str) -> int:
    """Wake time on the morning after the night that begins on planning date `day`."""
    return to_utc(local_midnight(day + timedelta(days=1)) + timedelta(minutes=wake), tz)


def week_of(day: date, week_start: int) -> int:
    # date.toordinal() is 1 on Monday 0001-01-01.
    return (day.toordinal() - 1 - week_start) // 7


@dataclass(frozen=True)
class GridSpec:
    timezone: str
    day_start: int = 4 * 60
    week_start: int = 0
    horizon_days: int = 14
    fine_days: int = 7
    fine_slot_units: int = 1
    coarse_slot_units: int = 2


@dataclass(frozen=True)
class Slot:
    index: int
    start_utc: int
    end_utc: int
    units: int
    day: int  # planning day counted from now
    date: date  # the calendar date the planning day begins on
    weekday: int  # 0 is Monday
    local_minute: int  # minutes since local midnight of the slot's own calendar day
    day_minute: int  # minutes since local midnight of `date`, so 01:00 the next morning is 1500
    week: int


class Grid:
    """Contiguous slots covering planning days 0 … H−1. Index `S` is the overflow slot."""

    def __init__(self, slots: list[Slot], now_utc: int, horizon_end: int, spec: GridSpec):
        self.slots = tuple(slots)
        self.S = len(slots)
        self.now = now_utc
        self.horizon_end = horizon_end
        self.spec = spec
        self.start = np.array([s.start_utc for s in slots] + [horizon_end], dtype=np.int64)
        self.end = np.array([s.end_utc for s in slots] + [horizon_end], dtype=np.int64)
        self.units = np.array([s.units for s in slots] + [0], dtype=np.int64)
        self.day = np.array([s.day for s in slots] + [-1], dtype=np.int64)
        self.n_days = slots[-1].day + 1 if slots else 0
        self.day_slots: list[list[int]] = [[] for _ in range(self.n_days)]
        self.week_slots: dict[int, list[int]] = {}
        for s in slots:
            self.day_slots[s.day].append(s.index)
            self.week_slots.setdefault(s.week, []).append(s.index)
        self.day_date = [self.slots[ix[0]].date if ix else None for ix in self.day_slots]

    def hours(self, s: int) -> float:
        return int(self.units[s]) * UNIT_MIN / 60

    def slot_at(self, minutes: int) -> int:
        """Index of the slot containing `minutes`, or −1 outside the grid."""
        if not self.slots or minutes < self.slots[0].start_utc or minutes >= self.horizon_end:
            return -1
        return int(np.searchsorted(self.start[: self.S], minutes, side="right")) - 1

    def slots_in(self, lo: int, hi: int) -> list[int]:
        """Slots lying entirely inside [lo, hi)."""
        return [s.index for s in self.slots if s.start_utc >= lo and s.end_utc <= hi]

    def slots_overlapping(self, lo: int, hi: int) -> list[int]:
        return [s.index for s in self.slots if s.start_utc < hi and s.end_utc > lo]

    def contiguous(self, a: int, b: int) -> bool:
        return self.end[a] == self.start[b]


def make_grid(now_utc: int, spec: GridSpec, end_utc: int | None = None) -> Grid:
    """Grid from `now_utc` rounded up to a unit; `end_utc` truncates it (tests, brute force)."""
    first_start = -(-now_utc // UNIT_MIN) * UNIT_MIN
    first_date = planning_date(first_start, spec.timezone, spec.day_start)
    stop = end_utc if end_utc is not None else np.iinfo(np.int64).max
    slots: list[Slot] = []
    for day in range(spec.horizon_days):
        day_date = first_date + timedelta(days=day)
        lo = max(first_start, planning_day_start_utc(day_date, spec.timezone, spec.day_start))
        hi = planning_day_start_utc(day_date + timedelta(days=1), spec.timezone, spec.day_start)
        step_units = spec.fine_slot_units if day < spec.fine_days else spec.coarse_slot_units
        t = lo
        while t < min(hi, stop):
            e = min(t + step_units * UNIT_MIN, hi, stop)
            slots.append(_make_slot(len(slots), t, e, day, day_date, spec))
            t = e
    if not slots:
        raise ValueError("the grid has no slots")
    return Grid(slots, first_start, slots[-1].end_utc, spec)


def _make_slot(index: int, start: int, end: int, day: int, day_date: date, spec: GridSpec) -> Slot:
    if utc_offset(start, spec.timezone) % timedelta(minutes=UNIT_MIN):
        raise ValueError(f"timezone: {spec.timezone} has an offset that isn't a multiple of 15 minutes")
    local = to_local(start, spec.timezone)
    local_minute = local.hour * 60 + local.minute
    return Slot(
        index=index,
        start_utc=start,
        end_utc=end,
        units=(end - start) // UNIT_MIN,
        day=day,
        date=day_date,
        weekday=day_date.weekday(),
        local_minute=local_minute,
        day_minute=local_minute + MINUTES_PER_DAY * (local.date() - day_date).days,
        week=week_of(day_date, spec.week_start),
    )
