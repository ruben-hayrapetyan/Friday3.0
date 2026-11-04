"""The AI by its name, the whole system (3 Nov: "for non-claude systems, does it still say ask claude?"): a real
`fridayd serve` reading with a model on this Mac (the stand-in Ollama, tests/fake_ollama.py), only HTTP between them.
What the model proposes that Friday won't run comes back naming the AI you have, as the app shows it."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.system.test_ai_system import Friday, Ollama

REFUSED = {"reply": "", "actions": [
    {"sentence": "Undo everything", "command": "undo", "input": {}},
    {"sentence": "Change the port", "command": "settings_set", "input": {"key": "server", "value": {}}},
    {"sentence": "No mornings", "command": "rule_add", "input": {"text": "no work before 10am"}},
]}  # fmt: skip


@pytest.fixture(scope="module")
def system(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Friday, Ollama]]:
    ollama = Ollama(["llama3.2:3b"])
    friday = Friday(tmp_path_factory.mktemp("named"), ollama)
    yield friday, ollama
    friday.stop()
    ollama.stop()


def test_a_model_on_this_mac_is_called_the_ai_everywhere(system: tuple[Friday, Ollama], tmp_path: Path) -> None:
    friday, ollama = system
    assert friday.q("inbox")["llm"]["name"] == "Claude"  # a new user starts on Claude
    friday.c("local_model_use", name="llama3.2:3b")
    assert friday.q("inbox")["llm"]["name"] == "AI"  # what the app turns into "Ask AI" and "the AI"
    ollama.tell("answer " + json.dumps(REFUSED))
    out = friday.c("ask_claude", text="anything", purpose="rule")
    errors = [a["error"] for a in out["actions"]]
    assert errors == ["Friday doesn't let the AI run 'undo' here", "The AI may not change the 'server' setting", None]
    assert not any("no work before 10am" in json.dumps(r) for r in friday.q("rules"))  # nothing ran: it waits for you
