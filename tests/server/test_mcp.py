"""Assistants (DESIGN §22.8): tokens with a scope over the HTTP API, and the MCP tools generated from the registry
at `/mcp`, acting as `mcp:<name>`."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from friday.commands.all import REGISTRY
from friday.server.app import create_app
from friday.server.mcp import HIDDEN, tools
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


def bearer(app: App, name: str, scope: str) -> dict[str, str]:
    return {"authorization": f"Bearer {app.do('token_add', name=name, scope=scope)['token']}"}


def test_a_read_token_reads_and_cant_write_and_a_revoked_one_is_refused(app: App, client: TestClient) -> None:
    reader = bearer(app, "dashboard", "read")
    assert client.get("/api/q/items", headers=reader).status_code == 200
    assert client.post("/api/c/add", json={"text": "x"}, headers=reader).status_code == 403
    app.do("token_remove", name="dashboard")
    assert client.get("/api/q/items", headers=reader).status_code == 401
    assert [t["name"] for t in app.do("tokens")] == []


def test_the_secret_is_shown_once_and_never_stored(app: App) -> None:
    token = app.do("token_add", name="claude", scope="read-write")["token"]
    assert token not in str(app.table("kv")) and token not in str(app.table("command_log"))


def test_every_query_and_command_is_a_tool_and_commands_can_preview() -> None:
    by_name = {t.name: t for t in tools()}
    assert set(by_name) == set(REGISTRY) - HIDDEN
    assert "preview" in by_name["add"].input_schema["properties"] and by_name["items"].annotations.read_only_hint


def rpc(client: TestClient, method: str, params: dict[str, Any], headers: dict[str, str]) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    return client.post("/mcp", json=body, headers=MCP_HEADERS | headers)


def test_mcp_needs_a_token_and_acts_as_the_assistant(app: App, client: TestClient) -> None:
    assert rpc(client, "tools/list", {}, {}).status_code == 401
    writer = bearer(app, "claude", "read-write")
    listed = rpc(client, "tools/list", {}, writer).json()["result"]["tools"]
    assert "add" in {t["name"] for t in listed}
    called = rpc(client, "tools/call", {"name": "add", "arguments": {"text": "essay due wed 17:00 ~2h"}}, writer)
    assert called.json()["result"]["isError"] is False
    assert [r["actor"] for r in app.table("command_log") if r["command"] == "add"] == ["mcp:claude"]
