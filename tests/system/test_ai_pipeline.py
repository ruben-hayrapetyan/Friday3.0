"""Checking the AI (tests/features.toml: ai), the whole pipeline: a real `fridayd serve` with no AI at all, then with an
OpenAI-style service at an address you give, played here by a small server of the test's own on 127.0.0.1 that
answers each model as told: well, not as asked, or with an error. `ai_check` is sent over HTTP as Settings →
Integrations → AI's Check sends it, and what came back is read against what the service was asked."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tests.system.test_beat_plan_system import Friday

NO_AI = (
    "No AI: install Claude Code (the claude command), add an Anthropic API key, or choose another AI in"
    " Settings → Integrations → AI"
)


class Service:
    """An OpenAI-style chat service: `answers[model]` is (status, body) for that model; every request is kept."""

    def __init__(self) -> None:
        self.answers: dict[str, tuple[int, dict[str, Any]]] = {}
        self.asked: list[dict[str, Any]] = []
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 (http.server's name)
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                service.asked.append({"path": self.path, "body": body})
                status, answer = service.answers.get(body["model"], (404, {"error": {"message": "no such model"}}))
                data = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args: Any) -> None:
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}/v1"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.http.shutdown()
        self.http.server_close()


def says(text: str) -> tuple[int, dict[str, Any]]:
    usage = {"prompt_tokens": 12, "completion_tokens": 3}
    return 200, {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                 "usage": usage}  # fmt: skip


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("ai"))
    yield server
    server.stop()


@pytest.fixture(scope="module")
def service() -> Iterator[Service]:
    found = Service()
    yield found
    found.stop()


def use(friday: Friday, service: Service, model: str, small: str) -> None:
    friday.c("settings_set", key="llm", value={"provider": "compatible", "base_url": service.url, "model": model,
                                               "small_model": small})  # fmt: skip


def test_with_no_ai_each_model_says_what_to_do_and_isnt_ok(friday: Friday) -> None:
    checks = friday.q("ai_check")
    llm = friday.q("settings")["llm"]
    assert [(c["model"], c["job"]) for c in checks] == [
        (llm["model"], "Reads mail and documents"),
        (llm["small_model"], "Sorts what comes in"),
    ]
    assert all(c["ok"] is False and c["said"] == NO_AI for c in checks)


def test_a_service_with_no_model_named_says_to_name_one(friday: Friday, service: Service) -> None:
    friday.c("settings_set", key="llm", value={"provider": "compatible", "base_url": service.url, "model": "",
                                               "small_model": ""})  # fmt: skip
    checks = friday.q("ai_check")
    assert [c["said"] for c in checks] == ["Name the model the service runs in Settings → Integrations → AI"] * 2
    assert service.asked == []  # nothing was sent


def test_each_model_is_asked_for_a_one_word_answer_and_answering_is_ok(friday: Friday, service: Service) -> None:
    service.answers = {"big-model": says('{"ok": true}'), "small-model": says('Here: {"ok": true}')}
    use(friday, service, "big-model", "small-model")
    checks = friday.q("ai_check")
    assert [(c["model"], c["ok"], c["said"]) for c in checks] == [
        ("big-model", True, "Answered"),
        ("small-model", True, "Answered"),
    ]
    assert [a["body"]["model"] for a in service.asked] == ["big-model", "small-model"]
    assert all(a["path"] == "/v1/chat/completions" for a in service.asked)
    first = service.asked[0]["body"]
    assert first["messages"][0] == {"role": "system", "content": "Answer ok: true."}
    assert first["messages"][-1] == {"role": "user", "content": "Ping"}
    assert first["response_format"]["json_schema"]["schema"]["required"] == ["ok"]


def test_a_model_that_answers_otherwise_is_said_not_to_follow_instructions(friday: Friday, service: Service) -> None:
    service.answers = {"big-model": says('{"ok": true}'), "coder": says('{"ok": false}')}
    use(friday, service, "big-model", "coder")
    checks = {c["model"]: c for c in friday.q("ai_check")}
    assert checks["big-model"]["ok"] is True
    assert checks["coder"]["ok"] is False
    assert checks["coder"]["said"] == "Answered, but not as asked: it may not follow Friday's instructions well"


def test_a_service_error_is_shown_in_its_own_words_for_that_model_only(friday: Friday, service: Service) -> None:
    service.answers = {"big-model": says('{"ok": true}'),
                       "retired": (404, {"error": {"message": "The model retired-7 has been retired"}})}  # fmt: skip
    use(friday, service, "big-model", "retired")
    checks = {c["model"]: c for c in friday.q("ai_check")}
    assert checks["big-model"]["said"] == "Answered"
    assert checks["retired"]["ok"] is False and "has been retired" in checks["retired"]["said"]


def test_a_service_that_cant_be_reached_is_said_and_not_ok(friday: Friday) -> None:
    friday.c("settings_set", key="llm", value={"provider": "compatible", "base_url": "http://127.0.0.1:9/v1",
                                               "model": "m", "small_model": "m"})  # fmt: skip
    checks = friday.q("ai_check")
    assert len(checks) == 2 and all(not c["ok"] and c["said"] and c["said"] != "Answered" for c in checks)


def test_an_assistant_s_token_may_not_check_the_ai(friday: Friday) -> None:
    token = friday.c("token_add", name="ai-check-helper", scope="read-write")["token"]
    answer = friday.http.get("/api/q/ai_check", headers={"authorization": f"Bearer {token}"})
    assert answer.status_code == 422, answer.text
    assert answer.json()["message"].startswith("command: Only you can do that (ai_check), not an assistant")
