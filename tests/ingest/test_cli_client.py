"""The `claude` command standing in for the Anthropic client (COMBINED.md 34)."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from friday.ingest import llm
from friday.ingest.extract import call


def answering(reply: dict[str, Any], seen: list[list[str]]):  # noqa: ANN201
    def run(args: list[str], **_: Any) -> subprocess.CompletedProcess:
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(reply), stderr="")

    return run


def test_a_structured_answer_comes_back_as_the_api_would_give_it() -> None:
    seen: list[list[str]] = []
    reply = {"structured_output": {"ok": True}, "usage": {"input_tokens": 12, "output_tokens": 3}}
    cli = llm.CliClient(Path("/bin/claude"), run=answering(reply, seen))
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    found, used = call(cli, "claude-sonnet-5-5", "Answer ok.", [{"type": "text", "text": "Ping"}], schema)
    assert (found, used) == ({"ok": True}, 15)
    args = seen[0]
    assert (
        args[args.index("--model") + 1] == "claude-sonnet-5-5"
        and json.loads(args[args.index("--json-schema") + 1]) == schema
    )
    assert args[args.index("--tools") + 1] == "" and "--no-session-persistence" in args


def test_documents_go_to_the_api_when_there_is_a_key_and_are_refused_without() -> None:
    class Api:
        def __init__(self) -> None:
            self.messages = self
            self.asked = 0

        def create(self, **_: Any) -> str:
            self.asked += 1
            return "from the api"

    api, seen = Api(), []
    routed = llm.Routed(llm.CliClient(Path("/bin/claude"), run=answering({"result": "{}"}, seen)), api)
    pdf = [{"role": "user", "content": [{"type": "document", "source": {"data": "JVBE"}}]}]
    assert routed.messages.create(model="m", system="s", messages=pdf) == "from the api" and seen == []
    with pytest.raises(RuntimeError, match="API key"):
        llm.Routed(llm.CliClient(Path("/bin/claude")), None).messages.create(model="m", system="s", messages=pdf)


def test_a_failing_command_says_why() -> None:
    def fail(args: list[str], **_: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="Not logged in")

    with pytest.raises(RuntimeError, match="Not logged in"):
        llm.CliClient(Path("/bin/claude"), run=fail).messages.create(model="m", system="s", messages=[])


def test_a_prompt_that_starts_with_a_dash_goes_in_on_stdin() -> None:
    # Event titles listed "- Poker night" were read by the command as an option: every rating failed, unseen.
    handed: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        handed.update(args=args, input=kwargs.get("input"))
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"result": "{}"}), stderr="")

    titles = [{"type": "text", "text": "- Poker night\n- CS 2112 Lecture"}]
    llm.CliClient(Path("/bin/claude"), run=run).messages.create(
        model="m", system="s", messages=[{"role": "user", "content": titles}]
    )
    assert handed["input"] == "- Poker night\n- CS 2112 Lecture"
    assert not any(a.startswith("- Poker") for a in handed["args"])
