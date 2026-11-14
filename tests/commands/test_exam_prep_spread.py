"""Exam prep spread over the days before its exam, by default again (14 Nov: "bring spread back in but its just very
confusing when you tell users about spread as a backend feature"): a built-in rule said as what it does to the week,
"Exam prep is spread over the days before the exam, not crammed into one", switched off or made stronger like the
other built-ins; never a field on tasks. Everyone gets it where the old built-in stood (migration 036), off for
anyone who had switched the old one off."""

import json
import sqlite3
from pathlib import Path

import pytest

from friday.core.db import MIGRATIONS, connect, one
from friday.core.settings import DEFAULTS
from friday.planner.service import replan
from tests.commands.helpers import App, new_app

NAME = "exam_prep_spread"
SAID = "Exam prep is spread over the days before the exam, not crammed into one"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 October, 09:00


def find(app: App, name: str) -> dict:
    return next(r for r in app.do("rules") if r["name"] == name)


def test_it_is_built_in_where_the_old_spread_rule_stood() -> None:
    names = [r.name for r in DEFAULTS["rules"]]
    assert names[names.index("buffer") + 1] == NAME
    rule = next(r for r in DEFAULTS["rules"] if r.name == NAME)
    assert (rule.type, rule.scope, rule.weight) == ("spread", {"preset": ["Exam prep"]}, 3.0)
    assert not {"spread", "cluster"} & set(names)  # not the old rules for "marked" work


def test_rules_says_what_it_does_to_the_week(app: App) -> None:
    rule = find(app, NAME)
    assert rule["sentence"] == SAID
    assert (rule["source"], rule["strength"], rule["editable"], rule["background"]) == (
        "default",
        "Prefer",
        True,
        False,
    )
    assert all("marked spread" not in r["sentence"] for r in app.do("rules"))


def prep_days(app: App) -> set[str]:
    app.do("add", title="CHEM Prelim", preset="Exam", start="2026-10-23T19:30", end="2026-10-23T21:00")
    prep = app.do("add", title="Prep: CHEM Prelim", preset="Exam prep", due="2026-10-23T19:30", duration_min=240)
    replan(app.conn, app.now_utc)
    return {b["start"][:10] for b in app.do("item", id=prep["item"]["id"])["blocks"]}


def test_exam_prep_is_spread_over_the_days_before_its_exam(app: App) -> None:
    days = prep_days(app)
    assert len(days) >= 3 and max(days) <= "2026-10-23"


def test_switched_off_it_is_not(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("rule_set", name=NAME, enabled=False)
    assert find(app, NAME)["enabled"] is False
    assert len(prep_days(app)) <= 2


def test_its_strength_changes_and_its_words_stay(app: App) -> None:
    app.do("rule_edit", name=NAME, strength="Strongly")
    assert (find(app, NAME)["strength"], find(app, NAME)["sentence"]) == ("Strongly", SAID)


def at_version(path: Path, version: int) -> sqlite3.Connection:
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("0[0-9][0-9]_*.sql") if int(p.name[:3]) <= version):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute(f"PRAGMA user_version = {version}")
    return old


OLD = [{"type": "chunk_cost", "name": "chunk_cost"}, {"type": "buffer", "name": "buffer"},
       {"type": "spread", "name": "spread", "weight": 3}, {"type": "cluster", "name": "cluster"},
       {"type": "same_course", "name": "same_course"}]  # fmt: skip


def migrated(tmp_path: Path, rules: list[dict] | None, logged: list[list[dict]] = ()) -> sqlite3.Connection:  # type: ignore[assignment]
    """A database at 35 with these rules saved (034 has taken the old two out), and rules writes logged before."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "old.db"
    old = at_version(path, 35)
    if rules is not None:
        old.execute("INSERT INTO settings (key, value, version, updated_utc) VALUES ('rules', ?, 1, 'x')",
                    [json.dumps(rules)])  # fmt: skip
    for value in logged:
        change = {"op": "update", "table": "settings", "key": {"user_id": 1, "key": "rules"},
                  "before": None, "after": {"user_id": 1, "key": "rules", "value": json.dumps(value)}}  # fmt: skip
        old.execute("INSERT INTO command_log (at_utc, actor, command, input, result, undo) "
                    "VALUES ('x', 'you', 'rule_set', '{}', '{}', ?)", [json.dumps([change])])  # fmt: skip
    old.close()
    return connect(path)


def saved(conn: sqlite3.Connection) -> list[dict] | None:
    found = one(conn, "SELECT value FROM settings WHERE key = 'rules'")
    return json.loads(found["value"]) if found else None


def after_034(rules: list[dict]) -> list[dict]:
    return [r for r in rules if r["name"] not in ("spread", "cluster")]


def test_migration_36_gives_saved_rules_the_new_one_where_the_old_one_stood(tmp_path: Path) -> None:
    conn = migrated(tmp_path, after_034(OLD))
    rules = saved(conn)
    assert [r["name"] for r in rules] == ["chunk_cost", "buffer", NAME, "same_course"]
    new = rules[2]
    assert (new["type"], new["scope"], new["enabled"]) == ("spread", {"preset": ["Exam prep"]}, True)
    app = App(conn, 0)
    assert find(app, NAME)["sentence"] == SAID


def test_migration_36_leaves_the_new_one_off_for_anyone_who_had_the_old_one_off(tmp_path: Path) -> None:
    off = [r | {"enabled": False} if r["name"] == "spread" else r for r in OLD]
    later = after_034(off) + [{"type": "time_preference", "name": "you:no-work-after-10pm"}]
    conn = migrated(tmp_path, later, logged=[OLD, off, later])  # its last write with the old rule had it off
    assert next(r for r in saved(conn) if r["name"] == NAME)["enabled"] is False
    back_on = migrated(tmp_path / "b", after_034(OLD), logged=[off, OLD])  # switched off, then on again
    assert next(r for r in saved(back_on) if r["name"] == NAME)["enabled"] is True


def test_migration_36_adds_it_once_and_leaves_unsaved_rules_to_the_defaults(tmp_path: Path) -> None:
    mine = after_034(OLD)
    mine.insert(2, {"type": "spread", "name": NAME, "enabled": False})
    assert [r["name"] for r in saved(migrated(tmp_path, mine))].count(NAME) == 1
    assert saved(migrated(tmp_path / "b", None)) is None
    no_buffer = [{"type": "deep_run", "name": "deep_run"}]  # buffer deleted: it goes at the end
    assert [r["name"] for r in saved(migrated(tmp_path / "c", no_buffer))] == ["deep_run", NAME]
