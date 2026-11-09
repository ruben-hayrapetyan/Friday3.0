"""The audit, 8 Nov: what a page elsewhere in your browser, or an assistant's token, could make Friday do. A read a
browser says another site asked for is refused; your AI key goes only where you saved; an assistant never runs what's
yours alone, nor undoes it; a preview of what can't be rolled back is refused, not done; a day that doesn't exist is
said, not a crash."""

from pathlib import Path

import pytest

from friday.commands.registry import YOURS_ONLY
from friday.core.items import FieldError
from friday.ingest import llm
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_an_assistant_never_runs_what_is_yours(app: App) -> None:
    app.actor = "mcp:claude"
    for name, payload in [("token_add", {"name": "x"}), ("ai_key_set", {"provider": "openai", "key": "k"}),
                          ("gmail_app_set", {"address": "a@gmail.com", "password": "abcdefghijklmnop"}),
                          ("settings_set", {"key": "llm", "value": {"provider": "openai", "base_url": "https://x"}}),
                          ("settings_set", {"key": "webhooks", "value": {}}),
                          ("settings_set", {"key": "phone", "value": {"on": True}})]:  # fmt: skip
        with pytest.raises(FieldError, match="Only you"):
            app.do(name, **payload)
    assert {"token_add", "ai_models", "phone_set"} <= YOURS_ONLY


def test_an_assistant_cant_undo_what_is_yours(app: App) -> None:
    mine = app.full("settings_set", payload={"key": "phone", "value": {"on": False}}, provisional=False)
    app.actor = "mcp:claude"
    with pytest.raises(FieldError, match="undoing settings_set"):
        app.do("undo", command_id=mine.command_id)
    app.do("settings_set", key="daily_cap", value=app.do("settings")["daily_cap"])  # the rest is still its to change


def test_a_preview_of_what_cant_be_rolled_back_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="can't be previewed"):
        app.full("token_add", payload={"name": "trial"}, preview=True)
    assert app.do("tokens") == []


def test_your_ai_key_goes_only_where_you_saved(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(llm, "models_of", lambda chosen: sent.append(chosen.base_url) or ["m"])
    out = app.do("ai_models", provider="openai", base_url="https://evil.example/steal")
    assert sent == [] and "Save this address first" in out["error"]
    app.do("settings_set", key="llm", value={"provider": "compatible", "base_url": "https://mine.example/v1"})
    assert app.do("ai_models", provider="compatible", base_url="https://mine.example/v1")["models"] == ["m"]


@pytest.mark.parametrize("day", ["2026-13-45", "2026-02-30"])
def test_a_day_that_doesnt_exist_is_said(app: App, day: str) -> None:
    with pytest.raises(ValueError, match="isn't a day"):
        app.do("week_review", date=day)


def test_an_add_with_nothing_in_it_is_said(app: App) -> None:
    with pytest.raises(FieldError, match="give it a title"):
        app.do("add")


def test_a_read_another_site_asked_for_is_refused(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path)
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as mac:
        assert mac.get("/api/q/status", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        assert mac.get("/api/q/status", headers={"sec-fetch-site": "same-origin"}).status_code == 200
        assert mac.get("/api/q/status").status_code == 200  # the CLI and scripts send no such header
