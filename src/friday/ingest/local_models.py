"""Open models run on this Mac (28 Oct: "some open source ones too but make sure that it is clear that the model will
be downloaded to the computer of the user and that it will be slow to inference. for the open source ones the user
must first decide which model to locally run... the type of model should at any time be able to be changed (and for
the ones that are downloaded the previous copy should be cleaned)... if the user has a previously downloaded version
of the model that downloaded version should NOT get cleaned").

Ollama runs them (a free app, installed by you: Friday never installs software). Friday asks it what it has, has it
download the model you choose (progress shown), reads with it through its OpenAI-style chat API, and removes a model
when you change to another, only if Friday downloaded it: one that was on this Mac before Friday asked for it, or one
you pulled yourself, is never removed. What Friday downloaded is kept in `kv.local_models`; a removal that couldn't
happen (Ollama closed) waits there and is done the next time Ollama answers.

Ollama's address is `OLLAMA_HOST`, as Ollama itself reads it, else 127.0.0.1:11434."""

import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from friday.planner.store import kv_get


# The open models offered, with roughly what each downloads: you can name any other Ollama has.
def entry(name: str, label: str, size_gb: float, note: str) -> dict[str, Any]:
    return {"name": name, "label": label, "size_gb": size_gb, "note": note}


CATALOG: list[dict[str, Any]] = [
    entry("llama3.2:3b", "Llama 3.2 3B (Meta)", 2.0, "Small and quickest; reads short mail well"),
    entry("gemma3:4b", "Gemma 3 4B (Google)", 3.3, "Small, reads well for its size"),
    entry("phi4-mini", "Phi-4 mini 3.8B (Microsoft)", 2.5, "Small, good at following instructions"),
    entry("mistral:7b", "Mistral 7B", 4.4, "Mid-sized, a steady all-rounder"),
    entry("qwen3:8b", "Qwen 3 8B (Alibaba)", 5.2, "Mid-sized, the best reader here; slower"),
    entry("deepseek-r1:8b", "DeepSeek-R1 8B", 5.2, "Thinks before answering: slowest"),
    entry(
        "nate/instinct",
        "Instinct 7B (Continue)",
        4.7,
        "Made for predicting code edits: likely to read syllabi and mail poorly",
    ),  # fmt: skip
]
WARNING = (
    "Runs on this Mac: the model is downloaded here (a few GB) and answers are slow, often a minute or more for a"
    " syllabus, using your Mac's memory while it thinks."
)
LOCAL_TIMEOUT_S = 900  # a slow Mac, a long syllabus, the model loading first
NAME = re.compile(r"^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?\Z")


def base() -> str:
    """Ollama's address: `OLLAMA_HOST` ("127.0.0.1:11434" or "http://…") else its own default."""
    host = os.environ.get("OLLAMA_HOST", "").strip() or "127.0.0.1:11434"
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.rstrip("/")


def chat_url() -> str:
    return base() + "/v1"


def full(name: str) -> str:
    """A model's name as Ollama lists it: "nate/instinct" is "nate/instinct:latest"."""
    name = name.strip().lower()
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def valid(name: str) -> bool:
    return bool(NAME.match(name.strip().lower())) and ".." not in name


class Ollama:
    """Ollama's API: what it has, a download, a removal. `transport` lets tests answer instead."""

    def __init__(self, transport: Any = None, timeout: float = 10) -> None:
        self.http = httpx.Client(base_url=base(), timeout=timeout, transport=transport)
        self.transport = transport

    def models(self) -> dict[str, int] | None:
        """Each model Ollama has, by full name, with its size in bytes; None when Ollama doesn't answer."""
        try:
            answer = self.http.get("/api/tags")
            answer.raise_for_status()
            return {
                full(m.get("name") or m.get("model") or ""): int(m.get("size") or 0)
                for m in answer.json().get("models", [])
            }
        except (httpx.HTTPError, ValueError):
            return None

    def pull(self, name: str, progress: Callable[[int, int, str], None], stop: threading.Event) -> None:
        """Download `name`, telling `progress` (bytes done, bytes in all, what Ollama says); raises on a failure."""
        layers: dict[str, tuple[int, int]] = {}
        with (
            httpx.Client(base_url=base(), timeout=httpx.Timeout(30, read=600), transport=self.transport) as http,
            http.stream("POST", "/api/pull", json={"model": name, "stream": True}) as answer,
        ):
            if answer.status_code >= 400:
                answer.read()
                raise RuntimeError(error_of(answer.text) or f"Ollama answered {answer.status_code}")
            for line in answer.iter_lines():
                if stop.is_set():
                    raise InterruptedError("cancelled")
                if not line.strip():
                    continue
                said = json.loads(line)
                if said.get("error"):
                    raise RuntimeError(str(said["error"]))
                if said.get("digest") and said.get("total"):
                    layers[said["digest"]] = (int(said.get("completed") or 0), int(said["total"]))
                done, total = sum(c for c, _ in layers.values()), sum(t for _, t in layers.values())
                progress(done, total, str(said.get("status", "")))
                if said.get("status") == "success":
                    return
        raise RuntimeError("the download ended before it was complete")

    def delete(self, name: str) -> bool:
        """Remove `name`; True when it's gone (or was), False when Ollama couldn't be asked."""
        try:
            answer = self.http.request("DELETE", "/api/delete", json={"model": name})
        except httpx.HTTPError:
            return False
        return answer.status_code in (200, 404)


def error_of(text: str) -> str | None:
    try:
        return str(json.loads(text).get("error") or "") or None
    except (ValueError, AttributeError):
        return text[:200] or None


# What Friday downloaded, and removals still to do.


def record(conn: sqlite3.Connection, user_id: int) -> dict[str, list[str]]:
    kept = kv_get(conn, "local_models", {}, user_id) or {}
    return {"downloaded": list(kept.get("downloaded", [])), "remove": list(kept.get("remove", []))}


def save(conn: sqlite3.Connection, user_id: int, kept: dict[str, list[str]]) -> None:
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'local_models', ?) ON CONFLICT (user_id, key) "
        "DO UPDATE SET value = excluded.value",
        [user_id, json.dumps(kept)],
    )


def in_use(settings: Any) -> set[str]:
    """The local models the AI settings read with."""
    if getattr(settings, "provider", None) != "local":
        return set()
    return {full(m) for m in (settings.model, settings.small_model) if m}


def forget(conn: sqlite3.Connection, user_id: int, before: Any, after: Any, ollama: Ollama | None = None) -> list[str]:
    """After the AI changed from `before` to `after`: remove the local models no longer used that Friday downloaded,
    never one it didn't. Returns what was removed; one Ollama couldn't be asked to remove waits for next time."""
    kept = record(conn, user_id)
    gone_from_use = in_use(before) - in_use(after)
    mine = set(kept["downloaded"])
    kept["remove"] = sorted((set(kept["remove"]) | (gone_from_use & mine)) - in_use(after))
    removed = tidy(kept, ollama or Ollama())
    save(conn, user_id, kept)
    return removed


def tidy(kept: dict[str, list[str]], ollama: Ollama) -> list[str]:
    """Do the removals waiting in `kept` (only of models Friday downloaded), as far as Ollama answers."""
    removed = []
    for name in list(kept["remove"]):
        if name not in kept["downloaded"]:
            kept["remove"].remove(name)  # not Friday's: never removed
            continue
        if ollama.delete(name):
            removed.append(name)
            kept["remove"].remove(name)
            kept["downloaded"].remove(name)
    return removed


# Downloads, one at a time, on a thread of their own: the app shows the progress and can stop it.


@dataclass
class Download:
    name: str
    status: str = "downloading"  # downloading, done, failed, cancelled
    completed: int = 0
    total: int = 0
    said: str = ""
    error: str | None = None
    outcome: str | None = None  # how the download itself ended, before what follows it (the switch) is done
    expected: int = 0  # bytes it's known to take (the catalog's), until Ollama has said of every part
    started: float = field(default_factory=time.time)
    stop: threading.Event = field(default_factory=threading.Event)

    def out(self) -> dict[str, Any]:
        # Ollama tells of a model's parts one at a time, so its total grows: the known size stands until it's passed.
        total = max(self.total, self.expected)
        return {"name": self.name, "status": self.status, "completed": self.completed, "total": total,
                "said": self.said, "error": self.error}  # fmt: skip


class Downloads:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.current: Download | None = None
        self.thread: threading.Thread | None = None

    def now(self) -> Download | None:
        with self.lock:
            return self.current

    def start(self, name: str, ollama: Ollama, finished: Callable[[Download], None], expected: int = 0) -> Download:
        """Download `name` unless one is under way already (that one is said instead)."""
        with self.lock:
            if self.current is not None and self.current.status == "downloading":
                return self.current
            job = self.current = Download(name, expected=expected)

        def progress(done: int, total: int, said: str) -> None:
            job.completed, job.total, job.said = done, total, said

        def run() -> None:
            # Still "downloading" to the app until `finished` (the switch to the model) is done too: the app never
            # sees it done while Friday still reads with the model before.
            try:
                ollama.pull(name, progress, job.stop)
                job.outcome = "done"
            except InterruptedError:
                job.outcome = "cancelled"
            except Exception as error:  # what went wrong is shown; the AI you had stays
                job.outcome, job.error = "failed", str(error)[:300]
            try:
                finished(job)
            finally:
                if job.status == "downloading":
                    job.status = job.outcome or "failed"

        self.thread = threading.Thread(target=run, name=f"friday-pull-{name}", daemon=True)
        self.thread.start()
        return job

    def cancel(self) -> bool:
        job = self.now()
        if job is None or job.status != "downloading":
            return False
        job.stop.set()
        return True

    def wait(self, timeout: float = 10) -> None:
        """For tests: until the download under way has ended."""
        if self.thread is not None:
            self.thread.join(timeout)


DOWNLOADS = Downloads()
