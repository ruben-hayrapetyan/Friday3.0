"""An event that holds a task's time (27 Oct: "right now a4 dd is meant to serve as a time storage for doing the a4
design doc"): "A4dd" on your calendar is when you'll write "CS A4 Design Doc". The planner gives the task the event's
time, from its start (or now, once it has begun) for as long as the task has left, as a lock no other work may use;
what's left of the event still keeps other work off. The event itself stays on the calendar as it is, with the task's
block in it. Pure: the snapshot passes what it read (`event_hold` sets the link)."""

from dataclasses import replace

from friday.core.items import Item
from friday.core.time import format_utc, parse_utc
from friday.planner.progress import remaining_minutes
from friday.planner.snapshot import PinRow

UNIT = 15  # minutes; the grid's quarter hour


def held(
    items: tuple[Item, ...],
    pins: tuple[PinRow, ...],
    holds: dict[int, int],
    done: dict[int, int],
    now_utc: int,
    loose: frozenset[int] = frozenset(),
) -> tuple[tuple[Item, ...], tuple[PinRow, ...]]:
    """The items and pins as the planner sees them with each held event given to its task. A task held by two events
    takes the earlier first, each for what the ones before left; a task done, or an event over, holds nothing. An event
    in `loose` (you let it move when it made work late, `resolve`) asks for the task there rather than holding it."""
    by_id = {i.id: i for i in items}
    changed: dict[int, Item] = {}
    extra: list[PinRow] = []
    left: dict[int, int] = {}
    events = sorted(
        (
            by_id[e]
            for e in holds
            if e in by_id and by_id[e].when == "fixed" and by_id[e].start_utc and by_id[e].end_utc
        ),
        key=lambda e: parse_utc(e.start_utc or ""),
    )
    for event in events:
        assert event.id is not None and event.start_utc is not None and event.end_utc is not None
        task = by_id.get(holds[event.id])
        if task is None or task.id is None or task.when == "fixed" or task.status != "todo" or event.status != "todo":
            continue
        start, end = max(parse_utc(event.start_utc), now_utc - now_utc % UNIT), parse_utc(event.end_utc)
        if task.id not in left:
            left[task.id] = remaining_minutes(task, done.get(task.id, 0)) or 0
        if start >= end or left[task.id] <= 0:
            continue
        length = min(-(-left[task.id] // UNIT) * UNIT, end - start)
        left[task.id] -= length
        extra.append(PinRow(-event.id, task.id, start, start + length, "preferred" if event.id in loose else "locked"))
        # What the task doesn't need stays the event's, without the gap its kind keeps before it (the task is there).
        changed[event.id] = (
            replace(event, start_utc=format_utc(start + length), buffer_before_min=0, buffer_after_min=0)
            if start + length < end
            else replace(event, blocks_time=False)
        )
    return tuple(changed.get(i.id or 0, i) for i in items), pins + tuple(extra)
