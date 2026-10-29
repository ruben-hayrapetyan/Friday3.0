"""The open models Friday runs on this Mac, from the inside (ingest/local_models.py): Ollama's address and model
names, what it has, a download and its progress, a removal, and above all which models Friday may remove: only one it
downloaded, never one that was here before or that you pulled yourself (28 Oct: "if the user has a previously
downloaded version of the model that downloaded version should NOT get cleaned"). Ollama is a stand-in."""

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from friday.ingest import local_models
from friday.ingest.local_models import Download, Downloads, Ollama, forget, full, record, save, tidy, valid
from tests.commands.helpers import App, new_app
from tests.fake_ollama import GB, FakeOllama


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def ollama(fake: FakeOllama) -> Ollama:
    return Ollama(transport=fake.transport())


def ai(provider: str, model: str = "", small: str = "") -> Any:
    return SimpleNamespace(provider=provider, model=model, small_model=small or model)


# Names and the address.


@pytest.mark.parametrize(
    ("given", "named"),
    [
        ("llama3.2:3b", "llama3.2:3b"),
        ("nate/instinct", "nate/instinct:latest"),
        ("Mistral:7B", "mistral:7b"),
        ("phi4-mini", "phi4-mini:latest"),
        (" qwen3:8b ", "qwen3:8b"),
        ("hf.co/org/model:q4", "hf.co/org/model:q4"),
    ],  # fmt: skip
)
def test_a_name_is_the_one_ollama_lists(given: str, named: str) -> None:
    assert full(given) == named


@pytest.mark.parametrize("name", ["llama3.2:3b", "nate/instinct", "gemma3:4b", "deepseek-r1:8b", "hf.co/a/b:q4_k_m"])
def test_names_ollama_uses_are_accepted(name: str) -> None:
    assert valid(name)


@pytest.mark.parametrize(
    "name", ["", "../etc/passwd", "llama 3", "rm -rf", "a;b", "-flag", "x:y:z", "mod\nel", "a:b\n:c"]
)
def test_anything_else_is_refused(name: str) -> None:
    assert not valid(name)


@pytest.mark.parametrize(
    ("host", "url"),
    [
        (None, "http://127.0.0.1:11434"),
        ("127.0.0.1:11500", "http://127.0.0.1:11500"),
        ("http://mac-mini.local:11434/", "http://mac-mini.local:11434"),
        ("https://ollama.example", "https://ollama.example"),
    ],  # fmt: skip
)
def test_ollama_is_found_where_ollama_host_says(monkeypatch: pytest.MonkeyPatch, host: str | None, url: str) -> None:
    if host is None:
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_HOST", host)
    assert local_models.base() == url and local_models.chat_url() == url + "/v1"


# What Ollama has.


def test_what_ollama_has_by_full_name_and_size() -> None:
    fake = FakeOllama({"llama3.2:3b": 2 * GB, "nate/instinct:latest": 4 * GB})
    assert ollama(fake).models() == {"llama3.2:3b": 2 * GB, "nate/instinct:latest": 4 * GB}


@pytest.mark.parametrize("trouble", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_ollama_not_answering_is_none(trouble: Exception) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise trouble

    assert Ollama(transport=httpx.MockTransport(down)).models() is None


def test_ollama_answering_oddly_is_none() -> None:
    odd = httpx.MockTransport(lambda request: httpx.Response(500, text="oops"))
    assert Ollama(transport=odd).models() is None
    html = httpx.MockTransport(lambda request: httpx.Response(200, text="<html>"))
    assert Ollama(transport=html).models() is None


# A download.


def test_a_download_reports_its_progress_layer_by_layer_and_ends_here() -> None:
    fake = FakeOllama()
    seen: list[tuple[int, int, str]] = []
    ollama(fake).pull("llama3.2:3b", lambda done, total, said: seen.append((done, total, said)), threading.Event())
    assert "llama3.2:3b" in fake.models and fake.pulled == ["llama3.2:3b"]
    totals = [t for _, t, _ in seen if t]
    assert totals == sorted(totals) and seen[-1][2] == "success"
    done_at_end, total_at_end, _ = seen[-1]
    assert done_at_end == total_at_end == 3 * (2 * GB // 3)  # every layer counted once, complete


def test_a_download_ollama_refuses_says_why() -> None:
    fake = FakeOllama()
    fake.fail_pull = "no space left on device"
    with pytest.raises(RuntimeError, match="no space left"):
        ollama(fake).pull("qwen3:8b", lambda *_: None, threading.Event())
    assert "qwen3:8b" not in fake.models


def test_a_model_ollama_doesnt_know_says_so() -> None:
    unknown = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"error": "pull model manifest: file does not exist"})
    )
    with pytest.raises(RuntimeError, match="does not exist"):
        Ollama(transport=unknown).pull("no-such-model", lambda *_: None, threading.Event())


def test_a_download_that_ends_early_is_not_complete() -> None:
    cut = httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps({"status": "pulling manifest"}).encode())
    )
    with pytest.raises(RuntimeError, match="before it was complete"):
        Ollama(transport=cut).pull("llama3.2:3b", lambda *_: None, threading.Event())


def test_a_stopped_download_stops() -> None:
    stop = threading.Event()
    stop.set()
    with pytest.raises(InterruptedError):
        ollama(FakeOllama()).pull("llama3.2:3b", lambda *_: None, stop)


# A removal.


def test_a_removal_is_done_once_it_is_gone_or_was() -> None:
    fake = FakeOllama({"llama3.2:3b": GB})
    assert ollama(fake).delete("llama3.2:3b") and "llama3.2:3b" not in fake.models
    assert ollama(fake).delete("llama3.2:3b")  # already gone: done
    down = httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    assert not Ollama(transport=down).delete("llama3.2:3b")  # Ollama closed: not done


# Which models Friday removes when you change: only its own.


def friday_downloaded(app: App, *names: str) -> None:
    save(app.conn, 1, {"downloaded": list(names), "remove": []})


def test_changing_models_removes_the_one_friday_downloaded(app: App) -> None:
    fake = FakeOllama({"llama3.2:3b": 2 * GB, "qwen3:8b": 5 * GB})
    friday_downloaded(app, "llama3.2:3b")
    removed = forget(app.conn, 1, ai("local", "llama3.2:3b"), ai("local", "qwen3:8b"), ollama(fake))
    assert removed == ["llama3.2:3b"] and fake.deleted == ["llama3.2:3b"]
    assert record(app.conn, 1) == {"downloaded": [], "remove": []}


def test_a_model_that_was_here_before_is_never_removed(app: App) -> None:
    fake = FakeOllama({"llama3.2:3b": 2 * GB, "qwen3:8b": 5 * GB})
    friday_downloaded(app)  # Friday downloaded nothing: llama was yours
    assert forget(app.conn, 1, ai("local", "llama3.2:3b"), ai("local", "qwen3:8b"), ollama(fake)) == []
    assert fake.deleted == [] and "llama3.2:3b" in fake.models


def test_leaving_local_models_for_an_online_ai_removes_friday_s_only(app: App) -> None:
    fake = FakeOllama({"llama3.2:3b": 2 * GB, "mistral:7b": 4 * GB})
    friday_downloaded(app, "mistral:7b")
    forget(app.conn, 1, ai("local", "mistral:7b", "llama3.2:3b"), ai("openai", "gpt-5"), ollama(fake))
    assert fake.deleted == ["mistral:7b"] and "llama3.2:3b" in fake.models  # the small model was yours


def test_a_model_still_read_with_is_kept(app: App) -> None:
    fake = FakeOllama({"llama3.2:3b": 2 * GB, "qwen3:8b": 5 * GB})
    friday_downloaded(app, "llama3.2:3b", "qwen3:8b")
    forget(app.conn, 1, ai("local", "qwen3:8b", "llama3.2:3b"), ai("local", "llama3.2:3b"), ollama(fake))
    assert fake.deleted == ["qwen3:8b"] and "llama3.2:3b" in fake.models


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (ai("claude", "claude-sonnet-5-5"), ai("openai", "gpt-5")),
        (ai("openai", "gpt-5"), ai("local", "qwen3:8b")),
        (ai("local", "qwen3:8b"), ai("local", "qwen3:8b")),
    ],  # fmt: skip
)
def test_nothing_is_removed_when_no_local_model_goes_out_of_use(app: App, before: Any, after: Any) -> None:
    fake = FakeOllama({"qwen3:8b": 5 * GB})
    friday_downloaded(app, "qwen3:8b")
    assert forget(app.conn, 1, before, after, ollama(fake)) == [] and fake.deleted == []


def test_a_removal_ollama_couldnt_do_waits_for_next_time(app: App) -> None:
    friday_downloaded(app, "llama3.2:3b")
    down = Ollama(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    assert forget(app.conn, 1, ai("local", "llama3.2:3b"), ai("openai", "gpt-5"), down) == []
    assert record(app.conn, 1) == {"downloaded": ["llama3.2:3b"], "remove": ["llama3.2:3b"]}
    fake = FakeOllama({"llama3.2:3b": GB})
    assert forget(app.conn, 1, ai("openai", "gpt-5"), ai("openai", "gpt-5"), ollama(fake)) == ["llama3.2:3b"]
    assert record(app.conn, 1) == {"downloaded": [], "remove": []}


def test_a_waiting_removal_is_dropped_if_you_choose_the_model_again(app: App) -> None:
    save(app.conn, 1, {"downloaded": ["llama3.2:3b"], "remove": ["llama3.2:3b"]})
    fake = FakeOllama({"llama3.2:3b": GB})
    forget(app.conn, 1, ai("openai", "gpt-5"), ai("local", "llama3.2:3b"), ollama(fake))
    assert fake.deleted == [] and record(app.conn, 1)["remove"] == []


def test_a_removal_of_a_model_friday_didnt_download_is_never_done_whatever_the_record_says() -> None:
    kept = {"downloaded": ["mistral:7b"], "remove": ["llama3.2:3b", "mistral:7b"]}
    fake = FakeOllama({"llama3.2:3b": GB, "mistral:7b": GB})
    assert tidy(kept, ollama(fake)) == ["mistral:7b"]
    assert fake.deleted == ["mistral:7b"] and kept == {"downloaded": [], "remove": []}


# Downloads, one at a time, on their own thread.


def test_a_download_runs_on_its_own_and_says_when_it_ends() -> None:
    downloads, fake, ended = Downloads(), FakeOllama(), []
    job = downloads.start("llama3.2:3b", ollama(fake), ended.append)
    downloads.wait()
    assert ended == [job] and job.status == "done" and job.total and job.completed == job.total
    assert "llama3.2:3b" in fake.models


def test_one_download_at_a_time() -> None:
    downloads, fake = Downloads(), FakeOllama()
    fake.gate = threading.Event()
    first = downloads.start("llama3.2:3b", ollama(fake), lambda job: None)
    assert downloads.start("qwen3:8b", ollama(fake), lambda job: None) is first
    fake.gate.set()
    downloads.wait()
    assert fake.pulled == ["llama3.2:3b"]


def test_a_failed_download_says_why_and_a_cancelled_one_says_so() -> None:
    downloads, fake, ended = Downloads(), FakeOllama(), []
    fake.fail_pull = "disk full"
    job = downloads.start("qwen3:8b", ollama(fake), ended.append)
    downloads.wait()
    assert (job.status, job.error) == ("failed", "disk full") and ended == [job]
    assert not downloads.cancel()  # nothing under way
    fake.fail_pull, fake.gate = None, threading.Event()
    job = downloads.start("mistral:7b", ollama(fake), ended.append)
    assert downloads.cancel()
    fake.gate.set()
    downloads.wait()
    assert job.status in ("cancelled", "done")  # stopped at the next line Ollama sends, if any was left


def test_what_a_download_says_to_the_app() -> None:
    job = Download("qwen3:8b", completed=10, total=40, said="pulling")
    assert job.out() == {"name": "qwen3:8b", "status": "downloading", "completed": 10, "total": 40, "said": "pulling",
                         "error": None}  # fmt: skip


def test_the_catalog_names_are_valid_and_each_warns_what_it_costs() -> None:
    assert all(valid(m["name"]) and m["size_gb"] > 0 and m["note"] for m in local_models.CATALOG)
    assert any("instinct" in m["name"] and "code" in m["note"] for m in local_models.CATALOG)
    assert "downloaded here" in local_models.WARNING and "slow" in local_models.WARNING


def test_a_download_s_size_is_the_known_one_until_ollama_has_said_more() -> None:
    # 29 Oct: "50% of 0.7 GB" for a 5.2 GB model: Ollama tells of each part as it reaches it.
    job = Download("qwen3:8b", completed=350_000_000, total=700_000_000, expected=5_200_000_000)
    assert job.out()["total"] == 5_200_000_000
    job.total = 5_300_000_000
    assert job.out()["total"] == 5_300_000_000
    assert Download("someone/model", completed=1, total=10).out()["total"] == 10  # not in the catalog: Ollama's
