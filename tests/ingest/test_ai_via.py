"""Ask through the command or through an API key (C95, 10 Nov: "right now it is very hard/impossible for friday users to
input an api key for an ai that is using the cli. the user should have the choice between cli commands or api key for
ai's that have both"). Claude, OpenAI and Gemini: `via` "command" (the default) asks the command first with the key
behind it, as before; "key" asks through the key alone, the command left alone. Fakes only: nothing real is asked."""

from pathlib import Path

import anthropic
import pytest

from friday.core.integrations import LlmSettings
from friday.ingest import llm
from tests.commands.helpers import App, new_app


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Claude Code, codex and agy all on this Mac."""
    monkeypatch.setattr(llm, "cli_path", lambda: Path("/opt/homebrew/bin/claude"))
    monkeypatch.setattr(llm, "codex_path", lambda: Path("/opt/homebrew/bin/codex"))
    monkeypatch.setattr(llm, "gemini_path", lambda: Path("/opt/homebrew/bin/agy"))


# Glass box: which client asks


def test_by_default_the_command_asks_first_with_the_key_behind_it(installed: None, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    asked = llm.client(LlmSettings())
    assert isinstance(asked, llm.Routed) and isinstance(asked.cli, llm.CliClient)
    assert isinstance(asked.api, anthropic.Anthropic)


def test_with_the_key_chosen_claude_is_asked_through_the_key_alone(installed: None, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    asked = llm.client(LlmSettings(via="key"))
    assert isinstance(asked, anthropic.Anthropic) and not isinstance(asked, llm.Routed)


@pytest.mark.parametrize(("provider", "variable"), [("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")])
def test_with_the_key_chosen_openai_and_gemini_skip_their_command(
    installed: None, monkeypatch: pytest.MonkeyPatch, provider: str, variable: str
) -> None:
    monkeypatch.setenv(variable, "test-key")
    model = {"model": "gemini-2.5-pro"} if provider == "gemini" else {}  # Gemini's is chosen from its list
    asked = llm.client(LlmSettings(provider=provider, via="key", **model))
    assert isinstance(asked, llm.OpenAIClient)
    assert isinstance(llm.client(LlmSettings(provider=provider, **model)), llm.Routed)  # the command first by default


def test_with_the_key_chosen_and_none_saved_nothing_is_asked_and_it_says_so(installed: None) -> None:
    settings = LlmSettings(via="key")
    assert llm.client(settings) is None
    said = llm.describe(settings)
    assert said["ready"] is False and said["via"] == "key" and said["cli"] is True and said["command"] == "claude"
    assert said["why"] == "No Anthropic API key: add one in Settings → Integrations → AI"


def test_the_command_chosen_needs_no_key(installed: None) -> None:
    said = llm.describe(LlmSettings())
    assert said["ready"] is True and said["via"] == "command" and said["key"] is False


def test_only_command_or_key_is_a_choice() -> None:
    assert LlmSettings().via == "command"
    with pytest.raises(ValueError, match="via"):
        LlmSettings(via="both")  # type: ignore[arg-type]


# Black box: through the app's commands


def test_choosing_the_key_in_settings_keeps_the_ai_and_its_models_and_shows_in_the_inbox(
    tmp_path: Path, installed: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    app: App = new_app(tmp_path)
    before = app.do("settings")["llm"]
    app.do("settings_set", key="llm", value={"via": "key"})
    after = app.do("settings")["llm"]
    assert after["via"] == "key" and {k: after[k] for k in ("provider", "model")} == {
        k: before[k] for k in ("provider", "model")
    }
    seen = app.do("inbox")["llm"]
    assert seen["via"] == "key" and seen["ready"] is False  # no key saved yet
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert app.do("inbox")["llm"]["ready"] is True
    app.do("settings_set", key="llm", value={"via": "command"})
    assert app.do("inbox")["llm"]["via"] == "command"
