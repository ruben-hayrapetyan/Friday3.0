"""The M5 gate (DESIGN §26): a scripted day through the CLI against a running daemon, where cancel and undo work.

The daemon is the real app on uvicorn, with its solver worker process and job loop, on a clock the script moves.
The CLI runs in-process but talks to it over HTTP like any terminal would.
"""

import contextlib
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from typer.testing import CliRunner

from friday.cli.main import app as cli
from friday.core.time import parse_local, to_utc
from friday.server.app import create_app
from tests.commands.helpers import TZ, new_app

SMALL = {"chains": 2, "step_budgets": [{"max_items": 1000, "cold": 40_000, "warm": 20_000}], "repair_steps": 50_000}
HUGE = SMALL | {"step_budgets": [{"max_items": 1000, "cold": 2_000_000_000, "warm": 2_000_000_000}]}


class Clock:
    def __init__(self, local: str):
        self.at(local)

    def at(self, local: str) -> None:
        self.now = to_utc(parse_local(local), TZ)

    def __call__(self) -> int:
        return self.now


@dataclass
class Daemon:
    url: str
    clock: Clock
    services: Any
    events: list[str]

    def friday(self, *args: str, code: int = 0) -> str:
        result = CliRunner().invoke(cli, list(args), env={"FRIDAY_SERVER": self.url})
        assert result.exit_code == code, result.output
        return result.output

    def data(self, *args: str) -> Any:
        return json.loads(self.friday(*args, "--json"))


def wait_for(condition: Callable[[], Any], timeout_s: float = 60) -> Any:
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        if found := condition():
            return found
        time.sleep(0.05)
    raise AssertionError("timed out")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listen(url: str, into: list[str]) -> None:
    # The server drops the stream when it stops; that ends this thread.
    with contextlib.suppress(httpx.HTTPError), httpx.stream("GET", f"{url}/events", timeout=None) as response:
        for line in response.iter_lines():
            if line.startswith("event: "):
                into.append(line.removeprefix("event: "))


@pytest.fixture
def daemon(tmp_path: Path) -> Iterator[Daemon]:
    new_app(tmp_path, now="2026-10-19T08:00", horizon_days=3).do("settings_set", key="engine", value=SMALL)
    clock = Clock("2026-10-19T08:00")
    served = create_app(tmp_path / "friday.db", clock=clock, plugin_dir=tmp_path / "rules")
    server = uvicorn.Server(uvicorn.Config(served, port=free_port(), log_level="warning", timeout_graceful_shutdown=1))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for(lambda: server.started)
    url = f"http://127.0.0.1:{server.config.port}"
    events: list[str] = []
    threading.Thread(target=listen, args=(url, events), daemon=True).start()
    yield Daemon(url, clock, served.state.services, events)
    server.should_exit = True
    thread.join(15)


def settled(d: Daemon) -> dict[str, Any]:
    """Wait until the saved plan has seen every command."""
    return wait_for(lambda: (s := d.data("status"))["plan_generation"] == s["generation"] and s)


def test_a_scripted_day(daemon: Daemon) -> None:
    d = daemon
    d.friday("settings-set", "planner", '{"debounce_s": 0.2}')

    # 08:00: the morning's list, with instant ghosts and then a plan from the worker.
    added = d.friday("add", "PS5 #cs due tue 5pm ~3h")
    assert added.startswith("Added T") and "undo: friday undo C" in added and "Probably " in added
    d.friday("add", "lecture at mon 2pm for 75m")
    d.friday("add", "laundry ~1h")
    assert "Plan P" in d.friday("replan")
    plan = d.data("plan")
    ps5 = next(b for b in plan["blocks"] if b["title"] == "PS5")
    assert "PS5" in d.friday("plan") and ("Now" in d.friday("now") or "Next" in d.friday("now"))
    short = f"T{ps5['item_id']}@{parse_local(ps5['start']):%a%H:%M}"
    assert "Due Tue 20 Oct 17:00" in d.friday("why", short)

    # 09:00–10:30: a timer session counts as progress.
    d.clock.at("2026-10-19T09:00")
    d.friday("start", "T1")
    d.clock.at("2026-10-19T10:30")
    d.friday("stop")
    assert d.data("item", "T1")["item"]["remaining_min"] == 90

    # A pin, undone by its command id.
    pinned = d.data("pin", "T3", "mon 16:00", "--kind", "locked")
    d.friday("undo", f"C{pinned['command_id']}")
    assert next(e for e in d.data("log-list") if e["id"] == pinned["command_id"])["undone_by"]

    # Lunch: shove half an hour.
    d.clock.at("2026-10-19T12:00")
    assert d.data("shove", "30m")["result"]["created"]

    # Cancel: a solve with an enormous budget is stopped by the next change, whose plan arrives promptly.
    d.friday("settings-set", "engine", json.dumps(HUGE))
    stale = wait_for(lambda: d.services.supervisor.job)
    began = time.monotonic()
    d.friday("settings-set", "engine", json.dumps(SMALL))
    settled(d)
    assert stale.cancelled and time.monotonic() - began < 30

    # 22:00: the review, then done and an undo of it.
    d.clock.at("2026-10-19T22:00")
    assert d.friday("review").startswith("Review of 2026-10-19")
    assert "Reviewed" in d.friday("review-submit", "--entries", "[]")
    done = d.data("done", "T3")
    assert done["result"]["item"]["status"] == "done"
    d.friday("undo", f"C{done['command_id']}")
    assert d.data("item", "T3")["item"]["status"] == "todo"
    settled(d)
    assert {"items.changed", "plan.provisional", "plan.changed"} <= set(d.events)


def test_exit_codes(daemon: Daemon) -> None:
    assert "no item T999" in daemon.friday("done", "T999", code=1)
    daemon.url = f"http://127.0.0.1:{free_port()}"
    assert "can't reach Friday" in daemon.friday("status", code=2)


def test_a_server_failure_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(500, text="boom"))
    result = CliRunner().invoke(cli, ["status"])
    assert result.exit_code == 3 and "Friday failed (500)" in result.output
