"""Open models on this Mac, from the outside: only Friday's commands and its HTTP API, as the app uses them, with
Ollama a stand-in. You choose a model; one here is used at once, one that isn't is downloaded first (its size and
"slow" said beforehand), and Friday switches when it's done; the model you had stays until then, and is removed only
if Friday downloaded it. Whatever you change to (another open model, an online AI), a model you had before is kept."""

from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from friday.core.items import FieldError
from friday.ingest import llm, local_models
from tests.commands.helpers import App, new_app
from tests.fake_ollama import GB, FakeOllama

RULE = {"reply": "", "actions": [{"sentence": "No work after 10pm", "command": "rule_add",
                                  "input": {"text": "no work after 10pm"}}]}  # fmt: skip


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOllama]:
    """Friday's Ollama and the chat it reads with, both the stand-in; downloads start afresh."""
    fake = FakeOllama({"llama3.2:3b": 2 * GB}, answer=RULE)  # llama3.2 was on this Mac before Friday
    monkeypatch.setattr(local_models, "Ollama", partial(local_models.Ollama, transport=fake.transport()))
    monkeypatch.setattr(llm, "OpenAIClient", partial(llm.OpenAIClient, transport=fake.transport()))
    monkeypatch.setattr(local_models, "DOWNLOADS", local_models.Downloads())
    yield fake
    local_models.DOWNLOADS.wait()


def use(app: App, name: str) -> str:
    out = app.do("local_model_use", name=name)["message"]
    local_models.DOWNLOADS.wait()
    return out


def ai(app: App) -> dict:
    return app.do("settings")["llm"]


# Choosing.


def test_what_is_offered_says_what_it_costs_and_what_is_here(app: App, ollama: FakeOllama) -> None:
    out = app.do("local_models")
    assert out["running"] and "downloaded here" in out["warning"] and "slow" in out["warning"]
    llama = next(m for m in out["catalog"] if m["name"] == "llama3.2:3b")
    assert (llama["here"], llama["friday"], llama["size_gb"]) == (True, False, 2.0)
    qwen = next(m for m in out["catalog"] if m["name"] == "qwen3:8b")
    assert (qwen["here"], qwen["friday"], qwen["size_gb"]) == (False, False, 5.2)
    assert out["download"] is None and out["active"] is None


def test_a_model_already_here_is_used_at_once_and_isnt_friday_s(app: App, ollama: FakeOllama) -> None:
    assert use(app, "llama3.2:3b") == "Friday reads with llama3.2:3b on this Mac now"
    assert (ai(app)["provider"], ai(app)["model"], ai(app)["small_model"]) == ("local", "llama3.2:3b", "llama3.2:3b")
    assert ollama.pulled == [] and local_models.record(app.conn, 1)["downloaded"] == []
    assert app.do("local_models")["active"] == "llama3.2:3b"


def test_a_model_not_here_is_downloaded_then_used(app: App, ollama: FakeOllama) -> None:
    said = use(app, "qwen3:8b")
    assert said.startswith("Downloading qwen3:8b (about 5.2 GB)") and "switches to it when it's done" in said
    assert ollama.pulled == ["qwen3:8b"] and ai(app)["model"] == "qwen3:8b" and ai(app)["provider"] == "local"
    assert local_models.record(app.conn, 1)["downloaded"] == ["qwen3:8b"]
    out = app.do("local_models")
    assert out["download"]["status"] == "done" and out["active"] == "qwen3:8b"
    assert next(m for m in out["catalog"] if m["name"] == "qwen3:8b")["friday"] is True


def test_another_model_ollama_has_is_listed_and_can_be_named(app: App, ollama: FakeOllama) -> None:
    ollama.models["hf.co/someone/tiny:q4"] = GB
    others = app.do("local_models")["others"]
    assert [m["name"] for m in others] == ["hf.co/someone/tiny:q4"] and others[0]["size_gb"] == 1.0
    use(app, "hf.co/someone/tiny:q4")
    assert ai(app)["model"] == "hf.co/someone/tiny:q4"


# Changing: Friday's copy goes, yours stays.


def test_changing_from_friday_s_download_removes_it_once_the_new_one_is_ready(app: App, ollama: FakeOllama) -> None:
    use(app, "qwen3:8b")  # Friday's
    ollama.gate = __import__("threading").Event()
    app.do("local_model_use", name="mistral:7b")
    # While mistral downloads, qwen is still read with and still here.
    assert ai(app)["model"] == "qwen3:8b" and "qwen3:8b" in ollama.models and ollama.deleted == []
    ollama.gate.set()
    local_models.DOWNLOADS.wait()
    assert ai(app)["model"] == "mistral:7b" and ollama.deleted == ["qwen3:8b"] and "qwen3:8b" not in ollama.models
    assert local_models.record(app.conn, 1)["downloaded"] == ["mistral:7b"]


def test_changing_from_a_model_you_had_never_removes_it(app: App, ollama: FakeOllama) -> None:
    use(app, "llama3.2:3b")  # yours
    use(app, "mistral:7b")  # Friday's
    assert "llama3.2:3b" in ollama.models and ollama.deleted == []
    use(app, "llama3.2:3b")  # back to yours: Friday's mistral goes, yours was never touched
    assert ollama.deleted == ["mistral:7b"] and "llama3.2:3b" in ollama.models


def test_leaving_open_models_for_an_online_ai_removes_friday_s_copy(app: App, ollama: FakeOllama) -> None:
    use(app, "qwen3:8b")
    app.do("ai_key_set", provider="openai", key="sk-test")
    app.do("settings_set", key="llm", value={"provider": "openai"})
    assert ollama.deleted == ["qwen3:8b"] and ai(app)["model"] == "gpt-5"


def test_leaving_for_an_online_ai_keeps_a_model_you_had(app: App, ollama: FakeOllama) -> None:
    use(app, "llama3.2:3b")
    app.do("settings_set", key="llm", value={"provider": "claude"})
    assert ollama.deleted == [] and "llama3.2:3b" in ollama.models


def test_choosing_the_model_already_in_use_changes_nothing(app: App, ollama: FakeOllama) -> None:
    use(app, "qwen3:8b")
    use(app, "qwen3:8b")
    assert ollama.deleted == [] and ollama.pulled == ["qwen3:8b"]


# When it goes wrong, you keep what you had.


def test_a_failed_download_keeps_the_ai_you_had(app: App, ollama: FakeOllama) -> None:
    use(app, "qwen3:8b")
    ollama.fail_pull = "no space left on device"
    use(app, "deepseek-r1:8b")
    assert ai(app)["model"] == "qwen3:8b" and "qwen3:8b" in ollama.models and ollama.deleted == []
    download = app.do("local_models")["download"]
    assert (download["status"], download["error"]) == ("failed", "no space left on device")


def test_a_stopped_download_keeps_the_ai_you_had(app: App, ollama: FakeOllama) -> None:
    use(app, "qwen3:8b")
    ollama.gate = __import__("threading").Event()
    app.do("local_model_use", name="mistral:7b")
    assert app.do("local_model_cancel")["message"] == "Stopped the download"
    ollama.gate.set()
    local_models.DOWNLOADS.wait()
    assert ai(app)["model"] == "qwen3:8b" and ollama.deleted == []
    assert app.do("local_model_cancel")["message"] == "Nothing is downloading"


def test_a_second_choice_while_one_downloads_waits(app: App, ollama: FakeOllama) -> None:
    ollama.gate = __import__("threading").Event()
    app.do("local_model_use", name="qwen3:8b")
    with pytest.raises(FieldError, match="qwen3:8b is still downloading"):
        app.do("local_model_use", name="mistral:7b")
    ollama.gate.set()


def test_without_ollama_it_says_how_to_get_it(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_models, "DOWNLOADS", local_models.Downloads())
    out = app.do("local_models")  # OLLAMA_HOST is a closed port in tests
    assert out["running"] is False and all(not m["here"] for m in out["catalog"])
    with pytest.raises(FieldError, match="Ollama isn't running.*ollama.com"):
        app.do("local_model_use", name="llama3.2:3b")


@pytest.mark.parametrize("name", ["../../etc/passwd", "llama 3", "a;rm -rf ~", "x:y:z"])
def test_a_name_ollama_wouldnt_use_is_refused(app: App, ollama: FakeOllama, name: str) -> None:
    with pytest.raises(FieldError, match="isn't a model name"):
        app.do("local_model_use", name=name)
    assert ollama.pulled == []


# Reading with it.


def test_friday_reads_with_the_model_on_this_mac(app: App, ollama: FakeOllama) -> None:
    use(app, "llama3.2:3b")
    out = app.do("ask_claude", text="i really can't think after 10", purpose="rule")
    assert [a["command"] for a in out["actions"]] == ["rule_add"]
    (chat,) = ollama.chats
    assert chat["model"] == "llama3.2:3b" and "max_tokens" in chat
    state = app.do("inbox")["llm"]
    assert (state["provider"], state["ready"], state["name"]) == ("local", True, "AI")


def test_while_it_downloads_friday_says_so_and_asks_nothing(app: App, ollama: FakeOllama) -> None:
    ollama.gate = __import__("threading").Event()
    app.do("settings_set", key="llm", value={"provider": "local", "model": "qwen3:8b"})  # chosen, not here yet
    app.do("local_model_use", name="qwen3:8b")
    with pytest.raises(FieldError, match="qwen3:8b is still downloading"):
        app.do("ask_claude", text="anything")
    assert app.do("inbox")["llm"]["ready"] is False
    ollama.gate.set()
    local_models.DOWNLOADS.wait()
    assert app.do("inbox")["llm"]["ready"] is True


def test_the_models_listed_for_choosing_are_ollama_s(app: App, ollama: FakeOllama) -> None:
    assert app.do("ai_models", provider="local")["models"] == ["llama3.2:3b"]


# The same, over HTTP, as the app sends it.


@pytest.fixture
def http(app: App, tmp_path: Path, ollama: FakeOllama) -> Iterator[TestClient]:
    from friday.server.app import create_app  # noqa: PLC0415

    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as client:
        yield client


def test_over_http_choose_download_switch_and_clean(http: TestClient, ollama: FakeOllama) -> None:
    assert http.get("/api/q/local_models").json()["running"] is True
    assert http.post("/api/c/local_model_use", json={"name": "qwen3:8b"}).status_code == 200
    local_models.DOWNLOADS.wait()
    assert http.get("/api/q/settings").json()["llm"]["model"] == "qwen3:8b"
    assert http.post("/api/c/local_model_use", json={"name": "llama3.2:3b"}).status_code == 200
    assert ollama.deleted == ["qwen3:8b"] and "llama3.2:3b" in ollama.models
    refused = http.post("/api/c/local_model_use", json={"name": "rm -rf"})
    assert refused.status_code == 422 and "isn't a model name" in refused.json()["message"]
    foreign = http.post(
        "/api/c/local_model_use", json={"name": "mistral:7b"}, headers={"origin": "https://evil.example"}
    )
    assert foreign.status_code == 403 and "mistral:7b" not in ollama.pulled


def test_a_model_that_answers_but_not_as_asked_is_said_to(app: App, ollama: FakeOllama) -> None:
    use(app, "llama3.2:3b")  # the stand-in answers {"reply": "", "actions": []} whatever it's asked
    checks = app.do("ai_check")
    assert not any(c["ok"] for c in checks) and all("not as asked" in c["said"] for c in checks)
    ollama.answer = {"ok": True}
    assert all(c["ok"] and c["said"] == "Answered" for c in app.do("ai_check"))
