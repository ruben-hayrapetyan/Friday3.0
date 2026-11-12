"""SQLite: connection, migrations and small query helpers (DESIGN §7). No ORM."""

import logging
import sqlite3
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MIGRATIONS = Path(__file__).parent / "migrations"


log = logging.getLogger("friday.db")
SLOW_MS = 300  # a wait for the write lock, or a hold of it, past this is logged: a click waits that long too
_waited: dict[int, float] = {}


def begin_write(conn: sqlite3.Connection, who: str) -> None:
    """BEGIN IMMEDIATE, timed: how long it waited for another writer is kept for `waited` (the command's log line),
    and said when it was long (12 Nov: clicks took seconds while something else held the lock, and the log couldn't
    say what)."""
    started = time.perf_counter()
    conn.execute("BEGIN IMMEDIATE")
    ms = (time.perf_counter() - started) * 1000
    _waited[id(conn)] = ms
    if ms > SLOW_MS:
        log.warning("%s waited %.0f ms for the database (another write held it)", who, ms)


def waited(conn: sqlite3.Connection) -> float:
    """How long this connection's last `begin_write` waited, in ms (0 when it didn't)."""
    return _waited.pop(id(conn), 0.0)


def held(who: str, since: float) -> None:
    """Say a write that held the lock long: `since` is time.perf_counter() when it took it."""
    ms = (time.perf_counter() - since) * 1000
    if ms > SLOW_MS:
        log.warning("%s held the database for %.0f ms (other writes waited)", who, ms)


def connect(path: str | Path) -> sqlite3.Connection:
    # Autocommit mode, so transactions are only the ones `transaction()` opens.
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    migrate(conn)
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> None:
    for path in sorted(MIGRATIONS.glob("*.sql")):
        number = int(path.name.split("_")[0])
        if number > schema_version(conn):
            # Rebuilding a table (SQLite can't alter a CHECK) drops it while rows still point at it, so foreign
            # keys are off for the migration and checked once it is done (SQLite's documented procedure).
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript(f"BEGIN;\n{path.read_text()}\nPRAGMA user_version = {number};\nCOMMIT;")
            conn.execute("PRAGMA foreign_keys = ON")
            broken = conn.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise sqlite3.IntegrityError(f"migration {path.name} left broken references: {broken[:3]}")


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def rows(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params)]


def one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None
