"""The AI Friday reads with (DESIGN §22.5, COMBINED.md 34): the `claude` command first, signed in as you, the way
personal's Mac app used it, so no key is needed while the server runs on your Mac; and the Anthropic API when a key
is set, for PDFs and images (which the command can't be handed here) and wherever the command isn't installed.

The key comes from `[anthropic] api_key` in `secrets.toml` beside `friday.toml`, or else `ANTHROPIC_API_KEY`; it is
never stored in settings, exported or logged. The file wins: it is the one written for Friday, while the variable may
be left over in a shell for something else."""

import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic

from friday.core.paths import secrets_path

CANDIDATES = (Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude"))
TIMEOUT_S = 180


def api_key() -> str | None:
    return key_source()[0]


def key_source() -> tuple[str | None, str]:
    """The key and where it came from, for saying which one a refusal was about."""
    path = secrets_path()
    found = tomllib.loads(path.read_text()).get("anthropic", {}).get("api_key") if path.exists() else None
    if found:
        return found.strip(), "secrets.toml"
    return os.environ.get("ANTHROPIC_API_KEY") or None, "ANTHROPIC_API_KEY"


def cli_path() -> Path | None:
    """The `claude` command, if it is installed."""
    for path in CANDIDATES:
        if path.exists() and os.access(path, os.X_OK):
            return path
    found = shutil.which("claude")
    return Path(found) if found else None


def client() -> Any | None:
    """The command when installed (and the API behind it for documents), else the API; None with neither."""
    key = api_key()
    api = anthropic.Anthropic(api_key=key) if key else None
    path = cli_path()
    if path is None:
        return api
    return Routed(CliClient(path), api)


class Routed:
    """The command for text, the API for PDFs and images (when there is a key)."""

    def __init__(self, cli: "CliClient", api: Any | None):
        self.cli, self.api = cli, api
        self.messages = self

    def create(self, **request: Any) -> Any:
        if self.api is not None and has_files(request.get("messages", [])):
            return self.api.messages.create(**request)
        return self.cli.messages.create(**request)


def has_files(messages: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(block, dict) and block.get("type") in ("document", "image")
        for m in messages
        for block in (m.get("content") if isinstance(m.get("content"), list) else [])
    )


class CliClient:
    """The `claude` command in print mode, standing in for `anthropic.Anthropic().messages`: no tools, no MCP servers
    and no saved session, the answer held to the JSON schema asked for (personal's parse.py did the same)."""

    def __init__(self, path: Path, run: Any = subprocess.run):
        self.path, self.run = path, run
        self.messages = self

    def create(self, *, model: str, system: str, messages: list[dict[str, Any]], output_config: dict | None = None,
               **_: Any) -> Any:  # fmt: skip
        if has_files(messages):
            raise RuntimeError("PDFs and images need an Anthropic API key (Settings → Integrations)")
        prompt = "\n\n".join(text_of(m.get("content")) for m in messages if m.get("role") == "user")
        args = [str(self.path), "-p", prompt, "--model", model, "--output-format", "json", "--system-prompt", system,
                "--tools", "", "--strict-mcp-config", "--no-session-persistence"]  # fmt: skip
        schema = (output_config or {}).get("format", {}).get("schema")
        if schema is not None:
            args += ["--json-schema", json.dumps(schema)]
        folder = Path(tempfile.gettempdir()) / "friday-claude"
        folder.mkdir(exist_ok=True)
        out = self.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=folder)
        if out.returncode != 0:
            raise RuntimeError(f"claude exited {out.returncode}: {(out.stderr or out.stdout).strip()[:300]}")
        envelope = json.loads(out.stdout)
        structured = envelope.get("structured_output")
        text = json.dumps(structured) if structured is not None else str(envelope.get("result", ""))
        usage = envelope.get("usage") or {}
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=int(usage.get("input_tokens", 0)), output_tokens=int(usage.get("output_tokens", 0))
            ),
        )


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
