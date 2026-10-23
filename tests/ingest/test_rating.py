"""How much each event needs attending, rated by the AI with the title as a fallback (COMBINED.md 56)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from friday.commands.rating import rate_upcoming
from friday.ingest import llm
from friday.ingest.rating import rate
from tests.commands.helpers import new_app


class Answering:
    def __init__(self, text: str) -> None:
        self.text, self.asked = text, []
        self.messages = self

    def create(self, **request: Any) -> Any:
        self.asked.append(request)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


def test_the_ai_s_rating_wins_and_what_it_leaves_out_falls_back() -> None:
    ai = Answering(json.dumps({"events": [{"title": "Robotics", "level": "required", "reason": "the team needs you"}]}))
    out = rate(["Robotics", "Poker night"], ai, "claude-haiku-5-5")
    assert out["robotics"] == {"level": "required", "reason": "the team needs you"}
    assert out["poker night"]["level"] == "optional"  # left out by the AI: from its title
    assert ai.asked[0]["model"] == "claude-haiku-5-5"


@pytest.mark.parametrize("text", ["not json", json.dumps({"events": [{"title": "Robotics", "level": "maybe"}]}), ""])
def test_a_bad_answer_falls_back_to_the_titles(text: str) -> None:
    assert rate(["Robotics"], Answering(text), "m")["robotics"]["level"] == "likely"


def test_no_ai_means_the_titles_decide() -> None:
    assert rate(["CS 2110 Lecture"], None, "m")["cs 2110 lecture"]["level"] == "required"


def test_upcoming_events_are_rated_once(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("add", title="Poker night", when="fixed", start="2026-10-20T19:00", end="2026-10-20T23:00")
    app.do("add", title="Poker night", when="fixed", start="2026-10-27T19:00", end="2026-10-27T23:00")
    app.do("add", title="Old talk", when="fixed", start="2026-10-10T19:00", end="2026-10-10T20:00")
    ai = Answering(json.dumps({"events": [{"title": "Poker night", "level": "optional", "reason": "a game"}]}))
    assert rate_upcoming(app.conn, app.now_utc, client=ai) == 1  # one title; the past one isn't asked about
    assert rate_upcoming(app.conn, app.now_utc, client=ai) == 0 and len(ai.asked) == 1


def test_the_command_comes_first_then_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "cli_path", lambda: Path("/bin/claude"))
    monkeypatch.setattr(llm, "api_key", lambda: None)
    assert isinstance(llm.client(), llm.Routed) and llm.client().api is None
    monkeypatch.setattr(llm, "cli_path", lambda: None)
    assert llm.client() is None
    monkeypatch.setattr(llm, "api_key", lambda: "sk-test")
    assert not isinstance(llm.client(), llm.Routed)
