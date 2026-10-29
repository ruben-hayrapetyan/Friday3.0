"""Friday's AI on OpenAI, or any service that speaks OpenAI's chat API (28 Oct: "check whether friday only works with
claude or whether it is compatible with OpenAI, or any other agent"). `OpenAIClient` takes the requests every part of
Friday makes (Anthropic's messages API: a system prompt, text, PDFs and images, an answer held to a JSON schema) to
the chat API and brings the answer back the same way. These run against a stand-in service (httpx's MockTransport):
nothing reaches the network."""

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from friday.commands.fetching import provider_down
from friday.core.integrations import LlmSettings
from friday.ingest import llm
from friday.ingest.llm import AIError, APIConnectionError, APITimeoutError, OpenAIClient

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def chat(text: str, prompt_tokens: int = 120, completion_tokens: int = 30, finish: str = "stop") -> dict[str, Any]:
    return {
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


class Service:
    """A stand-in chat API: each request kept, each answer the next of `answers` (a reply, a status and body, or an
    exception to raise)."""

    def __init__(self, *answers: Any) -> None:
        self.answers, self.seen = list(answers), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(
            {"url": str(request.url), "headers": dict(request.headers), "body": json.loads(request.content)}
        )
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, tuple):
            return (
                httpx.Response(answer[0], json=answer[1])
                if not isinstance(answer[1], str)
                else httpx.Response(answer[0], text=answer[1])
            )
        return httpx.Response(200, json=answer)


def client(
    service: Service, flavor: str = "openai", key: str | None = "sk-test", url: str = "https://api.openai.com/v1"
) -> OpenAIClient:
    return OpenAIClient(url, key, flavor, transport=httpx.MockTransport(service))


def ask(c: OpenAIClient, content: Any, schema: dict | None = SCHEMA, **extra: Any) -> Any:
    request: dict[str, Any] = {
        "model": "gpt-5",
        "max_tokens": 900,
        "system": "You read syllabi.",
        "messages": [{"role": "user", "content": content}],
    }
    if schema is not None:
        request["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    return c.messages.create(**request | extra)


# The request, as the chat API takes it.


def test_a_request_goes_as_the_chat_api_takes_it() -> None:
    service = Service(chat('{"ok": true}'))
    reply = ask(client(service), [{"type": "text", "text": "PS1 due Friday"}])
    (sent,) = service.seen
    assert sent["url"] == "https://api.openai.com/v1/chat/completions"
    assert sent["headers"]["authorization"] == "Bearer sk-test"
    body = sent["body"]
    assert body["model"] == "gpt-5" and body["max_completion_tokens"] == 900 and "max_tokens" not in body
    assert body["messages"] == [
        {"role": "system", "content": "You read syllabi."},
        {"role": "user", "content": "PS1 due Friday"},
    ]
    assert body["response_format"] == {"type": "json_schema", "json_schema": {"name": "answer", "schema": SCHEMA}}
    assert reply.content[0].type == "text" and json.loads(reply.content[0].text) == {"ok": True}
    assert (reply.usage.input_tokens, reply.usage.output_tokens) == (120, 30)


def test_another_service_gets_max_tokens_and_no_key_when_it_has_none() -> None:
    service = Service(chat('{"ok": true}'))
    ask(client(service, "compatible", key=None, url="http://localhost:11434/v1/"), "hello")
    (sent,) = service.seen
    assert sent["url"] == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in sent["headers"]
    assert sent["body"]["max_tokens"] == 900 and "max_completion_tokens" not in sent["body"]


def test_several_text_blocks_go_as_one_text() -> None:
    service = Service(chat('{"ok": true}'))
    ask(client(service), [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}])
    assert service.seen[0]["body"]["messages"][1]["content"] == "one\n\ntwo"


def test_an_image_goes_as_a_data_url_beside_the_text() -> None:
    service = Service(chat('{"ok": true}'))
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0K"}}
    ask(client(service), [image, {"type": "text", "text": "What's due?"}])
    content = service.seen[0]["body"]["messages"][1]["content"]
    assert content == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0K"}},
        {"type": "text", "text": "What's due?"},
    ]


PDF = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "JVBERi0xLjQ="}}


def test_a_pdf_goes_to_openai_as_a_file() -> None:
    service = Service(chat('{"ok": true}'))
    ask(client(service), [PDF])
    (part,) = service.seen[0]["body"]["messages"][1]["content"]
    assert part == {
        "type": "file",
        "file": {"filename": "document.pdf", "file_data": "data:application/pdf;base64,JVBERi0xLjQ="},
    }


def test_a_pdf_goes_to_another_service_as_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "pdf_text", lambda data: "CHEM 2090 PS3 due Oct 30" if data == b"%PDF-1.4" else None)
    service = Service(chat('{"ok": true}'))
    ask(client(service, "compatible"), [PDF, {"type": "text", "text": "Read it"}])
    assert service.seen[0]["body"]["messages"][1]["content"] == (
        "The attached PDF, as text:\n\nCHEM 2090 PS3 due Oct 30\n\nRead it"
    )


def test_a_scanned_pdf_another_service_cant_read_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "pdf_text", lambda data: None)
    service = Service(chat('{"ok": true}'))
    with pytest.raises(RuntimeError, match="can't be handed a PDF"):
        ask(client(service, "compatible"), [PDF])
    assert service.seen == []  # nothing was sent


def test_a_plain_request_asks_for_no_format() -> None:
    service = Service(chat("Hello"))
    reply = ask(client(service), "hi", schema=None)
    assert "response_format" not in service.seen[0]["body"] and reply.content[0].text == "Hello"


# The answer.


@pytest.mark.parametrize(
    "said",
    [
        '{"ok": true}',
        '```json\n{"ok": true}\n```',
        '```\n{"ok": true}\n```',
        'Here it is: {"ok": true}. Anything else?',
        '  \n{"ok": true}\n',
    ],
)
def test_the_json_is_taken_out_of_what_the_service_says(said: str) -> None:
    reply = ask(client(Service(chat(said))), "hi")
    assert json.loads(reply.content[0].text) == {"ok": True}


def test_an_answer_with_no_json_is_an_error() -> None:
    with pytest.raises(ValueError, match="wasn't JSON"):
        ask(client(Service(chat("I can't help with that."))), "hi")


def test_a_refusal_an_empty_answer_and_running_out_of_room_are_errors() -> None:
    declined = {"choices": [{"message": {"role": "assistant", "content": None, "refusal": "Not allowed"}}]}
    with pytest.raises(RuntimeError, match="declined: Not allowed"):
        ask(client(Service(declined)), "hi")
    with pytest.raises(RuntimeError, match="answered with nothing"):
        ask(client(Service({"choices": []})), "hi")
    with pytest.raises(RuntimeError, match="ran out of room"):
        ask(client(Service(chat("", finish="length"))), "hi")


def test_content_given_as_parts_is_joined() -> None:
    parts = {
        "choices": [{"message": {"content": [{"type": "text", "text": '{"ok":'}, {"type": "text", "text": " true}"}]}}]
    }
    assert json.loads(ask(client(Service(parts)), "hi").content[0].text) == {"ok": True}


def test_missing_usage_counts_as_none_spent() -> None:
    reply = ask(client(Service({"choices": [{"message": {"content": '{"ok": true}'}}]})), "hi")
    assert (reply.usage.input_tokens, reply.usage.output_tokens) == (0, 0)


# A service without JSON schemas.


def test_a_service_without_json_schemas_is_asked_for_json_in_words() -> None:
    refused = (400, {"error": {"message": "response_format json_schema is not supported by this model"}})
    service = Service(refused, chat('{"ok": true}'))
    reply = ask(client(service, "compatible"), "hi")
    first, second = (s["body"] for s in service.seen)
    assert first["response_format"]["type"] == "json_schema"
    assert second["response_format"] == {"type": "json_object"}
    assert "matching this JSON Schema" in second["messages"][0]["content"]
    assert json.dumps(SCHEMA) in second["messages"][0]["content"]
    assert json.loads(reply.content[0].text) == {"ok": True}


def test_and_one_without_a_json_mode_is_asked_with_no_format_at_all() -> None:
    refused = (400, {"error": {"message": "response_format is not supported"}})
    service = Service(refused, refused, chat('Sure! {"ok": true}'))
    reply = ask(client(service, "compatible"), "hi")
    assert len(service.seen) == 3 and "response_format" not in service.seen[2]["body"]
    assert json.loads(reply.content[0].text) == {"ok": True}


def test_a_refusal_about_something_else_is_not_asked_again() -> None:
    service = Service((400, {"error": {"message": "This model's maximum context length is 8192 tokens"}}))
    with pytest.raises(AIError, match="context length") as raised:
        ask(client(service, "compatible"), "hi")
    assert raised.value.status_code == 400 and len(service.seen) == 1


def test_three_refusals_about_the_format_end_with_the_last() -> None:
    refused = (422, {"error": {"message": "response_format: unsupported"}})
    service = Service(refused)
    with pytest.raises(AIError):
        ask(client(service, "compatible"), "hi")
    assert len(service.seen) == 3


# What goes wrong, said as Friday's own outages are.


@pytest.mark.parametrize(
    ("answer", "status", "down"),
    [
        ((401, {"error": {"message": "Incorrect API key provided"}}), 401, True),
        ((403, {"error": {"message": "Forbidden"}}), 403, True),
        ((404, {"error": {"message": "The model `gpt-9` does not exist"}}), 404, True),
        ((429, {"error": {"message": "Rate limit reached"}}), 429, True),
        ((500, {"error": {"message": "Server error"}}), 500, True),
        ((503, "Service Unavailable"), 503, True),
        ((400, {"error": {"message": "Invalid image data"}}), 400, False),
    ],
)
def test_a_refusal_carries_its_status_and_an_outage_reads_as_one(answer: tuple, status: int, down: bool) -> None:
    with pytest.raises(AIError) as raised:
        ask(client(Service(answer)), "hi", schema=None)
    assert raised.value.status_code == status and provider_down(raised.value) is down
    said = answer[1] if isinstance(answer[1], str) else answer[1]["error"]["message"]
    assert said in str(raised.value)


def test_an_unreachable_service_and_a_slow_one_are_outages() -> None:
    with pytest.raises(APIConnectionError, match="Couldn't reach") as raised:
        ask(client(Service(httpx.ConnectError("refused"))), "hi")
    assert provider_down(raised.value)
    with pytest.raises(APITimeoutError) as slow:
        ask(client(Service(httpx.ReadTimeout("slow"))), "hi")
    assert provider_down(slow.value)


def test_an_answer_that_isnt_json_from_the_service_is_an_error() -> None:
    with pytest.raises(AIError, match="wasn't JSON"):
        ask(client(Service((200, "<html>proxy login</html>"))), "hi")


# Which AI, which key.


def secrets(folder: Any, text: str) -> None:
    (folder / "secrets.toml").write_text(text)


def test_the_provider_chosen_decides_the_client(no_personal_config: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    assert llm.client(LlmSettings()) is None  # Claude, with neither the command nor a key (conftest)
    assert llm.client(LlmSettings(provider="openai")) is None  # no key
    assert llm.client(LlmSettings(provider="compatible")) is None  # no address
    secrets(no_personal_config, '[openai]\napi_key = "sk-file"\n')
    openai = llm.client(LlmSettings(provider="openai"))
    assert isinstance(openai, OpenAIClient) and openai.key == "sk-file" and openai.flavor == "openai"
    assert openai.url == "https://api.openai.com/v1/chat/completions"
    local = llm.client(LlmSettings(provider="compatible", base_url="http://localhost:11434/v1", model="llama3.1"))
    assert isinstance(local, OpenAIClient) and local.key is None and local.flavor == "compatible"
    monkeypatch.setenv("FRIDAY_AI_KEY", "or-env")
    openrouter = LlmSettings(provider="compatible", base_url="https://openrouter.ai/api/v1", model="meta/llama-4")
    assert llm.client(openrouter).key == "or-env"
    assert llm.client(LlmSettings(provider="compatible", base_url="https://openrouter.ai/api/v1")) is None  # no model


def test_a_key_in_secrets_toml_wins_over_one_in_the_shell(
    no_personal_config: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert llm.key_source("openai") == ("sk-env", "OPENAI_API_KEY")
    secrets(no_personal_config, '[openai]\napi_key = " sk-file "\n')
    assert llm.key_source("openai") == ("sk-file", "secrets.toml")
    assert llm.key_source("claude") == (None, "ANTHROPIC_API_KEY")  # each provider its own


def test_what_the_app_is_told_of_the_ai(no_personal_config: Any) -> None:
    claude = llm.describe(LlmSettings())
    assert (claude["name"], claude["ready"], claude["cli"]) == ("Claude", False, False)
    assert "Anthropic API key" in claude["why"]
    openai = llm.describe(LlmSettings(provider="openai"))
    assert (openai["name"], openai["ready"]) == ("GPT", False) and "OpenAI API key" in openai["why"]
    secrets(no_personal_config, '[openai]\napi_key = "sk-file"\n')
    assert llm.describe(LlmSettings(provider="openai"))["ready"] is True
    other = llm.describe(LlmSettings(provider="compatible", base_url="http://localhost:1234/v1", model="qwen"))
    assert (other["name"], other["ready"], other["key"], other["why"]) == ("AI", True, False, None)
    assert other["base_url"] == "http://localhost:1234/v1"


# The settings.


def test_switching_provider_brings_its_models_and_keeps_ones_you_named() -> None:
    assert (LlmSettings(provider="openai").model, LlmSettings(provider="openai").small_model) == ("gpt-5", "gpt-5-mini")
    named = LlmSettings(provider="openai", model="gpt-4.1")
    assert (named.model, named.small_model) == ("gpt-4.1", "gpt-5-mini")
    back = LlmSettings.model_validate({"provider": "claude", "model": "gpt-5", "small_model": "gpt-5-mini"})
    assert (back.model, back.small_model) == ("claude-sonnet-5-5", "claude-haiku-5-5")
    local = LlmSettings(provider="compatible", base_url="http://localhost:11434/v1", model="llama3.1")
    assert local.small_model == "llama3.1"  # one model, unless you name a second
    assert LlmSettings(provider="compatible", base_url="http://x/v1", model="a", small_model="b").small_model == "b"


@pytest.mark.parametrize("url", ["localhost:11434", "ftp://x", "file:///etc/passwd", "javascript:alert(1)"])
def test_a_service_address_must_be_http(url: str) -> None:
    with pytest.raises(ValueError, match="http:// or https://"):
        LlmSettings(provider="compatible", base_url=url)


def test_a_blank_address_is_none() -> None:
    assert LlmSettings(provider="compatible", base_url="  ").base_url is None


def make(answer: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=chat(json.dumps(answer)))


def test_base64_pdf_content_is_passed_through_unchanged() -> None:
    data = base64.b64encode(b"%PDF-1.4 a syllabus").decode()
    service = Service(chat('{"ok": true}'))
    ask(
        client(service),
        [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}],
    )
    assert service.seen[0]["body"]["messages"][1]["content"][0]["file"]["file_data"].endswith(data)
