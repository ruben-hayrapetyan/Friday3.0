"""Learning from your meals (Sleep & meals → Meals): when you eat each one, for how long, how regularly and how often
you skip it. Pure: no database.

- A meal belongs to the planning day it starts in (a 1am snack is the day before's).
- Each meal's usual start and length are the medians of its eaten days, on weekdays and at weekends apart, once a
  group has `min_days` recorded days (eaten or skipped); the start to the quarter hour. How much the start moves is
  the spread of the middle half of those days.
- How often you skip it: skipped days over recorded ones. A day with nothing tapped isn't counted: you may just not
  have tapped.
- A meal whose routine is planned 10 minutes or more off the length you take is offered the length you take.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median, quantiles

KINDS = ("breakfast", "lunch", "dinner", "snack")
WEEKENDS = (5, 6)  # Saturday, Sunday
QUARTER = 15
OFF_BY = 10  # minutes a learned length must differ from the planned one to be worth offering


@dataclass(frozen=True)
class Meal:
    id: int
    kind: str
    date: date  # the planning day
    start: datetime | None  # local; None when skipped
    end: datetime | None  # local; None while eating or skipped
    skipped: bool = False

    @property
    def minutes(self) -> int | None:
        if self.start is None or self.end is None:
            return None
        minutes = int((self.end - self.start).total_seconds() // 60)
        return minutes if 0 < minutes <= 4 * 60 else None


@dataclass(frozen=True)
class Learned:
    kind: str
    group: str  # weekdays or weekends
    days: int
    usual_start: str | None
    usual_min: int | None
    start_spread_min: int | None
    skip_share: float | None


def group_of(day: date) -> str:
    return "weekends" if day.weekday() in WEEKENDS else "weekdays"


def minute_of(moment: datetime, day: date) -> int:
    """Minutes from the planning day's midnight: a meal after midnight counts past 24:00, so the median stays right."""
    return int((moment - datetime.combine(day, datetime.min.time(), moment.tzinfo)).total_seconds() // 60)


def clock(minutes: int) -> str:
    rounded = round(minutes / QUARTER) * QUARTER
    return f"{rounded // 60 % 24:02d}:{rounded % 60:02d}"


def learn(meals: Iterable[Meal], min_days: int) -> list[Learned]:
    """Each meal's usual start, length, regularity and skips, by weekdays and weekends, where there are enough days."""
    by: dict[tuple[str, str], dict[date, Meal]] = {}
    for m in meals:
        days = by.setdefault((m.kind, group_of(m.date)), {})
        if m.date not in days or (days[m.date].skipped and not m.skipped):  # a meal eaten counts over a skip
            days[m.date] = m
    out = []
    for kind in KINDS:
        for group in ("weekdays", "weekends"):
            days = by.get((kind, group), {})
            if len(days) < min_days:
                continue
            eaten = [m for m in days.values() if not m.skipped and m.start is not None]
            starts = sorted(minute_of(m.start, m.date) for m in eaten if m.start is not None)
            lengths = [n for n in (m.minutes for m in eaten) if n is not None]
            spread = None
            if len(starts) >= 4:
                q1, _, q3 = quantiles(starts, n=4)
                spread = int(q3 - q1)
            out.append(
                Learned(
                    kind=kind,
                    group=group,
                    days=len(days),
                    usual_start=clock(int(median(starts))) if starts else None,
                    usual_min=int(round(median(lengths) / 5) * 5) if lengths else None,
                    start_spread_min=spread,
                    skip_share=round(sum(m.skipped for m in days.values()) / len(days), 2),
                )
            )
    return out


def length_changes(learned: list[Learned], planned: dict[str, int]) -> dict[str, int]:
    """Meals whose routine (`planned`: minutes, by meal) is 10 minutes or more off what you take: the length you take,
    from the weekdays' days where there are enough, else the weekends'."""
    out = {}
    for kind, minutes in planned.items():
        mine = [x for x in learned if x.kind == kind and x.usual_min]
        usual = next((x.usual_min for x in mine if x.group == "weekdays"), None) or next(
            (x.usual_min for x in mine), None
        )
        if usual is not None and abs(usual - minutes) >= OFF_BY:
            out[kind] = usual
    return out
