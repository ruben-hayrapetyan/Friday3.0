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


class Api:
    def __init__(self) -> None:
        self.messages = self
        self.asked = 0

    def create(self, **_: Any) -> str:
        self.asked += 1
        return "from the api"


def test_a_scan_or_an_image_goes_to_the_command_as_a_file_it_may_only_read() -> None:
    """29 Oct: "friday should use the cli whenever it can to not use the API": no key for a scan or a photo either."""
    handed: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        folder = Path(kwargs["cwd"])
        handed.update(args=args, input=kwargs["input"], files=sorted(p.name for p in folder.iterdir()), folder=folder)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"structured_output": {"ok": True}}), stderr="")

    api = Api()
    routed = llm.Routed(llm.CliClient(Path("/bin/claude"), run=run), api)
    scan = {"type": "document", "source": {"media_type": "application/pdf", "data": "JVBERi0="}}
    photo = {"type": "image", "source": {"media_type": "image/jpeg", "data": "/9j/"}}
    reply = routed.messages.create(model="m", system="s", messages=[{"role": "user", "content": [scan, photo]}],
                                   output_config={"format": {"schema": {"type": "object"}}})  # fmt: skip
    assert reply.content[0].text == '{"ok": true}' and api.asked == 0  # no key, no API
    assert handed["files"] == ["document-1.pdf", "image-2.jpg"]
    args = handed["args"]
    assert args[args.index("--tools") + 1] == "Read" and args[args.index("--allowedTools") + 1] == "Read"
    assert "--restricted" in args and "--strict-mcp-config" in args
    assert str(handed["folder"] / "document-1.pdf") in handed["input"] and "Read tool" in handed["input"]
    assert not handed["folder"].exists()  # the files are gone once it has answered


def test_text_alone_gives_the_command_no_tools_at_all() -> None:
    seen: list[list[str]] = []
    llm.CliClient(Path("/bin/claude"), run=answering({"result": "{}"}, seen)).messages.create(
        model="m", system="s", messages=[{"role": "user", "content": "Ping"}]
    )
    assert seen[0][seen[0].index("--tools") + 1] == "" and "--restricted" not in seen[0]


def test_the_api_answers_only_when_the_command_fails_and_there_is_a_key() -> None:
    def fail(args: list[str], **_: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="Not logged in")

    api = Api()
    ask = {"model": "m", "system": "s", "messages": [{"role": "user", "content": "Ping"}]}
    assert llm.Routed(llm.CliClient(Path("/bin/claude"), run=fail), api).messages.create(**ask) == "from the api"
    with pytest.raises(RuntimeError, match="Not logged in"):
        llm.Routed(llm.CliClient(Path("/bin/claude"), run=fail), None).messages.create(**ask)


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


def test_an_error_the_command_answers_with_goes_to_the_api_not_into_the_answer() -> None:
    # `claude -p --output-format json` can end well yet say it failed (`is_error`, its words in `result`): taken as
    # the answer, "Invalid API key · Please run /login" was read as JSON and failed there, past the key behind it
    said = {"type": "result", "is_error": True, "result": "Invalid API key · Please run /login"}
    api = Api()
    routed = llm.Routed(llm.CliClient(Path("/bin/claude"), run=answering(said, [])), api)
    assert routed.messages.create(model="m", system="s", messages=[{"role": "user", "content": "Ping"}]) == (
        "from the api"
    )
    with pytest.raises(RuntimeError, match="Please run /login"):
        llm.CliClient(Path("/bin/claude"), run=answering(said, [])).create(model="m", system="s", messages=[])
