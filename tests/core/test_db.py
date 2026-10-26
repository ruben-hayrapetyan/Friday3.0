import json
import sqlite3
from pathlib import Path

import pytest

from friday.core.db import connect, one, rows, schema_version, transaction

TABLES = {
    "users", "areas", "series", "items", "dependencies", "pins", "plans", "blocks", "progress", "timer",
    "reviews", "completions", "day_overrides", "pace_periods", "settings", "command_log", "notifications",
    "comparisons", "learned_profile", "checkins", "push_subscriptions", "job_runs", "kv", "sources", "raw_inputs",
    "suggestions", "event_writes", "sleep_marks", "meals",
}  # fmt: skip
NOW = "2026-10-18T10:00Z"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return connect(tmp_path / "friday.db")


def add_item(conn: sqlite3.Connection, **changes: object) -> int:
    fields = {"title": "PS5", "when_kind": "window", "amount": "fixed", "shape": "split",
              "created_utc": NOW, "updated_utc": NOW} | changes  # fmt: skip
    sql = f"INSERT INTO items ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})"
    return conn.execute(sql, list(fields.values())).lastrowid  # type: ignore[return-value]


def test_schema_creates_every_table(conn: sqlite3.Connection) -> None:
    names = {r["name"] for r in rows(conn, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert names == TABLES
    assert schema_version(conn) == 16


def test_every_table_is_strict_and_has_a_user(conn: sqlite3.Connection) -> None:
    for table in TABLES - {"users"}:
        columns = {r["name"] for r in rows(conn, f"PRAGMA table_info({table})")}
        assert "user_id" in columns, table
        assert "STRICT" in one(conn, "SELECT sql FROM sqlite_master WHERE name = ?", [table])["sql"], table


def test_reconnecting_does_not_migrate_twice(tmp_path: Path) -> None:
    connect(tmp_path / "friday.db").close()
    assert schema_version(connect(tmp_path / "friday.db")) == 16


def test_wal_and_foreign_keys_are_on(conn: sqlite3.Connection) -> None:
    assert one(conn, "PRAGMA journal_mode")["journal_mode"] == "wal"
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, area_id=99)


@pytest.mark.parametrize(
    "changes", [{"when_kind": "sometime"}, {"amount": "lots"}, {"status": "maybe"}, {"importance": 9}]
)
def test_enums_are_checked(conn: sqlite3.Connection, changes: dict) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, **changes)


def test_only_one_current_plan(conn: sqlite3.Connection) -> None:
    sql = ("INSERT INTO plans (created_utc, generation, reason, status, stage_values, solve_seconds, report) "
           "VALUES (?, 1, 'test', 'current', '{}', 0, '{}')")  # fmt: skip
    conn.execute(sql, [NOW])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, [NOW])


def test_occurrences_are_unique_per_series_date_and_count(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO series (template, rrule, dtstart_local, created_utc, updated_utc) "
                 "VALUES ('{}', 'FREQ=DAILY', '2026-10-18T04:00', ?, ?)", [NOW, NOW])  # fmt: skip
    add_item(conn, series_id=1, occurrence_date="2026-10-18", occurrence_n=1)
    with pytest.raises(sqlite3.IntegrityError):
        add_item(conn, series_id=1, occurrence_date="2026-10-18", occurrence_n=1)


def test_actors_are_checked(conn: sqlite3.Connection) -> None:
    sql = "INSERT INTO command_log (at_utc, actor, command, input, result) VALUES (?, ?, 'add', '{}', '{}')"
    conn.execute(sql, [NOW, "agent:assistant"])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, [NOW, "someone"])


def test_a_failed_transaction_leaves_nothing(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError), transaction(conn):
        add_item(conn)
        add_item(conn, amount="lots")
    assert rows(conn, "SELECT id FROM items") == []


def test_migration_2_keeps_sent_notifications_and_adds_the_check_kind(tmp_path: Path) -> None:
    conn = connect(tmp_path / "friday.db")
    conn.execute(
        "INSERT INTO notifications (kind, dedup_key, channel, sent_utc, title) "
        "VALUES ('check', 'k', 'app', 'x', 'Did you?')"
    )
    assert one(conn, "SELECT title FROM notifications")["title"] == "Did you?"


def test_rebuilding_the_log_keeps_undone_links_on_an_existing_database(tmp_path: Path) -> None:
    import sqlite3 as lite

    from friday.core.db import MIGRATIONS

    path = tmp_path / "old.db"
    old = lite.connect(path, isolation_level=None)
    for name in ("001_initial.sql", "002_notifications.sql"):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 2")
    old.execute(
        "INSERT INTO command_log (id, at_utc, actor, command, input, result) VALUES (1, 'x', 'you', 'add', '{}', '{}')"
    )
    old.execute(
        "INSERT INTO command_log (id, at_utc, actor, command, input, result) VALUES (2, 'x', 'you', 'undo', '{}', '{}')"
    )
    old.execute("UPDATE command_log SET undone_by = 2 WHERE id = 1")
    old.close()
    conn = connect(path)
    assert schema_version(conn) == 16
    assert one(conn, "SELECT undone_by FROM command_log WHERE id = 1")["undone_by"] == 2
    conn.execute(
        "INSERT INTO command_log (at_utc, actor, command, input, result) VALUES ('x', 'sync:Canvas', 'add', '{}', '{}')"
    )


def test_migration_4_clears_what_the_old_reading_left_for_the_next_sync(tmp_path: Path) -> None:
    from friday.core.db import MIGRATIONS

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    for name in ("001_initial.sql", "002_notifications.sql", "003_inbox.sql"):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 3")
    old.executescript(
        """
        INSERT INTO sources (id, kind, name, config) VALUES (1, 'gcal', 'primary', '{"calendar": "me@x"}'),
            (2, 'gcal', '1. Projects', '{"calendar": "me@x"}'), (3, 'gmail', 'Gmail', '{}');
        INSERT INTO raw_inputs (id, source_id, external_id, received_utc, content_hash, content, status, error)
        VALUES (1, 1, 'chem_1', 'x', 'h', 'c', 'extracted', NULL), (2, 3, 'm1', 'x', 'h', 'c', 'failed',
            'Error code: 401 - invalid x-api-key'), (3, 3, 'm2', 'x', 'h', 'c', 'failed', 'bad pdf');
        INSERT INTO suggestions (raw_input_id, command, input, quotes, created_utc)
        VALUES (1, 'add', '{"title": "CHEM"}', '{}', 'x');
        """
    )
    old.close()
    conn = connect(path)
    assert rows(conn, "SELECT * FROM suggestions") == []
    assert [r["external_id"] for r in rows(conn, "SELECT * FROM raw_inputs ORDER BY id")] == ["m1", "m2"]
    assert [r["status"] for r in rows(conn, "SELECT * FROM raw_inputs ORDER BY id")] == ["new", "failed"]
    assert [r["name"] for r in rows(conn, "SELECT * FROM sources WHERE kind = 'gcal'")] == ["primary"]


def test_migration_5_renames_commitment_to_event_and_adds_the_new_kinds(tmp_path: Path) -> None:
    from friday.core.db import MIGRATIONS

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    for name in ("001_initial.sql", "002_notifications.sql", "003_inbox.sql", "004_reread_inputs.sql"):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 4")
    old.executescript(
        """
        INSERT INTO settings (key, value, version, updated_utc) VALUES
            ('presets', '{"Commitment": {"when": "fixed", "event_kind": "other"}}', 1, 'x'),
            ('kind_order', '["Commitment", "Class"]', 1, 'x');
        """
    )
    add_item(old, preset="Commitment")  # type: ignore[arg-type]
    old.close()
    conn = connect(path)
    assert one(conn, "SELECT preset FROM items")["preset"] == "Event"
    presets = json.loads(one(conn, "SELECT value FROM settings WHERE key = 'presets'")["value"])
    assert set(presets) == {"Event", "Exam", "Meeting", "Appointment"}
    assert json.loads(one(conn, "SELECT value FROM settings WHERE key = 'kind_order'")["value"]) == ["Event", "Class"]


def test_migration_6_rereads_waiting_events_fixes_unacceptable_suggestions_and_clears_the_plan_ahead(
    tmp_path: Path,
) -> None:
    from friday.core.db import MIGRATIONS

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("00[1-5]_*.sql")):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 5")
    item = add_item(old)
    old.executescript(
        f"""
        INSERT INTO sources (id, kind, name, config)
        VALUES (1, 'gcal', 'Personal', '{{}}'), (2, 'gmail', 'Gmail', '{{}}');
        INSERT INTO raw_inputs (id, source_id, external_id, received_utc, content_hash, content)
        VALUES (1, 1, 'bday', 'x', 'h', 'c'), (2, 2, 'm1', 'x', 'h', 'c');
        INSERT INTO suggestions (id, raw_input_id, batch, command, input, quotes, created_utc) VALUES
            (1, 1, 'repeat:bday', 'add', '{{"title": "Birthday", "start": "2099-11-03T00:00"}}', '{{}}', 'x'),
            (2, 2, NULL, 'add', '{{"title": "Meet advisor", "preset": "Meeting"}}', '{{}}', 'x'),
            (3, 2, NULL, 'add', '{{"title": "Fix FAFSA", "preset": "Assignment"}}', '{{}}', 'x'),
            (4, 2, NULL, 'add', '{{"title": "A4", "preset": "Assignment", "due": "2020-10-18T23:59"}}', '{{}}', 'x');
        INSERT INTO plans (id, created_utc, generation, reason, status, stage_values, solve_seconds, report)
        VALUES (1, 'x', 1, 'x', 'current', '{{}}', 0, '{{}}');
        INSERT INTO blocks (plan_id, item_id, start_utc, end_utc, cost) VALUES
            (1, {item}, '2020-01-01T10:00Z', '2020-01-01T10:30Z', '{{}}'),
            (1, {item}, '2099-01-01T10:00Z', '2099-01-01T10:30Z', '{{}}');
        """
    )
    old.close()
    conn = connect(path)
    assert schema_version(conn) == 16
    assert one(conn, "SELECT content_hash FROM raw_inputs WHERE id = 1")["content_hash"] == ""
    found = {r["id"]: (r["status"], json.loads(r["input"])) for r in rows(conn, "SELECT * FROM suggestions")}
    assert found[2] == ("pending", {"title": "Meet advisor", "preset": "Errand"})
    assert found[3] == ("pending", {"title": "Fix FAFSA", "preset": "Assignment", "firmness": "none"})
    assert found[4][0] == "superseded"
    assert [b["start_utc"] for b in rows(conn, "SELECT * FROM blocks")] == ["2020-01-01T10:00Z"]
    assert "thread_id" in {c[1] for c in conn.execute("PRAGMA table_info(raw_inputs)")}


def test_migration_7_brings_kept_default_rules_and_keywords_up_to_date_and_clears_the_plan_ahead(
    tmp_path: Path,
) -> None:
    from friday.core.db import MIGRATIONS

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("00[1-6]_*.sql")):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 6")
    item = add_item(old)
    kept = [{"type": "deep_run", "name": "deep_run", "weight": 4, "params": {"threshold": "3h"}},
            {"type": "even_load", "name": "even_load", "weight": 1, "stage": None, "params": {}}]  # fmt: skip
    keywords = ["due", "deadline", "exam", "quiz", "assignment", "submit", "meeting", "invite", "reschedule",
                "cancelled"]  # fmt: skip
    old.execute(
        "INSERT INTO settings (key, value, version, updated_utc) VALUES ('rules', ?, 1, 'x'), ('gmail', ?, 1, 'x')",
        [json.dumps(kept), json.dumps({"enabled": True, "keywords": keywords})],
    )
    old.executescript(
        f"""
        INSERT INTO sources (id, kind, name, config, last_sync_utc) VALUES (1, 'gcal', 'Canvas', '{{}}', 'x');
        INSERT INTO plans (id, created_utc, generation, reason, status, stage_values, solve_seconds, report)
        VALUES (1, 'x', 1, 'x', 'current', '{{}}', 0, '{{}}');
        INSERT INTO blocks (plan_id, item_id, start_utc, end_utc, cost)
        VALUES (1, {item}, '2099-01-01T10:00Z', '2099-01-01T10:30Z', '{{}}');
        """
    )
    old.close()
    conn = connect(path)
    rules = {r["name"]: r for r in json.loads(one(conn, "SELECT value FROM settings WHERE key = 'rules'")["value"])}
    assert list(rules) == ["deep_run", "even_load", "finish_early", "elastic_minimum"]  # the last from migration 8
    assert rules["deep_run"]["scope"] == {"energy": ["deep", "light"]} and rules["even_load"]["stage"] == "preferences"
    assert rules["finish_early"]["scope"] == {"except_preset": ["Exam prep"]}
    gmail = json.loads(one(conn, "SELECT value FROM settings WHERE key = 'gmail'")["value"])
    assert gmail["keywords"][:10] == keywords and "prelim" in gmail["keywords"]
    assert one(conn, "SELECT last_sync_utc FROM sources")["last_sync_utc"] is None
    assert rows(conn, "SELECT * FROM blocks") == []


def test_migration_8_makes_kept_meal_rules_wellbeing_and_leaves_routines_out_of_load(tmp_path: Path) -> None:
    from friday.core.db import MIGRATIONS

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("00[1-7]_*.sql")):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 7")
    kept = [{"type": "elastic_shortfall", "name": "elastic_shortfall", "stage": None, "params": {}},
            {"type": "daily_load", "name": "daily_load", "scope": None, "params": {}},
            {"type": "reserve", "name": "weekends", "scope": {"area": ["Work"]}, "params": {}}]  # fmt: skip
    old.execute(
        "INSERT INTO settings (key, value, version, updated_utc) VALUES ('rules', ?, 1, 'x')", [json.dumps(kept)]
    )
    old.close()
    conn = connect(path)
    rules = {r["name"]: r for r in json.loads(one(conn, "SELECT value FROM settings WHERE key = 'rules'")["value"])}
    assert rules["elastic_shortfall"]["stage"] is None and rules["elastic_minimum"]["stage"] == "wellbeing"
    assert rules["daily_load"]["scope"] == {"except_preset": ["Routine"]}
    assert rules["weekends"]["scope"] == {"area": ["Work"]}  # one you scoped yourself stays yours
