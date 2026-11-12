"""Glass box on finding this Mac on the tailnet (sync/tailnet.py) from what the system says: a command that isn't
here or doesn't answer in time says nothing, and the address and name come from ifconfig and Tailscale's status."""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from friday.sync import tailnet


def test_a_command_that_isnt_here_says_nothing() -> None:
    assert tailnet.run("friday-no-such-command-here") == ""


def test_a_command_that_doesnt_answer_in_time_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(command: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)
    assert tailnet.run("tailscale", "status", "--json") == ""


def test_with_tailscale_off_there_is_no_address_or_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tailnet, "run", lambda *command: "")
    monkeypatch.setattr(tailnet, "cli", lambda: None)
    assert tailnet.address() is None and tailnet.name() is None


def test_the_address_and_name_are_read_from_the_system_each_time(monkeypatch: pytest.MonkeyPatch) -> None:
    said = {
        ("ifconfig",): "",  # not on this system: `ip` instead
        ("ip", "-4", "addr"): "inet 127.0.0.1/8 scope host lo\n    inet 100.101.102.103/32 scope global tailscale0",
        ("/usr/bin/tailscale", "status", "--json"): '{"Self": {"DNSName": "mac.tailnet.ts.net."}}',
    }
    monkeypatch.setattr(tailnet, "run", lambda *command: said[command])
    monkeypatch.setattr(tailnet, "cli", lambda: "/usr/bin/tailscale")
    assert tailnet.address() == "100.101.102.103" and tailnet.name() == "mac.tailnet.ts.net"


def test_tailscale_is_found_on_the_path_else_in_its_app_else_not(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tailnet.shutil, "which", lambda tool: "/opt/homebrew/bin/tailscale")
    assert tailnet.cli() == "/opt/homebrew/bin/tailscale"
    monkeypatch.setattr(tailnet.shutil, "which", lambda tool: None)
    monkeypatch.setattr(tailnet, "APP_CLI", tmp_path / "Tailscale")
    assert tailnet.cli() is None
    (tmp_path / "Tailscale").touch()
    assert tailnet.cli() == str(tmp_path / "Tailscale")
