"""A repeating task's times kept apart (PROGRESS.md C50, 8 Nov: "laundry sessions should have a minimum of 7 days
between each event"; weekly Laundry was planned on Sunday and again on Tuesday). Set on the repeat (`min_gap_days`),
by its field or a rule in words. Counted from when you did the last one: the next waits until that many days after
its start, and if that one was done late its due moves by as much. Each later one waits that long after the one before
it, as the plan places it (a dependency with a lag). A strong preference, not a wall: the wait is never longer than
leaves the time's own length before its due, so keeping times apart never makes one late; it's closer then."""

import math
from dataclasses import dataclass, replace

from friday.core.items import Item
from friday.core.time import MINUTES_PER_DAY, UNIT_MIN, format_utc, parse_utc
from friday.planner.build import Dependency


@dataclass(frozen=True)
class LastDone:
    """The latest done time of a repeat: when its work started and ended, and when it was due."""

    started_utc: int
    done_utc: int
    due_utc: int | None


def spaced(
    items: list[Item], gaps: dict[int, float], last: dict[int, LastDone]
) -> tuple[list[Item], list[Dependency], dict[int, Item]]:
    """The items with the next time of each spaced repeat moved after its last, the waits between the rest, and every
    spaced time as it was, to give back to any that would be late."""
    by_series: dict[int, list[Item]] = {}
    for item in items:
        if item.series_id in gaps and item.status == "todo" and item.due_utc and item.when != "fixed":
            by_series.setdefault(item.series_id, []).append(item)
    changed: dict[int, Item] = {}
    waits: list[Dependency] = []
    for series_id, times in by_series.items():
        gap = round(gaps[series_id] * MINUTES_PER_DAY)
        times.sort(key=lambda i: parse_utc(i.due_utc or ""))
        if (done := last.get(series_id)) is not None:
            changed[times[0].id] = after_last(times[0], gap, done)
        times = [changed.get(item.id, item) for item in times]
        for before, after in zip(times, times[1:], strict=False):
            waits.append(Dependency(after.id, before.id, 1.0, wait(before, after, gap)))
    originals = {item.id: item for times in by_series.values() for item in times}
    return [changed.get(item.id, item) for item in items], waits, originals


def loosened(
    items: list[Item], waits: list[Dependency], originals: dict[int, Item], late: dict[int, float]
) -> tuple[list[Item], list[Dependency]]:
    """Spaced times that would be late, brought closer by as much as they'd be late (and an hour more): a wait shorter
    by that, or a next time allowed that much earlier. A wait that would go to nothing goes, the time as it was."""
    over = {
        i: math.ceil(hours * 60 / UNIT_MIN) * UNIT_MIN + 60 for i, hours in late.items() if i in originals and hours
    }
    if not over:
        return items, waits
    kept = []
    for w in waits:
        lag = w.lag_min - over.get(w.item_id, 0)
        if lag > 0:
            kept.append(replace(w, lag_min=lag))
    moved = []
    for item in items:
        if item.id in over and item.release_utc and item.release_utc != originals[item.id].release_utc:
            earlier = parse_utc(item.release_utc) - over[item.id]
            first = originals[item.id].release_utc
            item = originals[item.id] if first and earlier <= parse_utc(first) else replace(
                item, release_utc=format_utc(earlier)
            )  # fmt: skip
        moved.append(item)
    return moved, kept


def let_go(
    items: list[Item], waits: list[Dependency], originals: dict[int, Item], late: dict[int, float]
) -> tuple[list[Item], list[Dependency]]:
    """Spaced times still late once brought closer: no wait on the one before, and their own window back."""
    still = {i for i, hours in late.items() if i in originals and hours}
    if not still:
        return items, waits
    return [originals[i.id] if i.id in still else i for i in items], [w for w in waits if w.item_id not in still]


def length(item: Item) -> int:
    return (item.duration_units or 0) * UNIT_MIN


def after_last(item: Item, gap: int, done: LastDone) -> Item:
    """The next time: not before `gap` after the last one started, its due moved as late as the last one was done."""
    due = parse_utc(item.due_utc or "")
    if done.due_utc is not None and done.done_utc > done.due_utc:
        due += done.done_utc - done.due_utc
    release = min(done.started_utc + gap, due - length(item))  # closer than asked rather than late
    earliest = parse_utc(item.release_utc) if item.release_utc else None
    if earliest is not None and earliest >= release:
        return replace(item, due_utc=format_utc(due))
    return replace(item, release_utc=format_utc(release), due_utc=format_utc(due))


def wait(before: Item, after: Item, gap: int) -> int:
    """Minutes from the end of one time to the start of the next: `gap` from start to start, but no more than lets the
    next fit before its due if the one before ends at its own."""
    roomy = parse_utc(after.due_utc or "") - parse_utc(before.due_utc or "") - length(after)
    return max(0, min(gap - length(before), roomy))


@dataclass(frozen=True)
class Closer:
    """A spaced time the plan put closer than asked (C50): how far after the one before it starts, in the asked unit."""

    item_id: int
    series_id: int
    apart: float
    asked: float
    unit: str  # "days", or "hours" for a gap under two days ("workouts at least 48 hours apart")
    since_last: bool  # after the last one you did, rather than the one before it in the plan


def closer(
    items: list[Item], gaps: dict[int, float], last: dict[int, LastDone], starts: dict[int, int]
) -> list[Closer]:
    """The spaced times whose planned start is closer to the one before than its repeat asks, as you'd read it: 6.97
    days isn't closer than 7, 6.9 is. Only planned times count; one not in the plan ends its repeat's count."""
    out = []
    for series_id, gap in gaps.items():
        times = sorted(
            (i for i in items if i.series_id == series_id and i.status == "todo" and i.due_utc and i.when != "fixed"),
            key=lambda i: parse_utc(i.due_utc or ""),
        )
        done = last.get(series_id)
        before, since_last = (done.started_utc, True) if done else (None, False)
        unit = "hours" if gap < 2 else "days"
        size = 60 if unit == "hours" else MINUTES_PER_DAY
        asked = round(gap * MINUTES_PER_DAY / size, 1)
        for item in times:
            start = starts.get(item.id)
            if start is None:
                break
            if before is not None and (apart := round((start - before) / size, 1)) < asked:
                out.append(Closer(item.id, series_id, max(apart, 0.0), asked, unit, since_last))
            before, since_last = start, False
    return out


def amount(n: float, unit: str) -> str:
    """5.0 days as "5 days", 1 as "1 day"."""
    shown = f"{n:g}" if n != int(n) else str(int(n))
    return f"{shown} {unit.removesuffix('s') if shown == '1' else unit}"


def closer_words(c: Closer) -> str:
    """'5.6 days after the last one you did, closer than the 7 days you asked, so it isn't late'."""
    after = "the last one you did" if c.since_last else "the one before"
    asked = amount(c.asked, c.unit)
    return f"{amount(c.apart, c.unit)} after {after}, closer than the {asked} you asked, so it isn't late"
