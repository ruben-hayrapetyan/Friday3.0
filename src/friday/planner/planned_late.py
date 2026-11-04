"""Which work your plans showed late, and how late at most (2 Nov): what learn/beat_plan.py checks your finishes
against. Kept in kv `planned_late` as {item id: {"hours": the most, "last": when last shown late}}, written with each
current plan; the first write reads it back from the plans saved before, so what you already finished counts."""

import json
import sqlite3
from collections.abc import Mapping

from friday.core.db import rows
from friday.core.time import format_utc
from friday.planner.store import kv_get, kv_set

KEY = "planned_late"
KEPT_DAYS = 120


def remember(conn: sqlite3.Connection, user_id: int, late_hours: Mapping[int | str, float], now_utc: int) -> None:
    """Add a current plan's late work, in the caller's transaction; entries not shown late for `KEPT_DAYS` go."""
    found = kv_get(conn, KEY, None, user_id)
    fresh = found is None
    if found is None:
        found = from_saved_plans(conn, user_id, now_utc)
    if not late_hours and not fresh:
        return
    now = format_utc(now_utc)
    for key, hours in late_hours.items():
        was = found.get(str(key), {})
        found[str(key)] = {"hours": round(max(float(hours), was.get("hours", 0.0)), 2), "last": now}
    cutoff = format_utc(now_utc - KEPT_DAYS * 1440)
    kv_set(conn, KEY, {k: v for k, v in found.items() if v["last"] >= cutoff}, user_id)


def from_saved_plans(conn: sqlite3.Connection, user_id: int, now_utc: int) -> dict[str, dict]:
    """The same record, read from the plans saved in the last `KEPT_DAYS`."""
    found: dict[str, dict] = {}
    for r in rows(
        conn,
        "SELECT created_utc, json_extract(report, '$.late_hours') AS late FROM plans WHERE user_id = ? "
        "AND status IN ('current', 'replaced') AND created_utc >= ? ORDER BY id",
        [user_id, format_utc(now_utc - KEPT_DAYS * 1440)],
    ):
        for key, hours in json.loads(r["late"] or "{}").items():
            was = found.get(key, {})
            found[key] = {"hours": round(max(float(hours), was.get("hours", 0.0)), 2), "last": r["created_utc"]}
    return found


def planned_late(conn: sqlite3.Connection, user_id: int) -> dict[int, float]:
    """Item id → the most hours late a plan showed it."""
    return {int(k): float(v["hours"]) for k, v in (kv_get(conn, KEY, {}, user_id) or {}).items()}
