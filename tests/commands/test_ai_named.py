"""The AI you chose, by its name (3 Nov: "for non-claude systems, does it still say ask claude?"). When Friday refuses
what the AI proposed, it says which AI: "Friday doesn't let Gemini run 'undo' here", "The AI may not change the
'server' setting", never "Claude" for an AI that isn't Claude."""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from friday.commands.claude import proposals
from friday.ingest import llm
from tests.commands.helpers import App, new_app

REPO = Path(__file__).resolve().parents[2]
REFUSED = [
    {"sentence": "Undo everything", "command": "undo", "input": {}},
    {"sentence": "Change the port", "command": "settings_set", "input": {"key": "server", "value": {}}},
]


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


class TestGlassBox:
    @pytest.mark.parametrize(
        ("provider", "said"),
        [("claude", "Claude"), ("openai", "GPT"), ("gemini", "Gemini"), ("grok", "Grok"), ("muse", "Muse"),
         ("compatible", "the AI"), ("local", "the AI")],
    )  # fmt: skip
    def test_each_provider_is_said_by_its_name_and_an_unnamed_one_as_the_ai(self, provider: str, said: str) -> None:
        assert llm.spoken(SimpleNamespace(provider=provider)) == said

    def test_no_settings_is_the_default_claude(self) -> None:
        assert llm.spoken() == llm.spoken(None) == "Claude"

    def test_every_provider_has_a_way_to_be_said(self) -> None:
        for provider in llm.NAMES:
            assert llm.spoken(SimpleNamespace(provider=provider))

    def test_refusals_name_the_ai_given_and_start_a_sentence_with_a_capital(self) -> None:
        errors = [a.error for a in proposals({"actions": REFUSED}, ("settings_set",), ai="the AI").actions]
        assert errors == ["Friday doesn't let the AI run 'undo' here", "The AI may not change the 'server' setting"]

    def test_left_out_it_is_claude_as_before(self) -> None:
        (first, _) = proposals({"actions": REFUSED}, ("settings_set",)).actions
        assert first.error == "Friday doesn't let Claude run 'undo' here"

    def test_the_web_app_says_it_the_same_way(self) -> None:
        web = (REPO / "web/src/lib/aiName.ts").read_text()
        assert re.search(r'name === "AI" \? "the AI" : name', web)


class Model:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer, self.messages = answer, self

    def create(self, **_: Any) -> Any:
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.answer))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=10),
        )


class TestBlackBox:
    @pytest.mark.parametrize(("provider", "said"), [("gemini", "Gemini"), ("openai", "GPT"), ("compatible", "the AI")])
    def test_a_refused_proposal_names_the_ai_you_chose_never_claude(
        self, app: App, monkeypatch: pytest.MonkeyPatch, provider: str, said: str
    ) -> None:
        app.do("settings_set", key="llm", value={"provider": provider, "base_url": "http://127.0.0.1:9/v1"})
        monkeypatch.setattr(llm, "client", lambda *_: Model({"reply": "", "actions": REFUSED}))
        errors = [a["error"] for a in app.do("ask_claude", text="anything")["actions"]]
        assert errors[0] == f"Friday doesn't let {said} run 'undo' here"
        assert errors[1] == f"{said[0].upper()}{said[1:]} may not change the 'server' setting"
        assert not any("Claude" in e for e in errors)

    def test_with_claude_it_still_says_claude(self, app: App, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(llm, "client", lambda *_: Model({"reply": "", "actions": REFUSED}))
        assert app.do("ask_claude", text="x")["actions"][0]["error"] == "Friday doesn't let Claude run 'undo' here"

    def test_what_the_app_is_told_to_call_it_matches(self, app: App) -> None:
        app.do("settings_set", key="llm", value={"provider": "gemini"})
        assert app.do("inbox")["llm"]["name"] == "Gemini"
