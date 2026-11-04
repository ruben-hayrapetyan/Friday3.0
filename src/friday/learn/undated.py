"""When you do work that has no due date, read from your recorded sittings (3 Nov: "the undated time slots thing should
be completely learned/dictated by rules"). Pure: sittings in local time in, the hours that hold nearly all of it out,
or nothing while there's too little to tell or it's spread over the day. commands/undated.py asks before it's a rule.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

MIN_HOURS = 6.0  # recorded undated work, at least
MIN_DAYS = 4  # on this many different days
SHARE = 0.9  # the hours hold this share of it
DAY_START = 4  # the planning day starts at 4am: work at 1am belongs to the evening before
MAX_SPAN = 16  # a window wider than this says nothing (a waking day)


@dataclass(frozen=True)
class Habit:
    start: int  # hour of the day, 0–23
    end: int  # hour of the day, 0–23; before `start` when it runs past midnight
    hours: float  # undated work recorded
    share: float  # of it inside the window
    days: int  # different days it was done on


def habit(sittings: Sequence[tuple[datetime, datetime]]) -> Habit | None:
    """The fewest whole hours, counted from 4am, holding `SHARE` of the recorded undated work; the earliest such."""
    minutes = [0.0] * 24  # by hour since 4am
    days: set[object] = set()
    for start, end in sittings:
        at = start
        while at < end:
            nxt = min(end, at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            minutes[(at.hour - DAY_START) % 24] += (nxt - at).total_seconds() / 60
            days.add((at - timedelta(hours=DAY_START)).date())
            at = nxt
    total = sum(minutes)
    if total / 60 < MIN_HOURS or len(days) < MIN_DAYS:
        return None
    for span in range(1, MAX_SPAN + 1):
        best = max(range(24 - span + 1), key=lambda lo: (sum(minutes[lo : lo + span]), -lo))
        inside = sum(minutes[best : best + span])
        if inside >= SHARE * total:
            return Habit((best + DAY_START) % 24, (best + span + DAY_START) % 24, total / 60, inside / total, len(days))
    return None


def clock_said(hour: int) -> str:
    """2pm, 12am, 10am."""
    return f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"


def sentence(h: Habit) -> str:
    """The rule a yes adds, in the words the Rules page reads."""
    return f"undated work only between {clock_said(h.start)} and {clock_said(h.end)}"
