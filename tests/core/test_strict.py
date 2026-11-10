"""Structured-output schemas as Anthropic's API takes them (10 Nov: one real request with an API key: "For 'object'
type, 'additionalProperties' must be explicitly set to false"; every "Ask the AI" failed that way)."""

import json
from pathlib import Path
from typing import Any

import pytest

from friday.commands import ai, claude
from friday.core.strict import strict_problems
from friday.ingest import llm, rating
from tests.commands.helpers import App, new_app
from tests.commands.test_ask_claude import Claude

OLD = {  # "Ask the AI" as it was sent
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object", "properties": {"input": {"type": "object"}}}},
    },
}


# Glass box: what the checker sees.


def test_the_old_ask_schema_is_what_anthropic_refused() -> None:
    assert strict_problems(OLD) == [
        "schema: an object without additionalProperties: false",
        "schema.actions.items[0]: an object without additionalProperties: false",
        "schema.actions.items[0].input: an object without additionalProperties: false",
    ]


@pytest.mark.parametrize("schema", [claude.SCHEMA, ai.PING, rating.SCHEMA], ids=["ask", "test the AI", "rating"])
def test_the_schemas_friday_sends_are_taken(schema: dict[str, Any]) -> None:
    assert strict_problems(schema) == []


def test_a_closed_object_inside_a_list_and_any_of_is_checked() -> None:
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"x": {"anyOf": [{"type": "object"}, {"type": "string"}]}}}  # fmt: skip
    assert strict_problems(schema) == ["schema.x.anyOf[0]: an object without additionalProperties: false"]


# Black box: an action's input, as JSON text (the schema now) or an object (as an AI may still give it).


@pytest.mark.parametrize(
    ("given", "read"),
    [('{"id": 41, "location": "Willard"}', {"id": 41, "location": "Willard"}), ({"id": 41}, {"id": 41}),
     ("not json", {}), ("", {}), (None, {}), ("[1, 2]", {})],
)  # fmt: skip
def test_an_actions_input_is_read_either_way(given: Any, read: dict[str, Any]) -> None:
    assert claude.input_of({"input": given}) == read


def test_ask_the_ai_with_input_as_text_proposes_the_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app: App = new_app(tmp_path)
    essay = app.do("add", text="essay 2h due fri")["item"]["id"]
    answer = {"reply": "Moved.", "actions": [{"sentence": "Rename the essay", "command": "edit",
              "input": json.dumps({"id": essay, "title": "History essay"})}]}  # fmt: skip
    monkeypatch.setattr(llm, "client", lambda *_: Claude(answer))
    out = app.do("ask_claude", text="call the essay History essay")
    (action,) = out["actions"]
    assert (action["command"], action["input"]["title"], action.get("error")) == ("edit", "History essay", None)
