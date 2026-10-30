"""OpenAI's and Google's commands standing in for their APIs, as `claude` does for Anthropic's (29 Oct: "friday should
use the cli whenever it can to not use the API... pasting in the api key seems pointless for some things"): `codex`
signed in with ChatGPT, Google's `agy` or `gemini` signed in with a Google account, each preferred when installed and
the key only behind it. Fakes only: no real command or AI is run."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from friday.ingest import llm
from friday.ingest.extract import call

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
PING = [{"role": "user", "content": "Ping"}]


def ran(reply: Any, seen: list[dict[str, Any]], code: int = 0, stderr: str = "", last: str | None = None):  # noqa: ANN201
    """A command that answers `reply` (JSON on stdout), or writes `last` where `-o` says, and remembers how it ran."""

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        seen.append({"args": args, **kwargs, "files": sorted(p.name for p in Path(kwargs["cwd"]).iterdir())})
        if last is not None and "-o" in args:
            Path(args[args.index("-o") + 1]).write_text(last)
        out = reply if isinstance(reply, str) else json.dumps(reply)
        return subprocess.CompletedProcess(args, code, stdout=out, stderr=stderr)

    return run


class TestCodex:
    def test_asks_codex_exec_read_only_with_the_prompt_on_stdin_and_reads_the_last_message(self) -> None:
        seen: list[dict[str, Any]] = []
        codex = llm.CodexClient(Path("/usr/local/bin/codex"), run=ran("", seen, last='{"ok": true}'))
        found, _ = call(codex, "gpt-5", "Answer ok.", [{"type": "text", "text": "- Poker night"}], SCHEMA)
        assert found == {"ok": True}
        args = seen[0]["args"]
        assert args[:2] == ["/usr/local/bin/codex", "exec"] and args[-1] == "-"
        for flag in ("--skip-git-repo-check", "--ephemeral", "--ignore-user-config", "--ignore-rules"):
            assert flag in args
        assert args[args.index("--sandbox") + 1] == "read-only" and args[args.index("--color") + 1] == "never"
        assert "--output-schema" in args and "schema.json" in seen[0]["files"]
        assert "--model" not in args  # Friday's own default for the API: codex picks its own
        assert seen[0]["input"].startswith("Answer ok.") and "- Poker night" in seen[0]["input"]

    def test_a_model_you_named_is_passed_on(self) -> None:
        seen: list[dict[str, Any]] = []
        llm.CodexClient(Path("/bin/codex"), run=ran("", seen, last="hi")).messages.create(
            model="gpt-5.3-codex", system="s", messages=PING
        )
        assert seen[0]["args"][seen[0]["args"].index("--model") + 1] == "gpt-5.3-codex"

    def test_a_schema_it_turns_down_is_asked_for_in_words_instead(self) -> None:
        tries: list[dict[str, Any]] = []

        def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            tries.append({"args": args, "input": kwargs["input"]})
            if "--output-schema" in args:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="invalid_json_schema: 'required' missing")
            Path(args[args.index("-o") + 1]).write_text('Here: {"ok": true}')
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        found, _ = call(
            llm.CodexClient(Path("/bin/codex"), run=run), "m", "Answer ok.", [{"type": "text", "text": "x"}], SCHEMA
        )
        assert found == {"ok": True} and len(tries) == 2
        assert "JSON Schema" in tries[1]["input"] and "--output-schema" not in tries[1]["args"]

    def test_images_go_with_image_and_a_scan_is_left_to_the_key(self) -> None:
        seen: list[dict[str, Any]] = []
        photo = {"type": "image", "source": {"media_type": "image/png", "data": "iVBORw=="}}
        llm.CodexClient(Path("/bin/codex"), run=ran("", seen, last="seen")).messages.create(
            model="m",
            system="s",
            messages=[{"role": "user", "content": [photo, {"type": "text", "text": "What's this?"}]}],
        )
        args = seen[0]["args"]
        assert Path(args[args.index("--image") + 1]).name == "image-1.png"
        scan = {"type": "document", "source": {"media_type": "application/pdf", "data": "JVBERi0="}}
        with pytest.raises(RuntimeError, match="scanned PDF"):
            llm.CodexClient(Path("/bin/codex"), run=ran("", [])).messages.create(
                model="m", system="s", messages=[{"role": "user", "content": [scan]}]
            )

    def test_not_signed_in_says_why(self) -> None:
        with pytest.raises(RuntimeError, match="Not signed in"):
            llm.CodexClient(
                Path("/bin/codex"), run=ran("", [], code=1, stderr="Not signed in. Run codex login")
            ).messages.create(model="m", system="s", messages=PING)


class TestGoogle:
    def test_agy_takes_the_prompt_as_one_value_and_holds_the_answer_to_the_schema(self) -> None:
        seen: list[dict[str, Any]] = []
        reply = {
            "status": "SUCCESS",
            "response": "",
            "structured_output": {"ok": True},
            "usage": {"input_tokens": 9, "output_tokens": 2},
        }
        found, used = call(
            llm.GeminiCliClient(Path("/opt/homebrew/bin/agy"), run=ran(reply, seen)),
            "gemini-3-pro",
            "Answer ok.",
            [{"type": "text", "text": "- Poker night"}],
            SCHEMA,
        )
        assert (found, used) == ({"ok": True}, 11)
        args = seen[0]["args"]
        assert (
            args[args.index("--output-format") + 1] == "json"
            and json.loads(args[args.index("--json-schema") + 1]) == SCHEMA
        )
        assert args[args.index("--model") + 1] == "gemini-3-pro"
        assert args[-1].startswith("--prompt=Answer ok.") and "- Poker night" in args[-1] and seen[0]["input"] is None

    def test_gemini_reads_the_text_on_stdin_read_only_and_finds_the_json_in_its_answer(self) -> None:
        seen: list[dict[str, Any]] = []
        reply = {"response": '```json\n{"ok": true}\n```', "stats": {}}
        found, _ = call(
            llm.GeminiCliClient(Path("/usr/local/bin/gemini"), run=ran(reply, seen)),
            "",
            "Answer ok.",
            [{"type": "text", "text": "Ping"}],
            SCHEMA,
        )
        assert found == {"ok": True}
        args = seen[0]["args"]
        assert "--approval-mode=plan" in args and seen[0]["input"] == "Ping" and "--model" not in args
        assert args[-1].startswith("--prompt=Answer ok.") and "JSON Schema" in args[-1]

    def test_an_error_or_a_failed_run_says_why(self) -> None:
        with pytest.raises(RuntimeError, match="authentication required"):
            llm.GeminiCliClient(
                Path("/bin/agy"),
                run=ran({"status": "ERROR", "error": {"message": "authentication required"}}, [], code=1),
            ).messages.create(model="", system="s", messages=PING)
        with pytest.raises(RuntimeError, match="gemini exited 42"):
            llm.GeminiCliClient(Path("/bin/gemini"), run=ran("Unknown arguments", [], code=42)).messages.create(
                model="", system="s", messages=PING
            )

    def test_images_are_left_to_the_key(self) -> None:
        photo = {"type": "image", "source": {"media_type": "image/png", "data": "iVBORw=="}}
        with pytest.raises(RuntimeError, match="needs a key"):
            llm.GeminiCliClient(Path("/bin/agy"), run=ran({}, [])).messages.create(
                model="", system="s", messages=[{"role": "user", "content": [photo]}]
            )


class TestFinding:
    def fake(self, tmp_path: Path, name: str) -> Path:
        path = tmp_path / name
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
        return path

    def test_each_command_is_found_where_it_installs_or_named_or_switched_off(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.undo()  # conftest hides every command: find them for real here, in a folder of fakes
        monkeypatch.setenv("FRIDAY_CONFIG", str(tmp_path / "friday.toml"))
        monkeypatch.setattr(llm, "FOLDERS", (tmp_path,))
        monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
        for name in ("FRIDAY_CODEX", "FRIDAY_GEMINI"):
            monkeypatch.delenv(name, raising=False)
        assert llm.codex_path() is None and llm.gemini_path() is None
        codex, gemini = self.fake(tmp_path, "codex"), self.fake(tmp_path, "gemini")
        assert (llm.codex_path(), llm.gemini_path()) == (codex, gemini)
        agy = self.fake(tmp_path, "agy")
        assert llm.gemini_path() == agy  # Antigravity's, where a Google account's own use went, first
        monkeypatch.setenv("FRIDAY_GEMINI", str(gemini))
        monkeypatch.setenv("FRIDAY_CODEX", "none")
        assert (llm.codex_path(), llm.gemini_path()) == (None, gemini)
        assert os.access(gemini, os.X_OK)


def settings(provider: str, model: str = "") -> SimpleNamespace:
    return SimpleNamespace(provider=provider, model=model, base_url=None)


class TestChoosing:
    def test_a_provider_with_its_command_installed_needs_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(llm, "codex_path", lambda: Path("/opt/homebrew/bin/codex"))
        monkeypatch.setattr(llm, "gemini_path", lambda: Path("/opt/homebrew/bin/agy"))
        openai, gemini = llm.client(settings("openai")), llm.client(settings("gemini"))
        assert isinstance(openai.cli, llm.CodexClient) and openai.api is None
        assert isinstance(gemini.cli, llm.GeminiCliClient) and gemini.api is None
        state = llm.describe(settings("openai"))
        assert (state["ready"], state["key"], state["cli"], state["command"]) == (True, False, True, "codex")
        assert llm.describe(settings("gemini"))["command"] == "agy"

    def test_with_a_key_too_the_command_comes_first_and_the_api_behind_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(llm, "codex_path", lambda: Path("/bin/codex"))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        found = llm.client(settings("openai", "gpt-5"))
        assert isinstance(found.cli, llm.CodexClient) and isinstance(found.api, llm.OpenAIClient)

    def test_without_its_command_it_is_the_key_as_before_and_says_how_to_do_without(self) -> None:
        assert llm.client(settings("openai", "gpt-5")) is None
        why = llm.describe(settings("openai"))["why"]
        assert "API key" in why and "codex command" in why
        assert "agy command" in llm.describe(settings("gemini"))["why"]

    def test_grok_and_the_others_have_no_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(llm, "codex_path", lambda: Path("/bin/codex"))
        monkeypatch.setattr(llm, "gemini_path", lambda: Path("/bin/agy"))
        assert all(llm.command_for(p) is None for p in ("grok", "muse", "compatible", "local"))
        assert llm.describe(settings("grok"))["command"] is None
