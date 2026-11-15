"""The Rules lab is gone (15 Nov, the user: "i don't think we need a rules lab"): no setting for it, and the value a
switch saved before goes with migration 40, so reading settings doesn't refuse a key it no longer knows."""

import sqlite3
from pathlib import Path

import pytest

from friday.core.db import MIGRATIONS, connect
from friday.core.settings import DEFAULTS, validate_value
from friday.planner.store import load_settings


def test_there_is_no_rules_lab_setting() -> None:
    assert "rules_lab" not in DEFAULTS
    with pytest.raises(ValueError, match="rules_lab: no such settings key"):
        validate_value("rules_lab", True)


def test_a_saved_switch_goes_and_settings_still_load(tmp_path: Path) -> None:
    path = tmp_path / "friday.db"
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("0[0-9][0-9]_*.sql") if int(p.name[:3]) <= 39):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute("PRAGMA user_version = 39")
    old.execute(
        "INSERT INTO settings (user_id, key, value, version, updated_utc) VALUES (1, 'rules_lab', 'true', 1, 'x')"
    )
    old.execute(
        "INSERT INTO settings (user_id, key, value, version, updated_utc) VALUES (1, 'school', 'false', 2, 'x')"
    )
    old.close()
    conn = connect(path)
    assert [r[0] for r in conn.execute("SELECT key FROM settings")] == ["school"]
    assert load_settings(conn)["school"] is False  # the rest stays
