"""Every database write a command makes, recorded so the command can be undone (DESIGN §9.2).

Undo data is the list of changes: an insert is undone by deleting the row, an update by restoring the row before,
a delete by inserting the full row again. Undo applies only if every row still looks as the command left it.
"""

import json
import sqlite3
from typing import Any

from friday.core.db import one

# Tables without an `id` column, keyed by these columns instead.
TABLE_KEYS = {
    "blocks": ("plan_id", "item_id", "start_utc"),
    "timer": ("user_id",),
    "reviews": ("user_id", "date"),
    "day_overrides": ("user_id", "date"),
    "settings": ("user_id", "key"),
    "kv": ("user_id", "key"),
    "checkins": ("user_id", "date"),
    "learned_profile": ("user_id", "version"),
}

Key = dict[str, Any]
Row = dict[str, Any]


class StaleUndo(ValueError):
    def __init__(self, table: str, key: Key, by: str | None):
        later = f"; undo {by} first" if by else ""
        super().__init__(f"{table} {key} changed since{later}")
        self.table, self.key, self.by = table, key, by


def key_columns(table: str) -> tuple[str, ...]:
    return TABLE_KEYS.get(table, ("id",))


def where(key: Key) -> tuple[str, list[Any]]:
    return " AND ".join(f"{column} = ?" for column in key), list(key.values())


class Writer:
    def __init__(self, conn: sqlite3.Connection, user_id: int):
        self.conn = conn
        self.user_id = user_id
        self.changes: list[dict[str, Any]] = []

    def fetch(self, table: str, key: Key) -> Row | None:
        clause, params = where(key)
        return one(self.conn, f"SELECT * FROM {table} WHERE {clause}", params)

    def insert(self, table: str, values: Row) -> int:
        values = {"user_id": self.user_id} | values
        columns = ", ".join(values)
        cursor = self.conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({', '.join('?' * len(values))})", list(values.values())
        )
        key = {c: values[c] for c in key_columns(table)} if table in TABLE_KEYS else {"id": cursor.lastrowid}
        self.changes.append({"op": "insert", "table": table, "key": key, "after": self.fetch(table, key)})
        return int(cursor.lastrowid or 0)

    def update(self, table: str, key: Key, values: Row) -> None:
        before = self.fetch(table, key)
        if before is None:
            raise ValueError(f"{table} {key} doesn't exist")
        if all(before.get(k) == v for k, v in values.items()):
            return
        clause, params = where(key)
        assignments = ", ".join(f"{column} = ?" for column in values)
        self.conn.execute(f"UPDATE {table} SET {assignments} WHERE {clause}", [*values.values(), *params])
        after = self.fetch(table, key)
        self.changes.append({"op": "update", "table": table, "key": key, "before": before, "after": after})

    def delete(self, table: str, key: Key) -> None:
        before = self.fetch(table, key)
        if before is None:
            return
        clause, params = where(key)
        self.conn.execute(f"DELETE FROM {table} WHERE {clause}", params)
        self.changes.append({"op": "delete", "table": table, "key": key, "before": before})

    def upsert(self, table: str, key: Key, values: Row) -> None:
        if self.fetch(table, key) is None:
            self.insert(table, key | values)
        else:
            self.update(table, key, values)

    def undo_data(self) -> str | None:
        return json.dumps(self.changes) if self.changes else None

    def revert(self, changes: list[dict[str, Any]], later_writer: "LaterCommands") -> None:
        """Undo `changes`, newest first, through this writer so the undo can itself be undone."""
        final: dict[str, dict[str, Any]] = {}  # a command may write one row twice; its last write is what to find
        for change in changes:
            final[json.dumps([change["table"], change["key"]], sort_keys=True)] = change
        changes = [c for c in changes if not passing(c)]  # a replan may have taken them since: nothing to put back
        for change in final.values():
            if not passing(change):
                self.check_unchanged(change, later_writer)
        for change in reversed(changes):
            table, key = change["table"], change["key"]
            if change["op"] == "insert":
                self.delete(table, key)
            elif change["op"] == "update":
                self.update(table, key, {k: v for k, v in change["before"].items() if k not in key})
            else:
                self.insert(table, {k: v for k, v in change["before"].items() if k != "user_id"})

    def check_unchanged(self, change: dict[str, Any], later: "LaterCommands") -> None:
        now = self.fetch(change["table"], change["key"])
        expected = None if change["op"] == "delete" else change["after"]
        if now != expected:
            raise StaleUndo(change["table"], change["key"], later.touching(change["table"], change["key"]))


# Notes a command leaves for the next replan, which takes them (`next_stability` after a rule or pace change,
# `next_cold` after a picked way): gone by the time you undo, they're no reason to refuse it (26 Oct: undoing a rule
# after the plan refreshed always failed, "kv next_stability changed since").
PASSING = {"next_stability", "next_cold"}


def passing(change: dict[str, Any]) -> bool:
    return change["table"] == "kv" and change["key"].get("key") in PASSING


class LaterCommands:
    """The commands logged after one being undone, to name the one that changed a row since."""

    def __init__(self, conn: sqlite3.Connection, after_id: int, user_id: int):
        self.logged = conn.execute(
            "SELECT id, command, undo FROM command_log WHERE user_id = ? AND id > ? AND undo IS NOT NULL "
            "AND undone_by IS NULL ORDER BY id DESC",
            [user_id, after_id],
        ).fetchall()

    def touching(self, table: str, key: Key) -> str | None:
        for row in self.logged:
            if any(c["table"] == table and c["key"] == key for c in json.loads(row["undo"])):
                return f"C{row['id']} ({row['command']})"
        return None
