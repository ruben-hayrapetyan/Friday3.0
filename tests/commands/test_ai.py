"""Checking the AI: each model answers the way Friday asks, or says why not."""

from pathlib import Path

import pytest

from friday.ingest import llm
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_each_model_is_asked_the_way_friday_asks(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient({"ok": True})
    monkeypatch.setattr(llm, "client", lambda *_: client)
    checks = app.do("ai_check")
    assert [(c["model"], c["ok"]) for c in checks] == [("claude-sonnet-5-5", True), ("claude-haiku-5-5", True)]
    assert all("output_config" in call for call in client.calls)


def test_a_refusal_is_said_in_full(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    class Refusing(FakeClient):
        def create(self, **request: object) -> object:
            raise ValueError("tool_choice is not supported for this model")

    monkeypatch.setattr(llm, "client", lambda *_: Refusing({}))
    assert all("not supported" in c["said"] and not c["ok"] for c in app.do("ai_check"))
    monkeypatch.setattr(llm, "client", lambda *_: None)
    assert all("an Anthropic API key" in c["said"] and "Settings" in c["said"] for c in app.do("ai_check"))
