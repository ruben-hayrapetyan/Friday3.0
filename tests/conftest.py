"""Every test runs away from your own files and keys: `friday.toml` points into a temporary folder, no Anthropic key
is visible, the `claude` command isn't found and Google's sign-in page never opens, so nothing reads your config,
calls the AI or reaches Google."""

from pathlib import Path
from typing import Any

import pytest


def no_google_page(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("tests don't open Google's sign-in page; fake google_auth.login instead")


@pytest.fixture(autouse=True)
def no_personal_config(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path_factory.mktemp("config")
    monkeypatch.setenv("FRIDAY_CONFIG", str(folder / "friday.toml"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("friday.ingest.llm.cli_path", lambda: None)
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.run_local_server", no_google_page)
    return folder
