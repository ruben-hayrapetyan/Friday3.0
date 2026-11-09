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
    monkeypatch.setattr(llm, "api_key", lambda *_: None)
    assert isinstance(llm.client(), llm.Routed) and llm.client().api is None
    monkeypatch.setattr(llm, "cli_path", lambda: None)
    assert llm.client() is None
    monkeypatch.setattr(llm, "api_key", lambda *_: "sk-test")
    assert not isinstance(llm.client(), llm.Routed)


def test_a_rating_only_guessed_from_the_title_is_asked_again_once_a_day(tmp_path: Path) -> None:
    # Every AI call had failed (the list went to the command as an option), so every title was guessed: "Book club"
    # stayed "likely" and was never offered to skip. Guesses are asked again, once a day, until the AI answers.
    app = new_app(tmp_path)
    app.do("add", title="Book club", when="fixed", start="2026-10-20T19:00", end="2026-10-20T20:00")
    failing = Answering("not json")
    assert rate_upcoming(app.conn, app.now_utc, client=failing) == 1
    assert rate_upcoming(app.conn, app.now_utc, client=failing) == 0  # not again today
    ai = Answering(json.dumps({"events": [{"title": "Book club", "level": "optional", "reason": "a hobby"}]}))
    assert rate_upcoming(app.conn, app.now_utc + 1440, client=ai) == 1  # the next day
    ratings = json.loads(app.conn.execute("SELECT value FROM kv WHERE key = 'event_ratings'").fetchone()[0])
    # a new install has the starter categories (C66), so an answer naming none is kept as none
    assert ratings["book club"] == {"level": "optional", "reason": "a hobby", "category": ""}
    assert rate_upcoming(app.conn, app.now_utc + 2 * 1440, client=ai) == 0  # answered: never asked again


def test_an_event_no_category_finds_gets_the_one_the_ai_names() -> None:
    # 26 Oct: "Dinner with Sam" matched no category's words and wore no colour.
    ai = Answering(json.dumps({"events": [
        {"title": "Dinner with Sam", "level": "likely", "reason": "a plan with a friend", "category": "Social"},
        {"title": "Bike repair", "level": "optional", "reason": "an errand", "category": "Nothing like it"},
    ]}))  # fmt: skip
    out = rate(["Dinner with Sam", "Bike repair"], ai, "m", ["Social", "Classes"])
    assert out["dinner with sam"]["category"] == "Social" and out["bike repair"]["category"] == ""
    asked = ai.asked[0]
    assert "Social; Classes" in asked["system"]
    assert "category" in asked["output_config"]["format"]["schema"]["properties"]["events"]["items"]["required"]


def test_the_category_the_ai_named_colours_the_event(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="categories", value={"categories": [{"name": "Social", "slug": "social", "color": "pink",
                                                                    "pattern": "poker"}]})  # fmt: skip
    app.do("add", title="Dinner with Sam", when="fixed", start="2026-10-20T19:00", end="2026-10-20T21:00")
    ai = Answering(json.dumps({"events": [
        {"title": "Dinner with Sam", "level": "likely", "reason": "plans", "category": "Social"}]}))  # fmt: skip
    rate_upcoming(app.conn, app.now_utc, client=ai)
    (dinner,) = app.do("plan", start="2026-10-20T00:00", end="2026-10-21T00:00")["fixed"]
    assert (dinner["category"], dinner["category_color"]) == ("Social", "pink")
