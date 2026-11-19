"""Friday's port taken by another app (19 Nov, a client's screenshot: "Friday's server isn't running. Another app is
using Friday's port ... [Errno 48] ... address already in use"; you: "lets do that", "test this thoroughly w edge
cases"). The Mac app now moves Friday to a free port (Mac/Sources/PortChoice.swift, tested in Mac/Tests); here, the
server's side for real: the error as the client saw it, fridayd on the port it's given, and the three that must
follow it there: the `friday` command (its cli.toml), the AI's connection (`fridayd mcp`) and pairing your phone
(both read the `server.port` setting the app sets). Spare ports only, never 8765."""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from friday.core.db import connect
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app
from tests.system.test_beat_plan_system import REPO, free_port


def fridayd(data: Path, port: int) -> subprocess.Popen:
    env = os.environ | {"PYTHONPATH": f"{REPO / 'src'}:{REPO}", "FRIDAY_CONFIG": str(data / "friday.toml")}
    return subprocess.Popen(
        [sys.executable, "-m", "friday.server.main", "--data-dir", str(data), "serve", "--port", str(port)],
        env=env, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )  # fmt: skip


@pytest.fixture
def held() -> Iterator[int]:
    """A spare port held by "another app" (Anki's AnkiConnect, say): listening, never answering as Friday."""
    other = socket.socket()
    other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    other.bind(("127.0.0.1", 0))
    other.listen(5)
    yield other.getsockname()[1]
    other.close()


def test_the_clients_error_another_app_on_the_port_stops_fridayd_starting(tmp_path: Path, held: int) -> None:
    """The reproduction: what the client's screen showed under "What it said"."""
    started = fridayd(tmp_path / "data", held)
    out, _ = started.communicate(timeout=120)
    assert started.returncode != 0
    assert "address already in use" in out and str(held) in out


def test_on_the_port_its_given_it_answers_there(tmp_path: Path, held: int) -> None:
    moved = free_port()
    started = fridayd(tmp_path / "data", moved)
    try:
        for _ in range(240):
            try:
                if httpx.get(f"http://127.0.0.1:{moved}/api/q/status", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise AssertionError("fridayd didn't answer on the port it was given")
        with pytest.raises(httpx.HTTPError):
            httpx.get(f"http://127.0.0.1:{held}/api/q/status", timeout=2)  # the other app's port isn't Friday's
    finally:
        started.terminate()
        started.wait(15)


def test_the_friday_command_follows_its_cli_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from friday.cli import main

    monkeypatch.delenv("FRIDAY_SERVER", raising=False)
    monkeypatch.setattr(main, "CONFIG", tmp_path / "cli.toml")
    assert main.server() == "http://localhost:8765"  # no file: 8765
    (tmp_path / "cli.toml").write_text('server = "http://127.0.0.1:8766"\n')  # as the Mac app writes it
    assert main.server() == "http://127.0.0.1:8766"


def test_the_ais_connection_and_phone_pairing_read_the_port_the_app_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app: App = new_app(tmp_path)
    server = app.do("settings")["server"]
    app.do("settings_set", key="server", value=server | {"port": 8766})  # as the Mac app sets it once running
    assert load_settings(connect(tmp_path / "friday.db"))["server"].port == 8766  # `fridayd mcp` reads this
    from friday.sync import tailnet

    monkeypatch.setattr(tailnet, "name", lambda: "mac.tailnet.ts.net")  # this Mac on Tailscale, for the test
    app.do("phone_set", on=True)
    assert app.do("phone_pair")["url"].startswith("http://mac.tailnet.ts.net:8766/pair#")
