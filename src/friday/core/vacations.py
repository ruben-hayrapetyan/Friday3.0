"""Breaks (vacation days, 18 Nov): a run of days off or light.

On a break day repeating events pause (one-off events stay), meals aren't planned unless you say so, tasks of a paused
tag wait, and the day is sized by things rather than hours: Off, nothing (work due inside is done before it starts);
Light, about `per_day` things, each counted at LIGHT_MIN_PER_THING when the planner sizes the day. The day shows a list
of what to get done, not times (web: the day's line under the break's band). Stored as `vacations`: "breaks" already
names naps and snacks in the code (`web/src/now/breaks.ts`, `snapshot.away`).
"""

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

from friday.core.db import rows
from friday.core.items import Item
from friday.core.quickadd import MEAL
from friday.core.settings import BreakSettings, Pause, minutes_of
from friday.core.time import parse_utc, planning_date

# What one thing on a Light day's list is sized at, inside: never shown (18 Nov: tasks, not time).
LIGHT_MIN_PER_THING = 45
FRIDAY_CALENDAR = "Friday"  # what the pause chooser calls events made here, on no calendar of yours
OWN = ("per_day", "pause", "plan_meals", "keep_sleep")  # what a break may set for itself, else your defaults


@dataclass(frozen=True)
class Vacation:
    id: int
    name: str
    start: str  # ISO date, the first day
    end: str  # ISO date, the last day (inclusive)
    mode: str  # "off" or "light"
    per_day: int = 3
    pause: Pause = Pause()
    plan_meals: bool = False
    keep_sleep: bool = False
    own: frozenset[str] = frozenset()  # which of OWN this break set itself

    @property
    def first(self) -> date:
        return date.fromisoformat(self.start)

    @property
    def last(self) -> date:
        return date.fromisoformat(self.end)

    def covers(self, day: date) -> bool:
        return self.first <= day <= self.last

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1

    def day_n(self, day: date) -> int:
        return (day - self.first).days + 1

    def dates(self) -> Iterable[date]:
        return (self.first + timedelta(days=n) for n in range(self.days))


def from_row(row: Mapping[str, Any], defaults: BreakSettings) -> Vacation:
    own = frozenset(k for k in OWN if row[k] is not None)
    return Vacation(
        id=row["id"],
        name=row["name"],
        start=row["start_date"],
        end=row["end_date"],
        mode=row["mode"],
        per_day=row["per_day"] if row["per_day"] is not None else defaults.per_day,
        pause=Pause.model_validate(json.loads(row["pause"])) if row["pause"] is not None else defaults.pause,
        plan_meals=bool(row["plan_meals"]) if row["plan_meals"] is not None else defaults.plan_meals,
        keep_sleep=bool(row["keep_sleep"]) if row["keep_sleep"] is not None else defaults.keep_sleep,
        own=own,
    )


def load(conn: sqlite3.Connection, user_id: int, defaults: BreakSettings) -> tuple[Vacation, ...]:
    found = rows(conn, "SELECT * FROM vacations WHERE user_id = ? ORDER BY start_date, id", [user_id])
    return tuple(from_row(r, defaults) for r in found)


def on(day: date, vacations: Iterable[Vacation]) -> Vacation | None:
    return next((v for v in vacations if v.covers(day)), None)


def pauses(pause: Pause, *, series_id: int | None, calendar: str | None) -> bool:
    """Whether a break with this `pause` pauses an event: only repeats pause; one named in `series_kept` or
    `series_paused` goes its own way; else its calendar decides ("all": every one but those listed; "only": just
    those listed). An event made here, on no calendar, counts as FRIDAY_CALENDAR."""
    if series_id is None:
        return False
    if series_id in pause.series_kept:
        return False
    if series_id in pause.series_paused:
        return True
    if pause.repeating == "all":
        return (calendar or FRIDAY_CALENDAR) not in pause.calendars
    return calendar is not None and calendar in pause.calendars


def day_cap_hours(vacation: Vacation, usual: float) -> float:
    """A break day's most work, inside: none when Off; about `per_day` things when Light, and never more than your own
    cap that day."""
    if vacation.mode == "off":
        return 0.0
    return min(usual, vacation.per_day * LIGHT_MIN_PER_THING / 60)


def item_day(item: Item, tz: str, day_start: int) -> date | None:
    """The planning day an event or a time of a routine is on."""
    if item.occurrence_date and item.when != "fixed":
        return date.fromisoformat(item.occurrence_date[:10])
    moment = item.start_utc or item.release_utc
    return planning_date(parse_utc(moment), tz, day_start) if moment else None


def is_meal(item: Item) -> bool:
    return item.preset == "Routine" and item.amount == "elastic" and MEAL.search(item.title) is not None


def on_break(
    items: tuple[Item, ...],
    vacations: tuple[Vacation, ...],
    settings: Mapping[str, Any],
    calendars: Mapping[int, str],
) -> tuple[tuple[Item, ...], frozenset[int]]:
    """The items as a break leaves them: each repeat it pauses blocks no time (and is returned, to be drawn paused);
    a meal on a break day isn't planned unless the break plans meals."""
    if not vacations:
        return items, frozenset()
    tz, day_start = settings["time"].timezone, minutes_of(settings["time"].day_start)
    out, paused = [], set()
    for item in items:
        day = item_day(item, tz, day_start) if item.when == "fixed" or item.series_id is not None else None
        vacation = on(day, vacations) if day is not None else None
        if vacation is None:
            out.append(item)
        elif item.when == "fixed":
            calendar = calendars.get(item.id) if item.id is not None else None
            if item.id is not None and pauses(vacation.pause, series_id=item.series_id, calendar=calendar):
                paused.add(item.id)
                out.append(replace(item, blocks_time=False))
            else:
                out.append(item)
        elif is_meal(item) and not vacation.plan_meals:
            continue
        else:
            out.append(item)
    return tuple(out), frozenset(paused)


def with_caps(
    overrides: Mapping[date, Mapping[str, Any]],
    vacations: tuple[Vacation, ...],
    usual: Any,
    first: date,
    last: date,
) -> dict[date, dict[str, Any]]:
    """Day overrides with each break day's cap (`usual(day)`: your cap that day without the break), from `first` to
    `last`: the planner's own days only, so a summer-long break costs no more than its weeks ahead."""
    out = {d: dict(v) for d, v in overrides.items()}
    for vacation in vacations:
        day = max(vacation.first, first)
        while day <= min(vacation.last, last):
            out.setdefault(day, {})["cap_hours"] = day_cap_hours(vacation, usual(day))
            day += timedelta(days=1)
    return out


def paused_tags(vacations: tuple[Vacation, ...], first: date, last: date) -> dict[tuple[str, ...], list[str]]:
    """Each set of paused tags, and the break days (ISO) it holds on, from `first` to `last`."""
    out: dict[tuple[str, ...], list[str]] = {}
    for vacation in vacations:
        tags = tuple(sorted(set(vacation.pause.tags)))
        if not tags or vacation.mode == "off":  # Off plans nothing anyway
            continue
        out.setdefault(tags, []).extend(d.isoformat() for d in vacation.dates() if first <= d <= last)
    return {k: v for k, v in out.items() if v}


def break_dates(conn: sqlite3.Connection, user_id: int) -> frozenset[date]:
    """Every day on one of your breaks."""
    out: set[date] = set()
    for r in rows(conn, "SELECT start_date, end_date FROM vacations WHERE user_id = ?", [user_id]):
        day, last = date.fromisoformat(r["start_date"]), date.fromisoformat(r["end_date"])
        while day <= last:
            out.add(day)
            day += timedelta(days=1)
    return frozenset(out)


def on_a_break(conn: sqlite3.Connection, user_id: int, settings: Mapping[str, Any]) -> Any:
    """Whether a moment (a stored UTC time) fell on a break day: what learning and Insights leave out (18 Nov: "learning
    and insights should be paused during the break")."""
    dates = break_dates(conn, user_id)
    if not dates:
        return lambda _moment: False
    tz, day_start = settings["time"].timezone, minutes_of(settings["time"].day_start)
    if tz is None:
        return lambda _moment: False
    return lambda moment: moment is not None and planning_date(parse_utc(moment), tz, day_start) in dates
