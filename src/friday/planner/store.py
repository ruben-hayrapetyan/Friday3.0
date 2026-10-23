"""Reads shared by the planner and the commands: settings, the plan generation, items. Writes live with commands."""

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from friday.core.db import one, rows
from friday.core.items import Item
from friday.core.rows import item_from_row
from friday.core.settings import DEFAULTS, validate_value


def load_settings(conn: sqlite3.Connection, user_id: int = 1) -> dict[str, Any]:
    """Every settings key: stored values over the defaults."""
    stored = rows(conn, "SELECT key, value FROM settings WHERE user_id = ?", [user_id])
    return DEFAULTS | {r["key"]: validate_value(r["key"], json.loads(r["value"])) for r in stored}


def settings_version(conn: sqlite3.Connection, user_id: int = 1) -> int:
    found = one(conn, "SELECT max(version) AS v FROM settings WHERE user_id = ?", [user_id])
    return int(found["v"] or 0) if found else 0


def kv_get(conn: sqlite3.Connection, key: str, default: Any = None, user_id: int = 1) -> Any:
    found = one(conn, "SELECT value FROM kv WHERE user_id = ? AND key = ?", [user_id, key])
    return json.loads(found["value"]) if found else default


def kv_set(conn: sqlite3.Connection, key: str, value: Any, user_id: int = 1) -> None:
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT (user_id, key) DO UPDATE SET value = "
        "excluded.value",
        [user_id, key, json.dumps(value)],
    )


def generation(conn: sqlite3.Connection, user_id: int = 1) -> int:
    return int(kv_get(conn, "generation", 0, user_id))


def load_item(conn: sqlite3.Connection, item_id: int, user_id: int = 1) -> Item | None:
    found = one(conn, "SELECT * FROM items WHERE id = ? AND user_id = ?", [item_id, user_id])
    return item_from_row(found) if found else None


def area_names(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, str]:
    return {r["id"]: r["name"] for r in rows(conn, "SELECT id, name FROM areas WHERE user_id = ?", [user_id])}


def current_plan(conn: sqlite3.Connection, user_id: int = 1) -> dict[str, Any] | None:
    return one(conn, "SELECT * FROM plans WHERE user_id = ? AND status = 'current'", [user_id])


@dataclass(frozen=True)
class EventLink:
    """Where a calendar event in Friday came from: the source (a Google calendar, or one of the Mac's) and the event
    there."""

    source_id: int
    calendar: str  # the source's name
    calendar_id: str | None  # Google's id for the calendar, or EventKit's
    event_id: str
    kind: str = "gcal"  # "gcal" or "mac"


def event_links(conn: sqlite3.Connection, user_id: int = 1) -> dict[int, EventLink]:
    """Each event read from a calendar, by item id: the latest suggestion that made or changed it says where."""
    found = rows(
        conn,
        "SELECT s.item_id, r.external_id, src.id AS source_id, src.name, src.kind, "
        "json_extract(src.config, '$.calendar') AS cal FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "JOIN sources src ON src.id = r.source_id WHERE s.user_id = ? AND s.item_id IS NOT NULL "
        "AND s.status = 'accepted' AND src.kind IN ('gcal', 'mac') ORDER BY s.id",
        [user_id],
    )
    return {r["item_id"]: EventLink(r["source_id"], r["name"], r["cal"], r["external_id"], r["kind"]) for r in found}
