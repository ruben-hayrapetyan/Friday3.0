"""Progress and remaining work (DESIGN §8). Recorded progress is summed from rows; nothing is inferred silently,
except that today's unreviewed past blocks count while `assume_unreviewed = done`, until the review settles them.
"""

import sqlite3
from collections import defaultdict
from typing import Any

from friday.core.db import rows
from friday.core.items import Item, amount_units
from friday.core.time import UNIT_MIN


def recorded_minutes(progress: list[dict[str, Any]]) -> int:
    """The latest slider row sets the total at its time; every other row adds to it."""
    total = 0
    for row in sorted(progress, key=lambda r: (r["created_utc"], r["id"])):
        total = row["minutes"] if row["source"] == "slider" else total + row["minutes"]
    return total


def progress_rows(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows(conn, "SELECT * FROM progress WHERE user_id = ?", [user_id]):
        out[row["item_id"]].append(row)
    return out


def minutes_by_item(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, int]:
    return {item_id: recorded_minutes(found) for item_id, found in progress_rows(conn, user_id).items()}


def remaining_minutes(item: Item, done_minutes: int) -> int | None:
    """What's left of the item's amount (its ideal for elastic items); None for open items."""
    if item.amount == "open":
        return None
    amount = item.ideal_units if item.amount == "elastic" else amount_units(item)
    return max(0, (amount or 0) * UNIT_MIN - done_minutes)


def actual_minutes(progress: list[dict[str, Any]], planned_minutes: int) -> tuple[int, str]:
    """Actual time for a completion (§8 rule 6): timer total, else review and retro, else the plan, assumed."""
    timer = sum(r["minutes"] for r in progress if r["source"] == "timer")
    if timer:
        return timer, "timer"
    reviewed = [r for r in progress if r["source"] in ("review", "retro")]
    if reviewed:
        source = "review" if any(r["source"] == "review" for r in reviewed) else "retro"
        return sum(r["minutes"] for r in reviewed), source
    return planned_minutes, "assumed"
