"""Every test runs away from your own files and keys: `friday.toml` points into a temporary folder, no Anthropic key
is visible and the `claude` command isn't found, so nothing reads your config or calls the AI."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def no_personal_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("FRIDAY_CONFIG", str(folder / "friday.toml"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("friday.ingest.llm.cli_path", lambda: None)
    return folder
