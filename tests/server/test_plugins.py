"""Rule plugins: a good file registers its rule type, a broken one is named with file:line and skipped, and a rule
whose type never loaded is switched off with a notice."""

from pathlib import Path

from friday.engine.rules import RULE_TYPES
from friday.planner.service import replan
from friday.server.plugins import load_plugins
from tests.commands.helpers import new_app

GOOD = """
from friday.engine.rules import Rule, rule_type


@rule_type("plugin_example")
class Example(Rule):
    pass
"""
BROKEN = "x = 1\nraise ValueError('nope')\n"


def test_a_good_plugin_registers_and_a_broken_one_is_named(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text(GOOD)
    (tmp_path / "broken.py").write_text(BROKEN)
    assert load_plugins(tmp_path) == [f"{tmp_path / 'broken.py'}:2: ValueError: nope"]
    assert "plugin_example" in RULE_TYPES


def test_a_rule_of_an_unknown_type_is_off_with_a_notice(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=3)
    app.do("settings_set", key="rules", value=[{"type": "not_loaded", "name": "mine"}])
    app.do("add", text="essay ~1h")
    replan(app.conn, app.now_utc)
    assert "Rule mine is off: no rule type 'not_loaded' is loaded" in app.do("status")["notices"]
