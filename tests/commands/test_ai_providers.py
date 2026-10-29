"""Every part of Friday that asks an AI, on OpenAI and on another service that speaks OpenAI's chat API (28 Oct:
"check whether friday only works with claude or whether it is compatible with OpenAI, or any other agent... very in
depth test it and also make sure it doesn't break any other functionality"): Ask, the quick-add reading, documents
and syllabi (text and PDF), mail, event ratings, the model check, the day's budget, a refused key, and the key itself,
kept in secrets.toml only. The service is a stand-in (httpx's MockTransport): nothing reaches the network."""

import json
import os
import stat
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from friday.commands.fetching import sync
from friday.commands.rating import rate_upcoming
from friday.core.items import FieldError
from friday.ingest import llm
from tests.commands.helpers import App, new_app
from tests.commands.test_inbox import syllabus_answer


class Service:
    """A stand-in chat API answering each request with `answer(request body)`; every request kept."""

    def __init__(self, answer: Callable[[dict[str, Any]], Any]) -> None:
        self.answer, self.seen = answer, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.seen.append({"url": str(request.url), "headers": dict(request.headers), "body": body})
        out = self.answer(body)
        if isinstance(out, httpx.Response):
            return out
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(out)}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 700, "completion_tokens": 50},
            },
        )

    def system(self, n: int = -1) -> str:
        return self.seen[n]["body"]["messages"][0]["content"]

    def user(self, n: int = -1) -> Any:
        return self.seen[n]["body"]["messages"][1]["content"]


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def serve(monkeypatch: pytest.MonkeyPatch, answer: Callable[[dict[str, Any]], Any]) -> Service:
    """Friday's OpenAI client, talking to the stand-in."""
    service = Service(answer)
    monkeypatch.setattr(llm, "OpenAIClient", partial(llm.OpenAIClient, transport=httpx.MockTransport(service)))
    return service


def on_openai(app: App) -> None:
    app.do("ai_key_set", provider="openai", key="sk-test-123")
    app.do("settings_set", key="llm", value={"provider": "openai"})


def on_ollama(app: App) -> None:
    app.do(
        "settings_set",
        key="llm",
        value={"provider": "compatible", "base_url": "http://localhost:11434/v1", "model": "llama3.1"},
    )


SETUPS = {"openai": on_openai, "ollama": on_ollama}


@pytest.fixture(params=list(SETUPS))
def provider(request: pytest.FixtureRequest, app: App) -> str:
    SETUPS[request.param](app)
    return request.param


# Ask, and the quick-add line.


def test_ask_proposes_changes_through_the_chosen_ai(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    event = app.do("add", title="Advisor meeting", when="fixed", start="2026-10-20T17:00", end="2026-10-20T17:30")
    proposal = {
        "reply": "Moved.",
        "actions": [
            {
                "sentence": "Move it to Thursday",
                "command": "edit",
                "input": {"id": event["item"]["id"], "start": "2026-10-22T17:00", "end": "2026-10-22T17:30"},
            }
        ],
    }
    service = serve(monkeypatch, lambda body: proposal)
    out = app.do("ask_claude", text="move my 5pm tomorrow to thursday")
    assert out["reply"] == "Moved." and out["actions"][0]["error"] is None
    assert app.do("events", text="advisor")[0]["start"] == "2026-10-20T17:00"  # proposed, not done
    (sent,) = service.seen
    assert sent["body"]["model"] == ("gpt-5" if provider == "openai" else "llama3.1")
    assert "Advisor meeting" in service.user() and "move my 5pm" in service.user()
    assert sent["body"]["response_format"]["type"] == "json_schema"
    if provider == "openai":
        assert sent["url"] == "https://api.openai.com/v1/chat/completions"
        assert sent["headers"]["authorization"] == "Bearer sk-test-123"
    else:
        assert sent["url"] == "http://localhost:11434/v1/chat/completions" and "authorization" not in sent["headers"]
    assert app.do("inbox")["llm"]["tokens"] == 750  # the day's spend, as with Claude


def test_a_rule_friday_cant_read_goes_to_the_chosen_ai(
    app: App, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = {
        "reply": "",
        "actions": [{"sentence": "No work after 10pm", "command": "rule_add", "input": {"text": "no work after 10pm"}}],
    }
    service = serve(monkeypatch, lambda body: rule)
    out = app.do("ask_claude", text="i really can't think straight late at night", purpose="rule")
    assert [a["command"] for a in out["actions"]] == ["rule_add"]
    assert "typed as a rule" in service.system()


def test_the_quick_add_line_is_read_by_the_chosen_ai(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    answer = {
        "title": "call mom",
        "preset": "Event",
        "start": "2026-10-24T15:00",
        "end": "2026-10-24T15:30",
        "confidence": 0.9,
        "quotes": {},
    }
    serve(monkeypatch, lambda body: answer)
    fields = app.do("ask_ai", text="ring mum saturday afternoon around 3 for half an hour")
    assert fields["start"] == "2026-10-24T15:00" and app.do("items") == []


# Documents, syllabi and mail.


def test_a_document_is_read_into_suggestions(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    answer = {
        "is_syllabus": False,
        "items": [{"title": "PS5", "due": "2026-10-23T17:00", "quotes": {"due": "Friday at 5pm"}, "confidence": 0.9}],
    }
    service = serve(monkeypatch, lambda body: answer)
    app.do("document_add", name="Email from prof", content="PS5 is due Friday at 5pm.")
    sync(app.conn, app.now_utc)
    (found,) = app.do("inbox")["suggestions"]
    assert found["input"]["title"] == "PS5" and found["source_text"] == "PS5 is due Friday at 5pm."
    assert "PS5 is due Friday at 5pm." in service.user()
    assert service.seen[0]["body"]["model"] == ("gpt-5" if provider == "openai" else "llama3.1")


def test_a_pdf_syllabus_becomes_one_batch(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "pdf_text", lambda data: "Midterm 1: Nov 5, 2-4pm")
    service = serve(monkeypatch, lambda body: syllabus_answer())
    app.do("document_add", name="CS 1110 syllabus.pdf", media_type="application/pdf", content="JVBERi0=")
    sync(app.conn, app.now_utc)
    batches = {s["batch"] for s in app.do("inbox")["suggestions"]}
    assert len(batches) == 1 and None not in batches
    app.do("batch_accept", batch=batches.pop())
    assert {"Midterm 1", "Midterm 1 prep"} <= {i["title"] for i in app.table("items")}
    content = service.user(0)
    if provider == "openai":  # OpenAI takes the PDF itself
        assert content[0]["type"] == "file" and content[0]["file"]["file_data"].endswith("JVBERi0=")
    else:  # another service gets its text
        assert "Midterm 1: Nov 5, 2-4pm" in content


def test_mail_and_its_pdf_are_read_through_the_chosen_ai(
    app: App, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from friday.sim.fakes import FakeGmail, mail  # noqa: PLC0415

    monkeypatch.setattr(llm, "pdf_text", lambda data: "Lab report due Friday 11:59pm")
    app.do("settings_set", key="gmail", value={"enabled": True, "sender_domains": ["cornell.edu"]})
    answer = {
        "is_syllabus": False,
        "items": [{"title": "Lab report", "due": "2026-10-23T23:59", "quotes": {}, "confidence": 0.8}],
    }
    service = serve(monkeypatch, lambda body: answer)
    box = FakeGmail(
        [mail("m1", "Prof <prof@chem.cornell.edu>", "Lab report", "<p>The lab report is due Friday.</p>", b"%PDF")]
    )
    sync(app.conn, app.now_utc, mail=box)
    assert {r["status"] for r in app.table("raw_inputs")} == {"extracted"} and len(app.table("raw_inputs")) == 2
    assert any(s["input"]["title"] == "Lab report" for s in app.do("inbox")["suggestions"])
    letter, attachment = service.user(0), service.user(1)
    assert "The lab report is due Friday." in letter and "<p>" not in letter
    if provider == "openai":
        assert attachment[0]["type"] == "file"
    else:
        assert "Lab report due Friday 11:59pm" in attachment


# Event ratings (the small model) and the model check.


def test_events_are_rated_by_the_small_model(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    app.do("add", title="Robotics", when="fixed", start="2026-10-21T18:00", end="2026-10-21T20:00")
    service = serve(
        monkeypatch,
        lambda body: {
            "events": [{"title": "Robotics", "level": "required", "reason": "the team needs you", "category": ""}]
        },
    )
    rate_upcoming(app.conn, app.now_utc)
    ratings = {r["key"]: json.loads(r["value"]) for r in app.table("kv") if r["key"] == "event_ratings"}
    assert ratings["event_ratings"]["robotics"]["level"] == "required"
    assert service.seen[0]["body"]["model"] == ("gpt-5-mini" if provider == "openai" else "llama3.1")


def test_the_model_check_asks_each_model(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    service = serve(monkeypatch, lambda body: {"ok": True})
    checks = app.do("ai_check")
    assert [c["ok"] for c in checks] == [True, True]
    expected = ["gpt-5", "gpt-5-mini"] if provider == "openai" else ["llama3.1", "llama3.1"]
    assert [c["model"] for c in checks] == expected == [s["body"]["model"] for s in service.seen]


def test_a_retired_model_shows_in_the_check(app: App, provider: str, monkeypatch: pytest.MonkeyPatch) -> None:
    serve(
        monkeypatch, lambda body: httpx.Response(404, json={"error": {"message": "The model `gpt-5` does not exist"}})
    )
    checks = app.do("ai_check")
    assert not any(c["ok"] for c in checks) and all("does not exist" in c["said"] for c in checks)


# What goes wrong.


def test_a_refused_key_leaves_documents_waiting_and_names_the_key(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    on_openai(app)
    serve(monkeypatch, lambda body: httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}}))
    for n in range(2):
        app.do("document_add", name=f"handout {n}", content=f"Reading {n} due Friday")
    sync(app.conn, app.now_utc)
    assert [r["status"] for r in app.table("raw_inputs")] == ["new", "new"]  # read again later
    said = app.table("sources")[0]["last_error"]
    assert "refused the key from secrets.toml" in said and "Incorrect API key" in said


def test_an_unreachable_service_leaves_documents_waiting(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    on_ollama(app)

    def down(body: dict[str, Any]) -> Any:
        raise httpx.ConnectError("connection refused")

    serve(monkeypatch, down)
    app.do("document_add", name="handout", content="Reading due Friday")
    sync(app.conn, app.now_utc)
    assert [r["status"] for r in app.table("raw_inputs")] == ["new"]
    assert "unavailable" in app.table("sources")[0]["last_error"]


def test_without_a_key_or_an_address_nothing_is_asked_and_it_says_what_to_add(app: App) -> None:
    app.do("settings_set", key="llm", value={"provider": "openai"})
    with pytest.raises(FieldError, match="No OpenAI API key"):
        app.do("ask_claude", text="anything")
    with pytest.raises(FieldError, match="No OpenAI API key"):
        app.do("ask_ai", text="anything")
    app.do("document_add", name="handout", content="Reading due Friday")
    sync(app.conn, app.now_utc)
    assert "No OpenAI API key" in app.table("sources")[0]["last_error"]
    app.do("settings_set", key="llm", value={"provider": "compatible"})
    assert "No address" in app.do("ai_check")[0]["said"]
    state = app.do("inbox")["llm"]
    assert (state["provider"], state["ready"], state["key"]) == ("compatible", False, False)


def test_the_days_budget_holds_whichever_ai(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    on_openai(app)
    app.do("settings_set", key="llm", value={"daily_calls": 1})
    service = serve(monkeypatch, lambda body: {"reply": "", "actions": []})
    app.do("ask_claude", text="first")
    with pytest.raises(FieldError, match="budget is spent"):
        app.do("ask_claude", text="second")
    assert len(service.seen) == 1


# The key: in secrets.toml, for you alone, never in settings, the log or an answer.


def test_a_key_is_kept_in_secrets_toml_for_you_alone(app: App, no_personal_config: Path) -> None:
    secrets = no_personal_config / "secrets.toml"
    secrets.write_text('[anthropic]\napi_key = "sk-ant-keep"\n\n[other]\nname = "x"\nn = 3\non = true\n')
    out = app.full("ai_key_set", payload={"provider": "openai", "key": "  sk-new-456  "})
    assert out.result["message"] == "OpenAI key saved" and "sk-new" not in json.dumps(out.result)
    assert stat.S_IMODE(os.stat(secrets).st_mode) == 0o600
    assert llm.key_source("openai") == ("sk-new-456", "secrets.toml")
    assert llm.api_key("claude") == "sk-ant-keep"  # the others stay
    assert 'name = "x"' in secrets.read_text() and "n = 3" in secrets.read_text() and "on = true" in secrets.read_text()
    assert "sk-new" not in json.dumps(app.table("command_log")) and "sk-new" not in json.dumps(app.do("settings"))
    assert app.do("inbox")["llm"]["key"] is True and "sk-new" not in json.dumps(app.do("inbox"))  # Claude's, kept
    app.do("ai_key_set", provider="openai", key="")
    assert llm.api_key("openai") is None and "[openai]" not in secrets.read_text()
    assert llm.api_key("claude") == "sk-ant-keep"


@pytest.mark.parametrize("key", ["sk with spaces", "sk-1\nsk-2", "sk-\ttab"])
def test_a_key_with_spaces_or_line_breaks_is_refused(app: App, key: str) -> None:
    with pytest.raises(FieldError, match="no spaces"):
        app.do("ai_key_set", provider="openai", key=key)


def test_a_secrets_file_with_more_than_friday_writes_isnt_rewritten(app: App, no_personal_config: Path) -> None:
    secrets = no_personal_config / "secrets.toml"
    secrets.write_text('[google]\nscopes = ["a", "b"]\n')
    with pytest.raises(FieldError, match="by hand"):
        app.do("ai_key_set", provider="openai", key="sk-x")
    assert secrets.read_text() == '[google]\nscopes = ["a", "b"]\n'


def test_a_key_with_quotes_reads_back_the_same(app: App) -> None:
    app.do("ai_key_set", provider="compatible", key='sk-"odd"\\key')
    assert llm.api_key("compatible") == 'sk-"odd"\\key'


# Changes only from Friday's own pages.


@pytest.fixture
def http(app: App, tmp_path: Path) -> Iterator[TestClient]:
    from friday.server.app import create_app  # noqa: PLC0415

    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as client:
        yield client


SET = {"key": "llm", "value": {"provider": "compatible", "base_url": "https://evil.example/v1"}}


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "http://192.168.1.9:8765", "null", "file://", "https://127.0.0.1.evil.example"]
)
def test_a_page_from_another_site_cant_change_anything(http: TestClient, origin: str) -> None:
    refused = http.post("/api/c/settings_set", json=SET, headers={"origin": origin})
    assert refused.status_code == 403 and "own pages" in refused.json()["message"]
    assert http.get("/api/q/settings").json()["llm"]["provider"] == "claude"


@pytest.mark.parametrize("origin", [None, "http://127.0.0.1:8765", "http://localhost:5190", "http://[::1]:5173"])
def test_friday_s_own_pages_a_dev_server_and_scripts_can(http: TestClient, origin: str | None) -> None:
    headers = {"origin": origin} if origin else {}
    assert http.post("/api/c/settings_set", json=SET, headers=headers).status_code == 200


def test_the_server_reached_by_another_name_takes_its_own_pages(http: TestClient) -> None:
    # On a phone over Tailscale the page and the server share the machine's name.
    headers = {"origin": "http://friday-mac.tail1234.ts.net:8765", "host": "friday-mac.tail1234.ts.net:8765"}
    assert http.post("/api/c/settings_set", json=SET, headers=headers).status_code == 200


def test_reading_from_another_site_is_left_to_the_browser(http: TestClient) -> None:
    assert http.get("/api/q/status", headers={"origin": "https://evil.example"}).status_code == 200


# Settings: a change names only what changes.


def test_the_daily_limit_set_alone_keeps_the_ai(app: App) -> None:
    on_openai(app)
    app.do("settings_set", key="llm", value={"daily_calls": 7})
    llm_now = app.do("settings")["llm"]
    assert (llm_now["provider"], llm_now["model"], llm_now["daily_calls"]) == ("openai", "gpt-5", 7)


def test_switching_brings_each_providers_own_models(app: App) -> None:
    app.do("settings_set", key="llm", value={"daily_calls": 9})
    on_ollama(app)
    now = app.do("settings")["llm"]
    assert (now["model"], now["small_model"], now["daily_calls"]) == ("llama3.1", "llama3.1", 9)
    app.do("settings_set", key="llm", value={"provider": "claude"})
    now = app.do("settings")["llm"]
    assert (now["provider"], now["model"], now["small_model"]) == ("claude", "claude-sonnet-5-5", "claude-haiku-5-5")
    app.do("settings_set", key="llm", value={"provider": "openai"})
    assert app.do("settings")["llm"]["model"] == "gpt-5"
    app.do("settings_set", key="llm", value={"provider": "openai", "model": "gpt-4.1"})
    assert app.do("settings")["llm"]["model"] == "gpt-4.1"  # named: kept


def test_a_bad_address_is_refused_and_changes_nothing(app: App) -> None:
    with pytest.raises(Exception, match="http:// or https://"):
        app.do("settings_set", key="llm", value={"provider": "compatible", "base_url": "localhost:11434"})
    assert app.do("settings")["llm"]["provider"] == "claude"


# Gemini, Grok and Muse: named services with addresses of their own, models chosen from their lists.

NAMED = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "Gemini"),
    "grok": ("https://api.x.ai/v1", "grok-4.6", "Grok"),
    "muse": ("https://api.meta.ai/v1", "muse-spark-1.3", "Muse"),
}


@pytest.mark.parametrize("provider", list(NAMED))
def test_a_named_service_asks_at_its_own_address_with_its_key(
    app: App, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    address, model, name = NAMED[provider]
    service = serve(monkeypatch, lambda body: {"reply": "ok", "actions": []})
    app.do("settings_set", key="llm", value={"provider": provider})
    assert app.do("settings")["llm"]["model"] == ""  # no guess: chosen from its list
    with pytest.raises(FieldError, match=f"No {name} API key"):
        app.do("ask_claude", text="anything")
    app.do("ai_key_set", provider=provider, key=f"key-{provider}")
    with pytest.raises(FieldError, match=f"Choose a {name} model"):
        app.do("ask_claude", text="anything")
    app.do("settings_set", key="llm", value={"model": model})
    assert app.do("ask_claude", text="anything")["reply"] == "ok"
    (sent,) = service.seen
    assert sent["url"] == f"{address}/chat/completions" and sent["headers"]["authorization"] == f"Bearer key-{provider}"
    assert sent["body"]["model"] == model and "max_tokens" in sent["body"]
    state = app.do("inbox")["llm"]
    assert (state["name"], state["ready"]) == (name, True)


@pytest.mark.parametrize("provider", list(NAMED))
def test_a_named_service_s_models_are_listed_for_choosing(
    app: App, provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    address = NAMED[provider][0]
    seen: list[httpx.Request] = []

    def models(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "models/b-model"}, {"id": "a-model"}, {"id": "a-model"}]})

    original = httpx.Client

    def stand_in(*args: Any, **kwargs: Any) -> httpx.Client:
        return original(*args, **(kwargs | {"transport": httpx.MockTransport(models)}))

    monkeypatch.setattr(httpx, "Client", stand_in)
    app.do("ai_key_set", provider=provider, key="k")
    out = app.do("ai_models", provider=provider)
    assert out == {"models": ["a-model", "b-model"], "error": None}
    assert str(seen[0].url) == f"{address}/models" and seen[0].headers["authorization"] == "Bearer k"


def test_a_list_the_service_refuses_says_why(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    original = httpx.Client
    refused = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "API key not valid"}}))
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: original(*a, **(k | {"transport": refused})))
    out = app.do("ai_models", provider="gemini")
    assert out["models"] == [] and "API key not valid" in out["error"]


def test_muse_s_address_can_be_given_if_it_moved(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    service = serve(monkeypatch, lambda body: {"reply": "ok", "actions": []})
    app.do("ai_key_set", provider="muse", key="k")
    app.do("settings_set", key="llm", value={"provider": "muse", "model": "muse-spark-1.3",
                                             "base_url": "https://graph.meta.ai/v2"})  # fmt: skip
    app.do("ask_claude", text="anything")
    assert service.seen[0]["url"] == "https://graph.meta.ai/v2/chat/completions"
    assert "preview" in app.do("inbox")["llm"]["note"]


def test_switching_between_named_services_forgets_the_other_s_model(app: App) -> None:
    app.do("settings_set", key="llm", value={"provider": "grok", "model": "grok-4.6"})
    app.do("settings_set", key="llm", value={"provider": "gemini"})
    assert app.do("settings")["llm"]["model"] == ""  # grok's name doesn't run on Gemini
    app.do("settings_set", key="llm", value={"provider": "openai"})
    assert app.do("settings")["llm"]["model"] == "gpt-5"


def test_the_app_is_told_apart_whether_a_key_is_saved_and_whether_the_ai_can_be_asked(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 28 Oct: with Claude Code installed and no key, the app said "A key is saved": the two were one flag.
    monkeypatch.setattr(llm, "cli_path", lambda: Path("/usr/local/bin/claude"))
    state = app.do("inbox")["llm"]
    assert (state["ready"], state["key"], state["cli"]) == (True, False, True)
    app.do("ai_key_set", provider="claude", key="sk-ant-x")
    state = app.do("inbox")["llm"]
    assert (state["ready"], state["key"]) == (True, True)
