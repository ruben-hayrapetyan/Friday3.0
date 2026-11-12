"""The MCP tools beyond adding a task (server/mcp.py): queries read as the assistant, a refusal or an unknown tool
comes back as an error result the assistant reads, and `fridayd mcp` on stdio forwards each call to a running
daemon's HTTP API with its token (here a real server on a free port, and the stdio session fed from a string)."""

import io
import json
import socket
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
import uvicorn
from fastapi.testclient import TestClient

from friday.server import main as fridayd
from friday.server import mcp
from friday.server.app import create_app, query_by_get
from tests.commands.helpers import App, new_app

MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


@pytest.fixture
def client(app: App, tmp_path: Path) -> Iterator[TestClient]:
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served) as client:
        yield client


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def daemon(app: App, tmp_path: Path) -> Iterator[str]:
    """The HTTP API served for real on a free port, as `fridayd mcp` finds it running."""
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(served, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="test-daemon", daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        threading.Event().wait(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


def token(app: App, name: str, scope: str = "read-write") -> str:
    return app.do("token_add", name=name, scope=scope)["token"]


def call(client: TestClient, secret: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    reply = client.post("/mcp", json=body, headers=MCP_HEADERS | {"authorization": f"Bearer {secret}"})
    assert reply.status_code == 200, reply.text
    return reply.json()["result"]


def text(result: dict[str, Any]) -> Any:
    [content] = result["content"]
    return content["text"] if result["isError"] else json.loads(content["text"])


def test_a_query_tool_reads_as_the_assistant_and_a_preview_changes_nothing(app: App, client: TestClient) -> None:
    secret = token(app, "claude")
    previewed = call(client, secret, "add", {"text": "essay due wed 17:00 ~2h", "preview": True})
    assert text(previewed)["preview"] is True and app.table("items") == []
    call(client, secret, "add", {"text": "essay due wed 17:00 ~2h"})
    assert [i["title"] for i in text(call(client, secret, "items", {}))] == ["essay"]


def test_an_unknown_or_hidden_tool_is_an_error_the_assistant_reads(app: App, client: TestClient) -> None:
    secret = token(app, "claude")
    for name in ("no_such_tool", "token_add"):
        result = call(client, secret, name, {})
        assert result["isError"] and text(result) == f"no tool named {name}"
    assert [t["name"] for t in app.do("tokens")] == ["claude"]  # the hidden one never ran


def test_a_refused_change_says_why(app: App, client: TestClient) -> None:
    reader, writer = token(app, "dashboard", "read"), token(app, "claude")
    refused = call(client, reader, "add", {"text": "essay ~2h"})
    assert refused["isError"] and text(refused) and app.table("items") == []
    missing = call(client, writer, "edit", {"id": 99, "title": "x"})
    assert missing["isError"] and "T99" in text(missing)


def test_stdio_calls_go_to_the_daemon_as_get_post_and_command(app: App, daemon: str) -> None:
    forward = mcp.forward(daemon, token(app, "claude"), query_by_get)

    async def calls() -> list[Any]:
        added = await forward("add", {"text": "essay due wed 17:00 ~2h"}, None)
        previewed = await forward("add", {"text": "laundry ~1h", "preview": True}, None)
        listed = await forward("items", {"text": "ess"}, None)  # a GET with query parameters
        await forward("replan", {}, None)
        weighed = await forward("preview_weights", {"weights": {"spread": 2}}, None)  # a POST: it has a mapping
        return [added, previewed, listed, weighed]

    added, previewed, listed, weighed = anyio.run(calls)
    assert added["result"]["item"]["title"] == "essay" and previewed["preview"] is True
    assert [i["title"] for i in listed] == ["essay"] and "rule_totals_after" in weighed
    assert [r["actor"] for r in app.table("command_log") if r["command"] == "add"] == ["mcp:claude"]


def test_stdio_says_the_daemons_refusal(app: App, daemon: str) -> None:
    reader = mcp.forward(daemon, token(app, "dashboard", "read"), query_by_get)
    with pytest.raises(RuntimeError) as refused:
        anyio.run(reader, "add", {"text": "essay ~2h"}, None)
    assert str(refused.value)
    stranger = mcp.forward(daemon, "not-a-token", query_by_get)
    with pytest.raises(RuntimeError, match="token"):
        anyio.run(stranger, "items", {}, None)


def test_stdio_needs_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="FRIDAY_TOKEN"):
        mcp.serve_stdio(8765, query_by_get)


def rpc(number: int, method: str, params: dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": number, "method": method, "params": params})


class Assistant:
    """Both ends of a stdio session: says each line in turn, then waits for the answer to the last before hanging up
    (a closed stdin ends the session, cancelling what is still being answered)."""

    def __init__(self, *lines: str) -> None:
        self.lines, self.heard = lines, io.StringIO()
        self.last = json.loads(lines[-1])["id"]

    def answers(self) -> dict[int, Any]:
        return {a["id"]: a for a in map(json.loads, self.heard.getvalue().splitlines()) if "id" in a}

    async def __aiter__(self) -> AsyncIterator[str]:
        for line in self.lines:
            yield line + "\n"
        with anyio.fail_after(60):
            while self.last not in self.answers():
                await anyio.sleep(0.02)

    async def write(self, data: str) -> None:
        self.heard.write(data)

    async def flush(self) -> None:
        pass


def test_an_assistant_session_on_stdio_lists_the_tools_and_adds_a_task(
    app: App, daemon: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    hello = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}
    assistant = Assistant(
        rpc(1, "initialize", hello),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        rpc(2, "tools/list", {}),
        rpc(3, "tools/call", {"name": "add", "arguments": {"text": "essay due wed 17:00 ~2h"}}),
    )
    real = mcp.stdio_server
    monkeypatch.setattr(mcp, "stdio_server", lambda: real(assistant, assistant))  # type: ignore[arg-type]
    monkeypatch.setenv("FRIDAY_TOKEN", token(app, "claude"))
    monkeypatch.setenv("FRIDAY_SERVER", daemon)
    mcp.serve_stdio(1, query_by_get)  # FRIDAY_SERVER wins over the port
    answers = assistant.answers()
    assert answers[1]["result"]["serverInfo"]["name"] == "friday"
    assert "add" in {t["name"] for t in answers[2]["result"]["tools"]}
    assert answers[3]["result"]["isError"] is False
    assert [r["actor"] for r in app.table("command_log") if r["command"] == "add"] == ["mcp:claude"]


def test_fridayd_mcp_serves_stdio_for_the_port_in_the_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[Any] = []
    monkeypatch.setattr(fridayd, "serve_stdio", lambda port, by_get: asked.append((port, by_get)))
    new_app(tmp_path).do("settings_set", key="server", value={"port": 8790})
    fridayd.main(["--data-dir", str(tmp_path), "mcp"])
    assert asked == [(8790, query_by_get)]
