"""Every test runs away from your own files and keys: `friday.toml` points into a temporary folder, no AI service's
key is visible, no AI command (`claude`, `codex`, `agy`, `gemini`) is found, Ollama is looked for where nothing
answers and Google's sign-in page never opens, so nothing reads your config, calls an AI, downloads a model or reaches
Google."""

from pathlib import Path
from typing import Any

import pytest


def no_google_page(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("tests don't open Google's sign-in page; fake google_auth.login instead")


@pytest.fixture(autouse=True)
def no_personal_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("FRIDAY_CONFIG", str(folder / "friday.toml"))
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FRIDAY_AI_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "META_API_KEY",
                "FRIDAY_CLAUDE", "FRIDAY_CODEX", "FRIDAY_GEMINI"):  # fmt: skip
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:9")  # a closed port: a real Ollama here is never reached
    # No AI command is found: not claude, codex, agy or gemini (tests that want one hand in a fake).
    for found in ("cli_path", "codex_path", "gemini_path"):
        monkeypatch.setattr(f"friday.ingest.llm.{found}", lambda: None)
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.run_local_server", no_google_page)
    # the Mac app's own Google client, where a test puts one (an installed fridayd's would otherwise count)
    monkeypatch.setattr("friday.sync.google_auth.SHIPPED_CLIENT", folder / "shipped" / "google_client.json")
    return folder
