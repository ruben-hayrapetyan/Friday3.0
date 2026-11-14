"""Tasks aren't marked spread or clustered (14 Nov: "Tasks are not marked as spread and i don't know where you would
find this distinction ... the user can add this as a separate rule if they would like"): the facet, its column and the
two built-in rules for marked work are gone, and saying it as a rule spreads, or keeps together, the work it names."""

import dataclasses
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from friday.api.commands import AddInput
from friday.api.types import ItemFields
from friday.core.db import MIGRATIONS, connect, one
from friday.core.items import Item
from friday.core.presets import DEFAULT_PRESETS, Preset
from friday.core.settings import DEFAULTS
from friday.engine.problem import EngineItem
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app
from tests.core.test_db import add_item


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_no_task_kind_or_api_has_spread() -> None:
    assert "spread" not in {f.name for f in dataclasses.fields(Item)}
    assert "spread" not in {f.name for f in dataclasses.fields(EngineItem)}
    assert "spread" not in ItemFields.model_fields and "spread" not in Preset.model_fields
    assert all("spread" not in p.model_dump(exclude_none=True) for p in DEFAULT_PRESETS.values())
    with pytest.raises(ValidationError):
        AddInput.model_validate({"title": "Essay", "spread": "spread"})


def test_the_built_in_rules_for_marked_work_are_gone(app: App) -> None:
    names = {r.name for r in DEFAULTS["rules"]}
    assert not names & {"spread", "cluster"}
    said = [r["sentence"] for r in app.do("rules")]
    assert "Spread out what you marked spread" not in said and "Keep clustered work on few days" not in said


def test_a_kind_saved_with_spread_still_reads() -> None:
    assert Preset.model_validate({"when": "window", "spread": "cluster", "firmness": "hard"}) == Preset(
        when="window", firmness="hard"
    )


def test_saying_it_as_a_rule_reads_and_scopes_it(app: App) -> None:
    read = app.do("rule_read", text="spread my essays over several days")
    assert (read["reading"]["kind"], read["sentence"]) == ("spread", "Spread essays over several days")
    assert "a share a day" in read["effect"]
    kept = app.do("rule_read", text="keep problem sets on few days")
    assert (kept["reading"]["kind"], kept["sentence"]) == ("cluster", "Keep problem sets on as few days as possible")
    app.do("rule_add", text="spread my essays over several days")
    app.do("rule_add", text="keep problem sets on few days")
    saved = take_snapshot(app.conn, app.now_utc).settings["rules"]
    rules = {r.type: r for r in saved if r.name.startswith("you:")}
    assert rules["spread"].scope == {"title": ["essays", "essay"]}
    assert rules["cluster"].scope and "title_regex" in rules["cluster"].scope


def plan_days(folder: Path, rule: str | None) -> set[str]:
    folder.mkdir()
    app = new_app(folder)
    essay = app.do("add", text="history essay ~6h due fri 17:00")["item"]["id"]
    app.do("add", text="math problem set ~3h due thu 17:00")
    if rule:
        app.do("rule_add", text=rule, strength="Strongly")
    replan(app.conn, app.now_utc)
    return {b["start"][:10] for b in app.do("item", id=essay)["blocks"]}


def test_a_spread_rule_spreads_the_work_it_names(tmp_path: Path) -> None:
    assert len(plan_days(tmp_path / "a", "spread my essays over several days")) >= 4


def test_a_cluster_rule_keeps_it_on_few_days(tmp_path: Path) -> None:
    assert len(plan_days(tmp_path / "b", "keep essays on as few days as possible")) == 1


def at_version(path: Path, version: int) -> sqlite3.Connection:
    old = sqlite3.connect(path, isolation_level=None)
    for name in sorted(p.name for p in MIGRATIONS.glob("0[0-9][0-9]_*.sql") if int(p.name[:3]) <= version):
        old.executescript((MIGRATIONS / name).read_text())
    old.execute(f"PRAGMA user_version = {version}")
    return old


def test_migration_34_drops_the_column_the_kinds_facet_and_the_two_rules(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    old = at_version(path, 33)
    add_item(old, title="Exam prep", spread="spread")
    presets = {"Project": {"when": "window", "spread": "cluster"}, "Essay": {"when": "window"}}
    rules = [{"type": "deep_run", "name": "deep_run"}, {"type": "spread", "name": "spread", "weight": 3},
             {"type": "time_preference", "name": "you:no-work-after-10pm"},
             {"type": "cluster", "name": "cluster", "params": {"per_day": 2}},
             {"type": "spread", "name": "you:spread-essays", "scope": {"title": ["essays"]}}]  # fmt: skip
    for key, value in (("presets", presets), ("rules", rules)):
        old.execute("INSERT INTO settings (key, value, version, updated_utc) VALUES (?, ?, 1, 'x')",
                    [key, json.dumps(value)])  # fmt: skip
    old.close()
    conn = connect(path)
    assert "spread" not in {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    assert one(conn, "SELECT title FROM items")["title"] == "Exam prep"  # the task stays
    kept = json.loads(one(conn, "SELECT value FROM settings WHERE key = 'presets'")["value"])
    assert kept == {"Project": {"when": "window"}, "Essay": {"when": "window"}}  # in their order
    left = json.loads(one(conn, "SELECT value FROM settings WHERE key = 'rules'")["value"])
    assert [r["name"] for r in left] == ["deep_run", "you:no-work-after-10pm", "you:spread-essays"]


def test_a_change_made_before_the_column_went_can_still_be_undone(app: App) -> None:
    out = app.full("add", payload={"text": "essay ~2h due fri"}, provisional=False)
    logged = one(app.conn, "SELECT undo FROM command_log WHERE id = ?", [out.command_id])
    changes = json.loads(logged["undo"])
    for change in changes:  # as it was logged while items had the column
        if change["table"] == "items":
            change["after"] = change["after"] | {"spread": "none"}
    app.conn.execute("UPDATE command_log SET undo = ? WHERE id = ?", [json.dumps(changes), out.command_id])
    app.do("undo", command_id=out.command_id)
    assert app.do("items") == [] or all(i["title"] != "essay" for i in app.do("items"))
