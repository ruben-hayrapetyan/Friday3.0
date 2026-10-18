"""Engine minutes <-> real local time. Engine date 0 is Monday 1970-01-05, so `date % 7` is the weekday (mon = 0)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

EPOCH = datetime(1970, 1, 5)


def to_minutes(t: datetime) -> int:
    """Local wall-clock time (naive, or aware and taken at face value) -> engine minutes."""
    t = t.replace(tzinfo=None)
    return int((t - EPOCH).total_seconds() // 60)


def from_minutes(m: int) -> datetime:
    return EPOCH + timedelta(minutes=int(m))


def date_index(d: date) -> int:
    return (d - EPOCH.date()).days


def iso(m: int) -> str:
    return from_minutes(m).strftime("%Y-%m-%dT%H:%M")


def parse(text: str) -> int:
    """'2026-10-20T14:30' or '2026-10-20' (start of day) -> engine minutes."""
    if "T" in text or " " in text:
        return to_minutes(datetime.fromisoformat(text.replace(" ", "T")))
    return date_index(date.fromisoformat(text)) * 1440
