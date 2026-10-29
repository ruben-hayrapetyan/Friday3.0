"""The AI Friday reads with (DESIGN §22.5, COMBINED.md 34), chosen in Settings → Integrations → AI (`llm.provider`):

- Claude: the `claude` command first, signed in as you, the way personal's Mac app used it, so no key is needed while
  the server runs on your Mac; and the Anthropic API when a key is set, for PDFs and images (which the command can't
  be handed here) and wherever the command isn't installed.
- OpenAI, with its API key (28 Oct: "check whether friday only works with claude or whether it is compatible with
  OpenAI, or any other agent").
- Any other service that speaks OpenAI's chat API at an address of its own (`llm.base_url`): OpenRouter, Ollama, LM
  Studio, Groq, Gemini's OpenAI endpoint…; a key only if it asks for one.

Every caller asks the same way, Anthropic's messages API (a system prompt, text, PDFs and images, an answer held to a
JSON schema), and gets the same back; `OpenAIClient` speaks it to the others.

A key comes from its section of `secrets.toml` beside `friday.toml` (`[anthropic]`, `[openai]` or `[compatible]`
`api_key`), else its variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `FRIDAY_AI_KEY`); it is never stored in settings,
exported or logged. The file wins: it is the one written for Friday, while the variable may be left over in a shell
for something else."""

import base64
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
import httpx

from friday.core.integrations import PROVIDERS
from friday.core.paths import secrets_path
from friday.ingest import local_models

CANDIDATES = (Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude"))
TIMEOUT_S = 180
OPENAI_URL = PROVIDERS["openai"].address
# Each provider's section of secrets.toml and its variable (core/integrations.PROVIDERS).
SECRETS = {p: (info.section, info.variable) for p, info in PROVIDERS.items()}
# What the app calls the AI it asks ("Ask Claude", "Ask GPT", "Ask Gemini", "Ask AI").
NAMES = {p: info.name for p, info in PROVIDERS.items()}


def api_key(provider: str = "claude") -> str | None:
    return key_source(provider)[0]


def key_source(provider: str = "claude") -> tuple[str | None, str]:
    """The provider's key and where it came from, for saying which one a refusal was about."""
    section, variable = SECRETS[provider]
    path = secrets_path()
    found = tomllib.loads(path.read_text()).get(section, {}).get("api_key") if path.exists() else None
    if found:
        return str(found).strip(), "secrets.toml"
    return (os.environ.get(variable) or None) if variable else None, variable or "secrets.toml"


def cli_path() -> Path | None:
    """The `claude` command, if it is installed, or the one `FRIDAY_CLAUDE` names (`named_cli`)."""
    chosen = os.environ.get("FRIDAY_CLAUDE")
    if chosen is not None:
        return named_cli(chosen)
    for path in CANDIDATES:
        if path.exists() and os.access(path, os.X_OK):
            return path
    found = shutil.which("claude")
    return Path(found) if found else None


def named_cli(chosen: str) -> Path | None:
    """`FRIDAY_CLAUDE`: another `claude` command, or "none" for a Friday that acts as if there were none (a fresh
    user without Claude, scripts/fresh_user.sh --no-claude)."""
    named = Path(chosen).expanduser()
    return named if chosen not in ("", "none") and named.exists() and os.access(named, os.X_OK) else None


def client(settings: Any = None) -> Any | None:
    """The AI `settings` (`llm`) choose; None when it can't be asked yet (`missing` says why). For Claude: the command
    when installed (and the API behind it for documents), else the API. Any other speaks OpenAI's chat API: OpenAI
    itself, Gemini, Grok, Muse, a service at an address you give, or an open model Ollama runs on this Mac."""
    provider = getattr(settings, "provider", "claude")
    if provider == "local":
        model = getattr(settings, "model", "")
        installed = local_models.Ollama().models() if model else None
        if not model or installed is None or local_models.full(model) not in installed:
            return None
        return OpenAIClient(local_models.chat_url(), None, "compatible", timeout=local_models.LOCAL_TIMEOUT_S)
    if provider != "claude":
        info, key = PROVIDERS[provider], api_key(provider)
        address = address_of(settings)
        if (info.needs_key and not key) or not address or not getattr(settings, "model", ""):
            return None
        return OpenAIClient(address, key, "openai" if provider == "openai" else "compatible")
    key = api_key()
    api = anthropic.Anthropic(api_key=key) if key else None
    path = cli_path()
    if path is None:
        return api
    return Routed(CliClient(path), api)


def address_of(settings: Any) -> str | None:
    """Where a provider's chat API is: the address you gave, else its own."""
    provider = getattr(settings, "provider", "claude")
    return getattr(settings, "base_url", None) or PROVIDERS[provider].address


def missing(settings: Any = None) -> str:
    """Why there's no AI to ask, in words to act on."""
    provider = getattr(settings, "provider", "claude")
    where = "in Settings → Integrations → AI"
    if provider == "local":
        model = getattr(settings, "model", "")
        if not model:
            return f"Choose an open model to run on this Mac {where}"
        if local_models.Ollama().models() is None:
            return "Ollama isn't running: open it (or install it from ollama.com) to use the model on this Mac"
        job = local_models.DOWNLOADS.now()
        if job is not None and job.status == "downloading" and job.name == local_models.full(model):
            share = f" ({round(100 * job.completed / job.total)}%)" if job.total else ""
            return f"{model} is still downloading{share}"
        return f"{model} isn't on this Mac yet: download it {where}"
    if provider == "compatible":
        if not getattr(settings, "base_url", None):
            return f"No address for the AI service: add it {where}"
        return f"Name the model the service runs {where}"
    if provider != "claude":
        name = {"openai": "OpenAI"}.get(provider, PROVIDERS[provider].name)
        if not api_key(provider):
            return f"No {name} API key: add one {where}"
        return f"Choose a {name} model {where}"
    return (
        "No AI: install Claude Code (the claude command), add an Anthropic API key, or choose another AI in"
        " Settings → Integrations → AI"
    )


def describe(settings: Any = None) -> dict[str, Any]:
    """What the app shows of the AI: which, what it's called, and whether it can be asked."""
    provider = getattr(settings, "provider", "claude")
    has_key = (api_key() if provider == "claude" else api_key(provider)) is not None
    cli = provider == "claude" and cli_path() is not None
    ready = (cli or has_key) if provider == "claude" else client(settings) is not None
    return {"provider": provider, "name": NAMES[provider], "key": has_key, "cli": cli, "ready": ready,
            "base_url": getattr(settings, "base_url", None), "note": PROVIDERS[provider].note or None,
            "why": None if ready else missing(settings)}  # fmt: skip


def models_of(settings: Any, transport: Any = None) -> list[str]:
    """The models the provider offers, for choosing one: the service's list (its /models), or what Ollama has here.
    Raises what the service said when it won't list them (a bad key)."""
    provider = getattr(settings, "provider", "claude")
    if provider == "local":
        ollama = local_models.Ollama() if transport is None else local_models.Ollama(transport=transport)
        return sorted(ollama.models() or {})
    if provider == "claude":
        return list(PROVIDERS["claude"].models or ())
    address = address_of(settings)
    if not address:
        return []
    key = api_key(provider)
    headers = {"authorization": f"Bearer {key}"} if key else {}
    try:
        answer = httpx.Client(timeout=20, transport=transport).get(address.rstrip("/") + "/models", headers=headers)
    except httpx.HTTPError as error:
        raise APIConnectionError(f"Couldn't reach {address}: {error}") from error
    if answer.status_code >= 400:
        raise AIError(answer.status_code, error_text(answer))
    try:
        found = answer.json().get("data", [])
    except (ValueError, AttributeError):
        found = []
    return sorted({str(m.get("id", "")).removeprefix("models/") for m in found if isinstance(m, dict) and m.get("id")})


class AIError(RuntimeError):
    """A service's refusal, with its HTTP status (a bad key is 401, a model it doesn't have 404, too many asks 429)."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class APIConnectionError(RuntimeError):
    """The service couldn't be reached (named as Anthropic's are, so an outage reads the same: `provider_down`)."""


class APITimeoutError(APIConnectionError):
    """The service took too long to answer."""


class OpenAIClient:
    """OpenAI's chat API, or another service's that speaks it, standing in for `anthropic.Anthropic().messages`: the
    system prompt first, text, images as data URLs and PDFs as files (OpenAI) or their text (others, which mostly
    can't take files), and the answer held to the JSON schema asked for. A service that can't hold an answer to a
    schema is asked for JSON in words instead, and the JSON is taken out of what it says."""

    def __init__(self, base_url: str, key: str | None, flavor: str, transport: Any = None,
                 timeout: float = TIMEOUT_S):  # fmt: skip
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.key, self.flavor = key, flavor
        self.http = httpx.Client(timeout=timeout, transport=transport)
        self.messages = self

    def create(self, *, model: str, system: str, messages: list[dict[str, Any]], output_config: dict | None = None,
               max_tokens: int = 4096, **_: Any) -> Any:  # fmt: skip
        schema = (output_config or {}).get("format", {}).get("schema")
        chat = [{"role": m.get("role", "user"), "content": self.parts(m.get("content"))} for m in messages]
        limit = "max_completion_tokens" if self.flavor == "openai" else "max_tokens"
        asks: list[tuple[str, dict[str, Any] | None]] = [(system, None)]
        if schema is not None:
            said = f"{system}\n\nAnswer with one JSON object only, matching this JSON Schema:\n{json.dumps(schema)}"
            asks = [(system, {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}}),
                    (said, {"type": "json_object"}), (said, None)]  # fmt: skip
        for n, (prompt, form) in enumerate(asks):
            first = [{"role": "system", "content": prompt}] if prompt else []
            body: dict[str, Any] = {"model": model, limit: max_tokens, "messages": first + chat}
            if form is not None:
                body["response_format"] = form
            try:
                answer = self.post(body)
                break
            except AIError as error:
                if n == len(asks) - 1 or error.status_code not in (400, 422) or not about_format(str(error)):
                    raise
        return reply_of(answer, schema is not None)

    def parts(self, content: Any) -> Any:
        """A message's content as the chat API takes it: one string when it's only text."""
        if isinstance(content, str):
            return content
        out: list[dict[str, Any]] = []
        for block in content or []:
            kind = block.get("type") if isinstance(block, dict) else None
            source = block.get("source", {}) if isinstance(block, dict) else {}
            if kind == "text":
                out.append({"type": "text", "text": block.get("text", "")})
            elif kind == "image":
                url = f"data:{source.get('media_type', 'image/png')};base64,{source.get('data', '')}"
                out.append({"type": "image_url", "image_url": {"url": url}})
            elif kind == "document" and self.flavor == "openai":
                data = f"data:{source.get('media_type', 'application/pdf')};base64,{source.get('data', '')}"
                out.append({"type": "file", "file": {"filename": "document.pdf", "file_data": data}})
            elif kind == "document":
                text = pdf_text(base64.b64decode(source.get("data", "")))
                if not text:
                    raise RuntimeError("This AI service can't be handed a PDF, and this one has no text to read out")
                out.append({"type": "text", "text": f"The attached PDF, as text:\n\n{text}"})
        if all(p["type"] == "text" for p in out):
            return "\n\n".join(p["text"] for p in out)
        return out

    def post(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {"content-type": "application/json"}
        if self.key:
            headers["authorization"] = f"Bearer {self.key}"
        try:
            answer = self.http.post(self.url, json=body, headers=headers)
        except httpx.TimeoutException as error:
            raise APITimeoutError(f"{self.url} didn't answer in time") from error
        except httpx.HTTPError as error:
            raise APIConnectionError(f"Couldn't reach {self.url}: {error}") from error
        if answer.status_code >= 400:
            raise AIError(answer.status_code, error_text(answer))
        try:
            return answer.json()
        except ValueError as error:
            raise AIError(answer.status_code, "The service's answer wasn't JSON") from error


def about_format(said: str) -> bool:
    """Whether a refusal is about the answer's format (a service without JSON schemas, or without JSON mode)."""
    said = said.lower()
    return any(word in said for word in ("response_format", "json_schema", "json_object", "json schema", "structured"))


def error_text(answer: httpx.Response) -> str:
    try:
        found = answer.json()
    except ValueError:
        return answer.text[:300] or f"HTTP {answer.status_code}"
    error = found.get("error") if isinstance(found, dict) else None
    said = error.get("message") if isinstance(error, dict) else error if isinstance(error, str) else None
    return str(said or found)[:300]


def reply_of(answer: dict[str, Any], wants_json: bool) -> Any:
    """The chat API's answer as Anthropic's: its text (the JSON alone, when JSON was asked for) and the tokens."""
    choices = answer.get("choices") or []
    if not choices:
        raise RuntimeError(f"The AI service answered with nothing: {str(answer)[:200]}")
    message = choices[0].get("message") or {}
    if message.get("refusal"):
        raise RuntimeError(f"The AI declined: {message['refusal']}"[:300])
    content = message.get("content")
    text = content if isinstance(content, str) else "".join(
        p.get("text", "") for p in content or [] if isinstance(p, dict)
    )  # fmt: skip
    if not text.strip() and choices[0].get("finish_reason") == "length":
        raise RuntimeError("The AI ran out of room before answering (its token limit)")
    if wants_json:
        text = json_in(text)
    usage = answer.get("usage") or {}
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
        ),
    )


def json_in(text: str) -> str:
    """The JSON object in an answer, from a fenced block or the text around it ("Here it is: {...}")."""
    stripped = text.strip()
    fenced = stripped.split("```")
    if len(fenced) >= 3:
        stripped = fenced[1].removeprefix("json").strip()
    try:
        json.loads(stripped)
        return stripped
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start >= 0 and end > start:
            inner = stripped[start : end + 1]
            json.loads(inner)  # a ValueError here says the answer had no JSON in it
            return inner
        raise ValueError(f"The AI's answer wasn't JSON: {text[:200]}") from None


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
        messages = [pdfs_as_text(m) for m in messages]  # the command takes text: a PDF's is read out here
        if has_files(messages):
            raise RuntimeError(
                "Images (and PDFs with no text in them) need an Anthropic API key (Settings → Integrations)"
            )
        prompt = "\n\n".join(text_of(m.get("content")) for m in messages if m.get("role") == "user")
        # The prompt goes in on stdin: as an argument, one starting with "-" (a list of event titles, "- Poker night")
        # was read as an option and every call failed, and a long syllabus could pass the argument limit.
        args = [str(self.path), "-p", "--model", model, "--output-format", "json", "--system-prompt", system,
                "--tools", "", "--strict-mcp-config", "--no-session-persistence"]  # fmt: skip
        schema = (output_config or {}).get("format", {}).get("schema")
        if schema is not None:
            args += ["--json-schema", json.dumps(schema)]
        folder = Path(tempfile.gettempdir()) / "friday-claude"
        folder.mkdir(exist_ok=True)
        out = self.run(args, input=prompt, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=folder)
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


PDFTOTEXT = (Path("/opt/homebrew/bin/pdftotext"), Path("/usr/local/bin/pdftotext"))


def pdftotext_path() -> Path | None:
    """Poppler's `pdftotext`, if it's installed (Homebrew puts it in one of these)."""
    found = shutil.which("pdftotext")
    return Path(found) if found else next((p for p in PDFTOTEXT if p.exists()), None)


def pdfs_as_text(message: dict[str, Any]) -> dict[str, Any]:
    """A message with each PDF it carries replaced by the PDF's text, for the `claude` command, which is handed text
    only; one with no text in it (a scan) stays a PDF, for the API."""
    content = message.get("content")
    if not isinstance(content, list):
        return message
    out = []
    for block in content:
        source = block.get("source", {}) if isinstance(block, dict) else {}
        if (
            isinstance(block, dict)
            and block.get("type") == "document"
            and source.get("media_type") == "application/pdf"
        ):
            text = pdf_text(base64.b64decode(source.get("data", "")))
            if text:
                out.append({"type": "text", "text": f"The attached PDF, as text:\n\n{text}"})
                continue
        out.append(block)
    return message | {"content": out}


def pdf_text(data: bytes, run: Any = subprocess.run) -> str | None:
    """A PDF's text, its layout kept (tables of due dates stay in rows); None without pdftotext or any text."""
    tool = pdftotext_path()
    if tool is None or not data:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data)
        f.flush()
        out = run([str(tool), "-layout", "-enc", "UTF-8", f.name, "-"], capture_output=True, timeout=60)
    text = out.stdout.decode("utf-8", "replace").strip() if out.returncode == 0 else ""
    return text or None


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")
