"""Which Anthropic key Friday uses: secrets.toml, written for Friday, over a variable left in a shell."""

from pathlib import Path

import pytest

from friday.ingest import llm


def test_secrets_toml_wins_over_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "secrets.toml").write_text('[anthropic]\napi_key = " sk-ant-file "\n')
    monkeypatch.setenv("FRIDAY_CONFIG", str(tmp_path / "friday.toml"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-shell")
    assert llm.key_source() == ("sk-ant-file", "secrets.toml")


def test_the_environment_is_the_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_CONFIG", str(tmp_path / "friday.toml"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-shell")
    assert llm.key_source() == ("sk-ant-shell", "ANTHROPIC_API_KEY")


def test_friday_can_be_told_there_is_no_claude_command_or_another(tmp_path) -> None:  # noqa: ANN001
    # A fresh user without Claude (scripts/fresh_user.sh --no-claude): no command, whatever is installed here.
    from friday.ingest.llm import named_cli

    assert named_cli("none") is None and named_cli("") is None
    named = tmp_path / "claude"
    named.write_text("#!/bin/sh\n")
    named.chmod(0o755)
    assert named_cli(str(named)) == named
    assert named_cli(str(tmp_path / "missing")) is None
