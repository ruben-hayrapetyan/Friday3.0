"""`friday.toml` (DESIGN §22.9): applied whole or not at all, logged as `config`, and its keys read-only elsewhere."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.server.config import apply_config
from tests.commands.helpers import App, new_app

TOML = """
[llm]
model = "claude-haiku-5-5"
daily_calls = 20

[[sources]]
name = "Canvas"
url = "https://example.edu/feed.ics"
trusted = true
"""


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_the_file_is_applied_as_config_and_its_keys_are_read_only_in_the_app(app: App, tmp_path: Path) -> None:
    path = tmp_path / "friday.toml"
    path.write_text(TOML)
    assert apply_config(app.conn, app.now_utc, path) == ["llm", "sources"]
    assert app.do("settings")["llm"]["model"] == "claude-haiku-5-5"
    assert {r["actor"] for r in app.table("command_log") if r["command"] == "settings_set"} >= {"config"}
    assert app.do("status")["config_keys"] == ["llm", "sources"]
    with pytest.raises(FieldError, match="set in friday.toml"):
        app.do("settings_set", key="llm", value={"daily_calls": 5})
    assert apply_config(app.conn, app.now_utc, path) == []  # unchanged: nothing written again
    sync(app.conn, app.now_utc, fetch=lambda url: "BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    assert [(s["name"], s["trusted"]) for s in app.do("inbox")["sources"]] == [("Canvas", True)]


def test_a_bad_file_changes_nothing_and_says_why(app: App, tmp_path: Path) -> None:
    path = tmp_path / "friday.toml"
    path.write_text('[llm]\ndaily_calls = "many"\n')
    assert apply_config(app.conn, app.now_utc, path) == []
    problems = app.do("status")["problems"]
    assert any("settings file isn't used until it's fixed" in p and "friday.toml" in p for p in problems)
    assert app.do("settings")["llm"]["daily_calls"] == 50


def test_removing_the_file_hands_its_keys_back_to_the_app(app: App, tmp_path: Path) -> None:
    path = tmp_path / "friday.toml"
    path.write_text(TOML)
    apply_config(app.conn, app.now_utc, path)
    path.unlink()
    apply_config(app.conn, app.now_utc, path)
    app.do("settings_set", key="llm", value={"daily_calls": 5})
    assert app.do("settings")["llm"]["daily_calls"] == 5


def test_the_example_config_is_valid(app: App, tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "friday.example.toml"
    assert apply_config(app.conn, app.now_utc, example) != []
    assert not any("friday.toml" in p for p in app.do("status")["problems"])
