"""The AI's smaller edges: finding a command on the PATH, why there's no AI to ask in words for each provider, the
models a service lists (or can't), and a PDF with no tool to read it. Nothing reaches the network: services answer
through httpx's MockTransport and Ollama is on a closed port (conftest)."""

from pathlib import Path
from typing import Any

import httpx
import pytest

from friday.core.integrations import LlmSettings
from friday.ingest import llm, local_models
from friday.ingest.llm import AIError, APIConnectionError

REAL_CLI_PATH = llm.cli_path  # conftest hides every AI command; these look for one as Friday does


def test_the_claude_command_is_found_on_the_path_when_not_in_the_usual_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "CANDIDATES", ())
    monkeypatch.setattr(llm.shutil, "which", lambda name: f"/somewhere/bin/{name}")
    assert REAL_CLI_PATH() == Path("/somewhere/bin/claude")
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    assert REAL_CLI_PATH() is None


def test_a_providers_command_is_found_on_the_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "FOLDERS", ())
    monkeypatch.setattr(llm.shutil, "which", lambda name: "/elsewhere/agy" if name == "agy" else None)
    assert llm.command(("gemini", "agy"), "FRIDAY_GEMINI") == Path("/elsewhere/agy")
    assert llm.command(("codex",), "FRIDAY_CODEX") is None


def test_a_model_on_this_mac_needs_one_chosen_and_ollama_running() -> None:
    assert llm.missing(LlmSettings(provider="local")).startswith("Choose an open model to run on this Mac")
    assert llm.missing(LlmSettings(provider="local", model="llama3.1")).startswith("Ollama isn't running")


def test_a_model_still_downloading_says_how_far_it_has_come(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_models.Ollama, "models", lambda self: {})
    job = local_models.Download("llama3.1:latest", completed=25, total=100)
    monkeypatch.setattr(local_models.DOWNLOADS, "current", job)
    assert llm.missing(LlmSettings(provider="local", model="llama3.1")) == "llama3.1 is still downloading (25%)"
    job.total = 0  # Ollama hasn't said its size yet
    assert llm.missing(LlmSettings(provider="local", model="llama3.1")) == "llama3.1 is still downloading"
    job.status = "done"
    assert "isn't on this Mac yet" in llm.missing(LlmSettings(provider="local", model="llama3.1"))


def test_another_service_needs_its_address_and_then_its_model() -> None:
    assert llm.missing(LlmSettings(provider="compatible")).startswith("No address for the AI service")
    named = LlmSettings(provider="compatible", base_url="http://localhost:1234/v1")
    assert llm.missing(named).startswith("Name the model the service runs")


def test_claudes_models_are_its_own_list_and_a_service_without_an_address_has_none() -> None:
    assert llm.models_of(LlmSettings()) == list(llm.PROVIDERS["claude"].models or ())
    assert llm.models_of(LlmSettings(provider="compatible")) == []


def service(answer: Any) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.MockTransport(respond)


def test_a_services_models_are_its_list_by_name() -> None:
    listed = httpx.Response(200, json={"data": [{"id": "models/b"}, {"id": "a"}, {"id": ""}, "odd", {"id": "a"}]})
    settings = LlmSettings(provider="compatible", base_url="http://localhost:1234/v1")
    assert llm.models_of(settings, service(listed)) == ["a", "b"]


@pytest.mark.parametrize("answer", [httpx.Response(200, text="not json"), httpx.Response(200, json=["a", "b"])])
def test_a_list_that_isnt_the_usual_json_is_no_models(answer: httpx.Response) -> None:
    settings = LlmSettings(provider="compatible", base_url="http://localhost:1234/v1")
    assert llm.models_of(settings, service(answer)) == []


def test_a_service_that_cant_be_reached_or_refuses_says_so() -> None:
    settings = LlmSettings(provider="compatible", base_url="http://localhost:1234/v1")
    with pytest.raises(APIConnectionError, match="Couldn't reach http://localhost:1234/v1"):
        llm.models_of(settings, service(httpx.ConnectError("refused")))
    with pytest.raises(AIError):
        llm.models_of(settings, service(httpx.Response(401, json={"error": {"message": "bad key"}})))


def test_a_pdf_has_no_text_without_pdftotext_or_without_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "pdftotext_path", lambda: None)
    assert llm.pdf_text(b"%PDF-1.4") is None
    monkeypatch.setattr(llm, "pdftotext_path", lambda: Path("/usr/bin/true"))
    assert llm.pdf_text(b"") is None


def test_a_provider_with_its_own_models_fills_in_one_left_blank() -> None:
    blank = LlmSettings(provider="openai", model="", small_model="")
    assert (blank.model, blank.small_model) == ("gpt-5", "gpt-5-mini")


def test_a_providers_address_is_yours_else_its_own() -> None:
    assert LlmSettings(provider="openai").address == "https://api.openai.com/v1"
    assert LlmSettings(provider="compatible", base_url="http://localhost:1234/v1").address == "http://localhost:1234/v1"
