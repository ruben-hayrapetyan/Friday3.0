"""A repeating task's times kept apart (PROGRESS.md C50, 8 Nov: "laundry sessions should have a minimum of 7 days
between each event"; weekly Laundry was planned on Sunday and again on Tuesday). Set on the repeat (`min_gap_days`),
by its field or a rule in words. Counted from when you did the last one: the next waits until that many days after
its start, and if that one was done late its due moves by as much. Each later one waits that long after the one before
it, as the plan places it (a dependency with a lag). A strong preference, not a wall: the wait is never longer than
leaves the time's own length before its due, so keeping times apart never makes one late; it's closer then."""

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
    items: list[Item], waits: list[Dependency], originals: dict[int, Item], late: set[int]
) -> tuple[list[Item], list[Dependency]]:
    """The late spaced times back as they were, without their waits: closer than asked rather than late."""
    back = late & set(originals)
    if not back:
        return items, waits
    return [originals[i.id] if i.id in back else i for i in items], [w for w in waits if w.item_id not in back]


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
