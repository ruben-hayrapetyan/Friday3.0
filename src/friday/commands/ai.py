"""Checking the AI (M13): one tiny call to each model Friday uses, so a refused key, a retired model or a request
the model won't take shows here, in plain words, rather than as mail stuck unread."""

import json
import tomllib
from typing import Any

from friday.api.commands import AiKeyInput, AiModelsInput, Changed, LocalModelInput, SettingsSetInput
from friday.api.types import Empty
from friday.api.views import AiModelsOut, LocalDownload, LocalModel, LocalModelsOut, ModelCheck
from friday.commands.registry import Ctx, command, query, run
from friday.core.db import connect
from friday.core.integrations import PROVIDERS, LlmSettings
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.core.plain import plain
from friday.ingest import extract, llm, local_models
from friday.sync.google_auth import write_private

PING = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}


@query("ai_check")
def ai_check(ctx: Ctx, inp: Empty) -> list[ModelCheck]:
    """Ask each model Friday uses for a one-word answer, the way Friday asks; say what came back."""
    client = llm.client(ctx.settings["llm"])
    budget = ctx.settings["llm"]
    jobs = [(budget.model, "Reads mail and documents"), (budget.small_model, "Sorts what comes in")]
    out = []
    for model, job in jobs:
        if client is None:
            said = llm.missing(budget)
            out.append(ModelCheck(model=model, job=job, ok=False, said=said))
            continue
        try:
            found, _ = extract.call(client, model, "Answer ok: true.", [{"type": "text", "text": "Ping"}], PING)
            ok = found.get("ok") is True
            # A model that answers, but not what it was asked, may not follow Friday's instructions (a small or a
            # coding model run on this Mac): said, so its readings aren't trusted blindly.
            said = "Answered" if ok else "Answered, but not as asked: it may not follow Friday's instructions well"
            out.append(ModelCheck(model=model, job=job, ok=ok, said=said))
        except Exception as error:  # the point is to show it
            out.append(ModelCheck(model=model, job=job, ok=False, said=plain(error, "The AI")))
    return out


@command("ai_key_set", logged=False)  # the key is never logged, so there is nothing to undo with
def ai_key_set(ctx: Ctx, inp: AiKeyInput) -> Changed:
    """Keep an AI service's key in secrets.toml beside friday.toml, readable by you alone (28 Oct: connect the AI in
    the setup or in Settings); an empty key forgets it. Never stored in settings, sent back or logged."""
    key = inp.key.strip()
    if any(c.isspace() for c in key):
        raise FieldError("key", "a key has no spaces or line breaks in it: paste it again")
    section = llm.SECRETS[inp.provider][0]
    path = secrets_path()
    kept = tomllib.loads(path.read_text()) if path.exists() else {}
    if any(not isinstance(v, dict) or any(isinstance(x, dict | list) for x in v.values()) for v in kept.values()):
        raise FieldError("key", f"{path} holds more than Friday writes there: add the key to it by hand")
    if key:
        kept[section] = {**kept.get(section, {}), "api_key": key}
    elif section in kept:
        kept[section].pop("api_key", None)
        if not kept[section]:
            del kept[section]
    write_private(path, toml_of(kept))
    name = {"claude": "Anthropic", "openai": "OpenAI", "compatible": "AI service"}.get(
        inp.provider, PROVIDERS[inp.provider].name
    )
    return Changed(message=f"{name} key saved" if key else f"{name} key removed")


def toml_of(sections: dict[str, dict[str, Any]]) -> str:
    """Sections of plain values as TOML: strings quoted as JSON quotes them, which TOML reads the same."""
    out = []
    for name, values in sections.items():
        out.append(f"[{name}]")
        out += [f"{k} = {toml_value(v)}" for k, v in values.items()]
        out.append("")
    return "\n".join(out)


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value))


@query("ai_models")
def ai_models(ctx: Ctx, inp: AiModelsInput) -> AiModelsOut:
    """The models a provider offers, to choose from: the service's own list once its key is in (names change too
    often to guess), or what Ollama has on this Mac."""
    try:
        chosen = LlmSettings(provider=inp.provider, base_url=inp.base_url, model="x")
        return AiModelsOut(models=llm.models_of(chosen))
    except Exception as error:  # a bad key, no answer: said, not raised
        return AiModelsOut(models=[], error=f"{error}"[:300] or type(error).__name__)


@query("local_models")
def local_models_list(ctx: Ctx, inp: Empty) -> LocalModelsOut:
    """The open models Friday offers to run on this Mac, which are here (and which Friday downloaded), the download
    under way, and the one Friday reads with."""
    have = local_models.Ollama().models()
    kept = local_models.record(ctx.conn, ctx.user_id)
    here = have or {}
    mine = set(kept["downloaded"])

    def model(name: str, label: str, size_gb: float | None, note: str = "") -> LocalModel:
        full = local_models.full(name)
        size = round(here[full] / 1e9, 1) if full in here and here[full] else size_gb
        return LocalModel(name=name, label=label, size_gb=size, note=note, here=full in here, friday=full in mine)

    catalog = [model(m["name"], m["label"], m["size_gb"], m["note"]) for m in local_models.CATALOG]
    offered = {local_models.full(m["name"]) for m in local_models.CATALOG}
    others = [model(name, name, None) for name in sorted(here) if name not in offered]
    job = local_models.DOWNLOADS.now()
    settings = ctx.settings["llm"]
    return LocalModelsOut(
        running=have is not None,
        warning=local_models.WARNING,
        catalog=catalog,
        others=others,
        download=LocalDownload(**job.out()) if job is not None else None,
        active=settings.model if settings.provider == "local" else None,
    )


@command("local_model_use", logged=False)  # what it downloads or removes isn't Friday's to undo
def local_model_use(ctx: Ctx, inp: LocalModelInput) -> Changed:
    """Read with an open model on this Mac: at once if it's here, else once Ollama has downloaded it. The model you
    had stays until the new one is ready; then, if Friday downloaded it, it's removed (one you had is never)."""
    name = inp.name.strip().lower()
    if not local_models.valid(name):
        raise FieldError("name", f'{inp.name!r} isn\'t a model name Ollama uses ("llama3.2:3b")')
    full = local_models.full(name)
    ollama = local_models.Ollama()
    have = ollama.models()
    if have is None:
        raise FieldError("name", "Ollama isn't running: open it (or install it from ollama.com), then choose again")
    if full in have:
        use_local(ctx, full)
        return Changed(message=f"Friday reads with {name} on this Mac now")
    database = ctx.conn.execute("PRAGMA database_list").fetchone()[2]
    now, user_id = ctx.now_utc, ctx.user_id
    size = next((m["size_gb"] for m in local_models.CATALOG if local_models.full(m["name"]) == full), None)
    expected = int((size or 0) * 1e9)
    job = local_models.DOWNLOADS.start(full, ollama, lambda job: downloaded(database, user_id, job, now), expected)
    if job.name != full:
        raise FieldError("name", f"{job.name} is still downloading: wait for it, or stop it first")
    about = f" (about {size} GB)" if size else ""
    return Changed(message=f"Downloading {name}{about} to this Mac; Friday switches to it when it's done")


@command("local_model_cancel", logged=False)
def local_model_cancel(ctx: Ctx, inp: Empty) -> Changed:
    """Stop the download under way; the AI you had stays."""
    return Changed(message="Stopped the download" if local_models.DOWNLOADS.cancel() else "Nothing is downloading")


def use_local(ctx: Ctx, full: str) -> None:
    from friday.commands.settings import settings_set  # settings imports this module's neighbours

    settings_set(ctx, SettingsSetInput(key="llm", value={"provider": "local", "model": full, "small_model": full}))


def downloaded(database: str, user_id: int, job: local_models.Download, now_utc: int) -> None:
    """A download ended: if it's done, the model is Friday's (it wasn't here: that's why it was downloaded), and
    Friday reads with it, which removes the one before if Friday downloaded that."""
    if job.outcome != "done":
        return
    conn = connect(database)  # the download's own thread: its own connection
    try:
        kept = local_models.record(conn, user_id)
        if job.name not in kept["downloaded"]:
            kept["downloaded"].append(job.name)
        local_models.save(conn, user_id, kept)
        conn.commit()
        value = {"provider": "local", "model": job.name, "small_model": job.name}
        run(conn, "settings_set", {"key": "llm", "value": value}, now_utc=now_utc, actor="job", provisional=False)
    except Exception as error:  # e.g. the AI is set in friday.toml: shown with the download
        job.status, job.error = "failed", f"Downloaded, but couldn't switch to it: {error}"[:300]
    finally:
        conn.close()
