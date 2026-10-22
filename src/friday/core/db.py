"""SQLite: connection, migrations and small query helpers (DESIGN §7). No ORM."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MIGRATIONS = Path(__file__).parent / "migrations"


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
