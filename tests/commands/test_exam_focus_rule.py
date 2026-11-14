"""Exam focus is a rule (14 Nov: a client set "start studying for an exam 5 days before" and found it nowhere in Rules;
"this kind of thing should always be a rule and shouldn't be stored in another way"): read from words, listed and
edited in Rules like any other, what the planner and Projects read, and a saved setting migrated into it."""

import json
import sqlite3
from pathlib import Path

import pytest

from friday.core.db import MIGRATIONS, connect, one
from friday.core.settings import DEFAULTS, REFERENCE_RULES, exam_focus_of, import_toml, to_json, validate_value
from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app

NAME = "you:exam-focus"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 October, 09:00


def prelim(app: App, day: str = "2026-10-23") -> None:
    app.do("add", title="MATH 2940 Prelim 2", preset="Exam", start=f"{day}T19:30", end=f"{day}T21:00")


def focus_rule(app: App) -> dict | None:
    return next((r for r in app.do("rules") if r["type"] == "exam_focus"), None)


def test_it_isnt_a_setting_any_more() -> None:
    assert "exam_focus" not in DEFAULTS
    with pytest.raises(ValueError, match="no such settings key"):
        validate_value("exam_focus", {"on": True, "days_before": 3})


def test_typed_words_read_as_the_rule(app: App) -> None:
    read = app.do("rule_read", text="focus on exams 5 days before")
    assert read["reading"]["kind"] == "exam_focus" and read["reading"]["amount"] == 5
    assert read["sentence"] == "Focus on an exam's course 5 days before it"
    assert "other courses' work due after the exam waits" in read["effect"]
    app.do("rule_add", text="focus on exams 5 days before")
    rule = focus_rule(app)
    assert rule and (rule["name"], rule["source"], rule["strength"]) == (NAME, "you", "Always")
    assert (rule["sentence"], rule["words"]) == (
        "Focus on an exam's course 5 days before it",
        "focus on exams 5 days before",
    )


def test_there_is_one_exam_focus_a_new_one_takes_its_place(app: App) -> None:
    app.do("rule_add", text="focus on exams 5 days before")
    at = [r["name"] for r in app.do("rules")].index(NAME)
    app.do("rule_add", text="the 2 days before a final are only for that class")
    rules = [r for r in app.do("rules") if r["type"] == "exam_focus"]
    assert len(rules) == 1 and rules[0]["sentence"] == "Focus on an exam's course 2 days before it"
    assert [r["name"] for r in app.do("rules")].index(NAME) == at


def test_editing_its_days_changes_planning(app: App) -> None:
    prelim(app)  # Friday 7:30pm
    app.do("rule_add", text="focus on exams 2 days before")
    assert app.do("exams")[0]["focus_from"] == "2026-10-21T19:30"
    essay = app.do("add", title="HIST 1200 essay", preset="Assignment", due="2026-10-26T12:00", duration_min=60)
    key = f"item:{essay['item']['id']}"
    before = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items[key].release_utc
    assert before in (None, app.now_utc)  # the exam is more than 2 days off: nothing waits yet
    app.do("rule_edit", name=NAME, overrides={"amount": 5})
    assert focus_rule(app)["sentence"] == "Focus on an exam's course 5 days before it"
    assert app.do("exams")[0]["focus_from"] == "2026-10-18T19:30"
    after = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items[key].release_utc
    assert after is not None and after > app.now_utc  # now it waits until the exam is over
    app.do("rule_set", name=NAME, enabled=False)  # its switch is the old on and off
    assert app.do("exams")[0]["focus_from"] is None
    assert not exam_focus_of(take_snapshot(app.conn, app.now_utc).settings).on


def at_version(path: Path, version: int) -> sqlite3.Connection:
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("0[0-9][0-9]_*.sql") if int(p.name[:3]) <= version):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute(f"PRAGMA user_version = {version}")
    return old


def migrated(tmp_path: Path, settings: dict[str, object], kv: dict[str, object] | None = None) -> sqlite3.Connection:
    path = tmp_path / "old.db"
    old = at_version(path, 34)
    for key, value in settings.items():
        old.execute("INSERT INTO settings (key, value, version, updated_utc) VALUES (?, ?, 3, 'x')",
                    [key, json.dumps(value)])  # fmt: skip
    for key, value in (kv or {}).items():
        old.execute("INSERT INTO kv (key, value) VALUES (?, ?)", [key, json.dumps(value)])
    old.close()
    return connect(path)


def saved(conn: sqlite3.Connection, key: str) -> object:
    found = one(conn, "SELECT value FROM settings WHERE key = ?", [key])
    return json.loads(found["value"]) if found else None


def test_migration_35_makes_a_saved_exam_focus_the_rule_after_the_built_in_ones(tmp_path: Path) -> None:
    conn = migrated(tmp_path, {"exam_focus": {"on": True, "days_before": 5, "words": ["exam", "quiz"]}})
    rules = saved(conn, "rules")
    assert rules[:-1] == to_json("rules", REFERENCE_RULES)  # the built-in rules, as they are now
    assert rules[-1] == {"type": "exam_focus", "name": NAME, "weight": 0.0, "stage": None, "scope": None,
                         "reason": "Focus on an exam's course 5 days before it",
                         "params": {"days_before": 5, "words": ["exam", "quiz"]}, "enabled": True}  # fmt: skip
    assert saved(conn, "exam_focus") is None
    readings = json.loads(one(conn, "SELECT value FROM kv WHERE key = 'rule_readings'")["value"])
    assert readings[NAME]["reading"]["kind"] == "exam_focus" and readings[NAME]["reading"]["amount"] == 5
    assert readings[NAME]["strength"] == "Always"
    version = one(conn, "SELECT version FROM settings WHERE key = 'rules'")["version"]
    assert version > 3  # newer than every setting before it
    app = App(conn, 0)
    assert exam_focus_of(take_snapshot(conn, 0).settings).days_before == 5
    assert app.do("rules")[-1]["sentence"] == "Focus on an exam's course 5 days before it"


def test_migration_35_adds_it_to_your_rules_and_keeps_your_readings(tmp_path: Path) -> None:
    mine = [{"type": "deep_run", "name": "deep_run", "params": {"threshold": "2h"}},
            {"type": "time_preference", "name": "you:no-work-after-10pm", "reason": "No work after 10pm"}]  # fmt: skip
    kept = {
        "you:no-work-after-10pm": {"reading": {"kind": "window"}, "strength": "Prefer", "text": "no work after 10pm"}
    }
    conn = migrated(tmp_path, {"rules": mine, "exam_focus": {"on": True, "days_before": 1}}, {"rule_readings": kept})
    rules = saved(conn, "rules")
    assert [r["name"] for r in rules] == ["deep_run", "you:no-work-after-10pm", NAME]
    assert rules[-1]["reason"] == "Focus on an exam's course the day before it"
    readings = json.loads(one(conn, "SELECT value FROM kv WHERE key = 'rule_readings'")["value"])
    assert set(readings) == {"you:no-work-after-10pm", NAME}


def test_migration_35_drops_an_exam_focus_that_was_off(tmp_path: Path) -> None:
    conn = migrated(tmp_path, {"exam_focus": {"on": False, "days_before": 4}})
    assert saved(conn, "exam_focus") is None and saved(conn, "rules") is None  # the built-in rules, unsaved


def test_a_config_file_with_the_old_setting_reads_as_the_rule() -> None:
    values = import_toml("[exam_focus]\non = true\ndays_before = 4\n")
    assert exam_focus_of(values).days_before == 4
    assert [r.name for r in values["rules"]][-1] == NAME
    assert not exam_focus_of(import_toml("[exam_focus]\non = false\n")).on
