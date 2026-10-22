"""Publishing the plan to Google Calendar (DESIGN §22.3): the current plan's blocks from now to the end of the
horizon become the events of a "Friday" calendar, at most once every `gcal.publish_debounce_s`, and only when the
plan changed. Fixed items aren't blocks, so what came from Google is never copied back. The server's job loop runs
this every minute; kv `gcal_publish` keeps the calendar id and what was published last.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from friday.core.db import rows
from friday.core.time import format_utc, parse_utc
from friday.planner.prepare import block_key
from friday.planner.store import current_plan, kv_get, load_settings
from friday.sync import gcal, google_auth


def publish_plan(
    conn: sqlite3.Connection, now_utc: int, user_id: int = 1, folder: Path | None = None, google: Any | None = None
) -> bool:
    """Publish when it is due; returns whether it did."""
    settings = load_settings(conn, user_id)
    wanted, saved = settings["gcal"], current_plan(conn, user_id)
    if not wanted.publish or saved is None:
        return False
    state = kv_get(conn, "gcal_publish", {}, user_id) or {}
    if state.get("plan") == saved["id"]:
        return False
    if state.get("at") and (now_utc - parse_utc(state["at"])) * 60 < wanted.publish_debounce_s:
        return False
    google = google or (google_auth.calendar(folder) if folder else None)
    if google is None:
        return False
    calendar = gcal.own_calendar(google, state.get("calendar"), settings["time"].timezone)
    until = now_utc + settings["time"].horizon_days * 24 * 60
    gcal.publish(
        google, calendar, blocks(conn, saved["id"], now_utc, until, settings["notify"].app_url), gcal.rfc3339(now_utc)
    )
    state = {"calendar": calendar, "plan": saved["id"], "at": format_utc(now_utc)}
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'gcal_publish', ?) ON CONFLICT (user_id, key) "
        "DO UPDATE SET value = excluded.value",
        [user_id, json.dumps(state)],
    )
    return True


def blocks(conn: sqlite3.Connection, plan_id: int, now_utc: int, until: int, app_url: str | None) -> list[gcal.Block]:
    found = rows(
        conn,
        "SELECT b.item_id, b.start_utc, b.end_utc, b.tentative, i.title FROM blocks b JOIN items i ON i.id = b.item_id "
        "WHERE b.plan_id = ? AND b.end_utc > ? AND b.start_utc < ? ORDER BY b.start_utc",
        [plan_id, format_utc(now_utc), format_utc(until)],
    )
    return [
        gcal.Block(
            key=block_key(r["item_id"], parse_utc(r["start_utc"])),
            title=r["title"],
            start=gcal.rfc3339(parse_utc(r["start_utc"])),
            end=gcal.rfc3339(parse_utc(r["end_utc"])),
            tentative=bool(r["tentative"]),
            link=f"{app_url.rstrip('/')}/#/" if app_url else None,
        )
        for r in found
    ]
