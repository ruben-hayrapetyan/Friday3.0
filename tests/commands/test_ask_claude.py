"""Ask Claude (COMBINED.md 20, 37): proposals as Friday's own commands, checked before you see them; nothing runs."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from friday.core.items import FieldError
from friday.ingest import llm
from tests.commands.helpers import App, new_app


class Claude:
    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer, self.asked = answer, []
        self.messages = self

    def create(self, **request: Any) -> Any:
        self.asked.append(request)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(self.answer))],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def asking(monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any]) -> Claude:
    claude = Claude(answer)
    monkeypatch.setattr(llm, "client", lambda: claude)
    return claude


def test_moving_an_event_is_proposed_as_an_edit_and_changes_nothing_yet(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = app.do("add", title="Advisor meeting", when="fixed", start="2026-10-20T17:00", end="2026-10-20T17:30")
    claude = asking(monkeypatch, {"reply": "Moved to Thursday.", "actions": [
        {"sentence": "Move Advisor meeting to Thu 17:00", "command": "edit",
         "input": {"id": event["item"]["id"], "start": "2026-10-22T17:00", "end": "2026-10-22T17:30"}}]})  # fmt: skip
    out = app.do("ask_claude", text="move my 5pm tomorrow to thursday")
    assert out["reply"] == "Moved to Thursday." and out["actions"][0]["error"] is None
    assert app.do("events", text="advisor")[0]["start"] == "2026-10-20T17:00"  # not applied
    context = claude.asked[0]["messages"][0]["content"][0]["text"]
    assert "Advisor meeting" in context and '"now": "2026-10-19T09:00"' in context
    assert app.table("kv") and any(r["key"] == "llm_usage" for r in app.table("kv"))


def test_what_a_command_wouldn_t_take_says_why(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    asking(monkeypatch, {"reply": "", "actions": [
        {"sentence": "Delete everything", "command": "undo", "input": {}},
        {"sentence": "Change the server port", "command": "settings_set", "input": {"key": "server", "value": {}}},
        {"sentence": "Add a task", "command": "add", "input": {"title": "Essay", "duration_min": "a lot"}},
        {"sentence": "Prioritize assignments", "command": "settings_set",
         "input": {"key": "kind_order", "value": ["Assignment", "Reading"]}},
    ]})  # fmt: skip
    errors = [a["error"] for a in app.do("ask_claude", text="anything")["actions"]]
    assert "undo" in errors[0] and "server" in errors[1] and "duration_min" in errors[2] and errors[3] is None


def test_a_rule_gets_only_rule_shaped_answers(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    claude = asking(monkeypatch, {"reply": "", "actions": [
        {"sentence": "Focus on exams", "command": "settings_set",
         "input": {"key": "exam_focus", "value": {"on": True, "days_before": 3}}},
        {"sentence": "Drop the essay", "command": "drop", "input": {"id": 1}},
    ]})  # fmt: skip
    out = app.do("ask_claude", text="focus on an exam before it", purpose="rule")
    assert out["actions"][0]["error"] is None and out["actions"][1]["error"] is not None
    assert "only with rule_add" in claude.asked[0]["system"]


def test_gaps_around_events_and_short_term_first_are_rules_claude_may_propose(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    gaps = {k: {"before_min": 15, "after_min": 15} for k in ("class", "meeting", "exam", "other")}
    asking(monkeypatch, {"reply": "", "actions": [
        {"sentence": "Around events", "command": "settings_set", "input": {"key": "event_kinds", "value": gaps}},
        {"sentence": "Short term", "command": "settings_set", "input": {"key": "short_term_first", "value": True}},
    ]})  # fmt: skip
    actions = app.do("ask_claude", text="15 minutes before and after events; short term over long term", purpose="rule")
    assert [a["error"] for a in actions["actions"]] == [None, None]
    for action in actions["actions"]:
        app.do(action["command"], **action["input"])
    kinds = app.do("settings")["event_kinds"]
    assert kinds["class"] == {"before_min": 15, "after_min": 15} and kinds["shove"] == {"before_min": 0, "after_min": 0}
    assert app.do("settings")["short_term_first"] is True


def test_some_kinds_gaps_change_and_the_rest_stay(app: App) -> None:
    app.do("settings_set", key="event_kinds", value={"class": {"before_min": 0, "after_min": 15}})
    kinds = app.do("settings")["event_kinds"]
    assert kinds["class"] == {"before_min": 0, "after_min": 15}
    assert kinds["meeting"] == {"before_min": 5, "after_min": 5}


def test_an_applied_proposal_is_an_ordinary_undoable_command(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    order = {"key": "kind_order", "value": ["Assignment", "Reading"]}
    asking(
        monkeypatch, {"reply": "", "actions": [{"sentence": "Prioritize", "command": "settings_set", "input": order}]}
    )
    action = app.do("ask_claude", text="prioritize assignments over readings")["actions"][0]
    applied = app.full(action["command"], payload=action["input"])
    assert app.do("settings")["kind_order"] == ["Assignment", "Reading"]
    app.do("undo", command_id=applied.command_id)
    assert app.do("settings")["kind_order"] == []


def test_without_an_ai_it_says_how_to_get_one(app: App) -> None:
    with pytest.raises(FieldError, match="claude command"):
        app.do("ask_claude", text="anything")


def test_the_daily_ai_budget_holds(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    asking(monkeypatch, {"reply": "", "actions": []})
    app.do("settings_set", key="llm", value={"daily_calls": 1})
    app.do("ask_claude", text="one")
    with pytest.raises(FieldError, match="budget"):
        app.do("ask_claude", text="two")


def test_a_proposal_that_only_changes_a_calendar_event_says_so(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    """27 Oct: "have the claude requesting approval be a toggle for changing calendar events". The toggle applies
    these at once; tasks, rules and settings still ask."""
    event = app.do("add", title="Advisor meeting", when="fixed", start="2026-10-20T17:00", end="2026-10-20T17:30")
    task = app.do("add", title="Essay", duration_min=60, due="2026-10-23T23:00")
    eid, tid = event["item"]["id"], task["item"]["id"]
    thursday = {"start": "2026-10-22T17:00", "end": "2026-10-22T17:30"}
    poker = {"title": "Poker", "when": "fixed", "start": "2026-10-22T20:00", "end": "2026-10-22T23:00"}
    morning = {"start": "2026-10-20T09:00", "end": "2026-10-20T10:00", "kind": "preferred"}
    asking(monkeypatch, {"reply": "", "actions": [
        {"sentence": "Move it", "command": "edit", "input": {"id": eid, **thursday}},
        {"sentence": "Add poker", "command": "add", "input": poker},
        {"sentence": "Make it weekly", "command": "repeat", "input": {"id": eid, "every": "week"}},
        {"sentence": "Delete it", "command": "drop", "input": {"id": eid}},
        {"sentence": "Make it a task", "command": "edit", "input": {"id": eid, "when": "anytime"}},
        {"sentence": "Move the essay's due", "command": "edit", "input": {"id": tid, "due": "2026-10-24T23:00"}},
        {"sentence": "Add a task", "command": "add", "input": {"title": "Read ch 4", "duration_min": 30}},
        {"sentence": "Pin the essay", "command": "pin", "input": {"id": tid, **morning}},
        {"sentence": "A rule", "command": "rule_add", "input": {"text": "no work after 11pm"}},
        {"sentence": "Someone else's", "command": "drop", "input": {"id": 99999}},
        {"sentence": "Broken", "command": "add", "input": {"title": "X", "when": "fixed", "start": 5}},
    ]})  # fmt: skip
    out = app.do("ask_claude", text="sort my week out")
    assert [a["event"] for a in out["actions"]] == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ]
    assert out["actions"][-1]["error"]  # one that wouldn't run is never applied without asking


def test_changing_events_without_asking_is_off_until_you_turn_it_on(app: App) -> None:
    assert app.do("settings")["claude"] == {"events_without_asking": False}
    app.do("settings_set", key="claude", value={"events_without_asking": True})
    assert app.do("settings")["claude"]["events_without_asking"] is True
