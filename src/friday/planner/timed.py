"""What the timer says about a planned block that has passed (5 Nov: the Inbox asked "did you do it?" of CS A4
Complete while its timer ran, and of everything else planned that evening). Timed time is accounted for: a block of
the timed task is what the sitting replaces, and a block mostly under other things' sittings didn't happen, as you
were doing those. Neither is asked about or counted done; the review, the plan's assumed progress and the calendar
all go by this. A task that runs by itself (laundry) needs you only at its start, so timing it covers nothing else,
and its own block isn't covered by what you timed meanwhile."""

import sqlite3
from collections.abc import Collection, Iterable, Sequence

from friday.core.time import format_utc, parse_utc

Sitting = tuple[int, int, int]  # item id, start, end (UTC minutes)

OWN = "own"  # a sitting of the block's own task over it: the sitting is what happened there
OTHER = "other"  # other things timed over at least half of it: it wasn't done


def timed_over(
    item_id: int, start: int, end: int, sittings: Sequence[Sitting], background: Collection[int] = ()
) -> str | None:
    """OWN when a sitting of the block's task overlaps it, OTHER when sittings of other things that need you cover at
    least half of it, else None: Friday can't tell, so it asks (or counts it done)."""
    if any(i == item_id and s < end and e > start for i, s, e in sittings):
        return OWN
    if item_id in background or end <= start:
        return None
    covered = covered_minutes(start, end, [(s, e) for i, s, e in sittings if i not in background])
    return OTHER if 2 * covered >= end - start else None


def covered_minutes(start: int, end: int, spans: Iterable[tuple[int, int]]) -> int:
    """How much of `start`…`end` the spans cover, each minute once (two timers at once don't count it twice)."""
    clipped = sorted((max(s, start), min(e, end)) for s, e in spans if s < end and e > start)
    total, reach = 0, start
    for s, e in clipped:
        if e > reach:
            total += e - max(s, reach)
            reach = e
    return total


def with_running(found: Iterable[Sitting], running: Iterable[tuple[int, int]], now: int) -> list[Sitting]:
    """Finished sittings and the timers running now (item id, start), each running one so far."""
    return [*found, *((item_id, since, now) for item_id, since in running if since < now)]


def sittings_between(conn: sqlite3.Connection, user_id: int, lo: int, hi: int, now: int) -> list[Sitting]:
    """Every timer sitting touching `lo`…`hi`, the running timers included up to `now`."""
    found = [
        (r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]))
        for r in conn.execute(
            "SELECT item_id, start_utc, end_utc FROM progress WHERE user_id = ? AND source = 'timer' "
            "AND start_utc IS NOT NULL AND end_utc IS NOT NULL AND start_utc < ? AND end_utc > ?",
            [user_id, format_utc(hi), format_utc(lo)],
        )
    ]
    running = [
        (r["item_id"], parse_utc(r["start_utc"]))
        for r in conn.execute("SELECT item_id, start_utc FROM timer WHERE user_id = ?", [user_id])
    ]
    return with_running(found, running, now)


def background_ids(conn: sqlite3.Connection, user_id: int) -> set[int]:
    """The tasks that run by themselves once started."""
    found = conn.execute("SELECT id FROM items WHERE user_id = ? AND background = 1", [user_id])
    return {r["id"] for r in found}
