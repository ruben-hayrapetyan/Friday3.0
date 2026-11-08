"""`friday.toml` (DESIGN §22.9): at start and within a minute of a change, the whole file is validated, then each
key it sets is written through `settings_set` as actor `config`, logged and undoable. The keys it sets are
remembered in `kv` (`config_keys`); the app shows them read-only and `settings_set` refuses them from anyone else.
"""

import json
import sqlite3
import tomllib
from pathlib import Path

from friday.commands.registry import run
from friday.core.settings import to_json, validate_value
from friday.planner.store import kv_get, load_settings
from friday.server.worker import set_problem


def apply_config(conn: sqlite3.Connection, now_utc: int, path: Path, user_id: int = 1) -> list[str]:
    """Apply the file if it changed since last time; returns the keys written."""
    stamp = path.stat().st_mtime_ns if path.exists() else None
    if stamp == kv_get(conn, "config_stamp", None, user_id):
        return []
    remember(conn, user_id, "config_stamp", stamp)
    if stamp is None:
        remember(conn, user_id, "config_keys", [])
        set_problem(conn, user_id, "config", None)
        return []
    try:
        document = tomllib.loads(path.read_text())
        values = {key: validate_value(key, value) for key, value in document.items()}
    except (tomllib.TOMLDecodeError, ValueError) as error:
        set_problem(
            conn,
            user_id,
            "config",
            f"Your settings file isn't used until it's fixed ({path}): {error}. Friday keeps the settings it had.",
        )
        return []
    set_problem(conn, user_id, "config", None)
    remember(conn, user_id, "config_keys", sorted(values))
    current = load_settings(conn, user_id)
    written = []
    for key, value in values.items():
        if to_json(key, value) != to_json(key, current[key]):
            run(
                conn,
                "settings_set",
                {"key": key, "value": to_json(key, value)},
                now_utc=now_utc,
                actor="config",
                user_id=user_id,
                provisional=False,
            )
            written.append(key)
    return written


def remember(conn: sqlite3.Connection, user_id: int, key: str, value: object) -> None:
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT (user_id, key) DO UPDATE SET "
        "value = excluded.value",
        [user_id, key, json.dumps(value)],
    )
