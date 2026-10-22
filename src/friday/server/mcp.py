"""The MCP server (DESIGN §22.8): tools generated from the registry, like the HTTP API and the CLI. Every query is a
read tool; every command a write tool with a `preview` argument. Two transports share the tools:

- streamable HTTP at `/mcp` on the daemon, which runs each call in-process (`app.execute`); a bearer token is
  required, and its scope decides what it may do;
- stdio (`fridayd mcp`), for an assistant on this machine, which forwards each call to the running daemon's HTTP
  API with the token in `FRIDAY_TOKEN`, so changes are planned and shown live as usual.
"""

import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import httpx
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from friday.commands.registry import REGISTRY, Spec

Call = Callable[[str, dict[str, Any], Any], Awaitable[Any]]  # (tool, arguments, the HTTP request or None)
HIDDEN = {"token_add", "token_remove"}  # an assistant doesn't hand out or revoke access
INSTRUCTIONS = (
    "Friday plans the person's time. Read with queries (status, items, calendar, explain); change things with "
    "commands. Pass preview: true first to see what a change would do. Times are local, like 2026-10-20T14:00."
)


def shown(spec: Spec) -> bool:
    return spec.name not in HIDDEN


def previewable(spec: Spec) -> bool:
    return spec.mutates and spec.logged


def tools() -> list[types.Tool]:
    out = []
    for spec in filter(shown, REGISTRY.values()):
        schema = spec.input_type.model_json_schema()
        if previewable(spec):
            preview = {"type": "boolean", "default": False, "description": "run it and roll back: what it would do"}
            schema["properties"] = schema.get("properties", {}) | {"preview": preview}
        out.append(
            types.Tool(
                name=spec.name,
                description=(spec.fn.__doc__ or spec.summary).strip(),
                inputSchema=schema,
                annotations=types.ToolAnnotations(readOnlyHint=not spec.mutates),
            )
        )
    return out


def server(call: Call) -> Server:
    async def list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools())

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        spec = REGISTRY.get(params.name)
        if spec is None or not shown(spec):
            return failed(f"no tool named {params.name}")
        try:
            result = await call(params.name, dict(params.arguments or {}), ctx.request)
        except Exception as error:  # a field error, a refused token: the assistant reads why
            return failed(str(getattr(error, "detail", None) or error))
        return types.CallToolResult(content=[types.TextContent(text=json.dumps(result, default=str))])

    return Server("friday", instructions=INSTRUCTIONS, on_list_tools=list_tools, on_call_tool=call_tool)


def failed(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(text=message)], isError=True)


def http_app(call: Call, has_token: Callable[[str], bool]) -> tuple[ASGIApp, StreamableHTTPSessionManager]:
    """The `/mcp` endpoint, and its session manager (the app's lifespan runs it)."""
    # Every call needs a token, so DNS rebinding can't reach it; checking Host would only lock out a tailnet name.
    manager = StreamableHTTPSessionManager(
        server(call),
        stateless=True,
        json_response=True,
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return Guarded(StreamableHTTPASGIApp(manager), has_token), manager


class Guarded:
    """Lets through only requests with a known token (a class, so Starlette's Route treats it as an ASGI app)."""

    def __init__(self, inner: ASGIApp, has_token: Callable[[str], bool]):
        self.inner, self.has_token = inner, has_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        auth = dict(scope.get("headers", [])).get(b"authorization", b"").decode()
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if not token or not await anyio.to_thread.run_sync(self.has_token, token):
            reply = JSONResponse({"message": "Friday's MCP needs a token: `friday token-add NAME`"}, status_code=401)
            await reply(scope, receive, send)
            return
        await self.inner(scope, receive, send)


def forward(base_url: str, token: str, query_by_get: Callable[[Spec], bool]) -> Call:
    """For stdio: each call goes to the daemon's HTTP API."""

    async def call(name: str, arguments: dict[str, Any], request: Any) -> Any:
        spec = REGISTRY[name]
        headers = {"authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=180) as client:
            if spec.mutates:
                preview = "true" if arguments.pop("preview", False) else "false"
                reply = await client.post(f"/api/c/{name}", params={"preview": preview}, json=arguments)
            elif query_by_get(spec):
                reply = await client.get(f"/api/q/{name}", params=arguments)
            else:
                reply = await client.post(f"/api/q/{name}", json=arguments)
        body = reply.json()
        if reply.is_error:
            raise RuntimeError(body.get("message") or body.get("detail") or reply.text)
        return body

    return call


def serve_stdio(port: int, query_by_get: Callable[[Spec], bool]) -> None:
    token = os.environ.get("FRIDAY_TOKEN")
    if not token:
        raise SystemExit("set FRIDAY_TOKEN to a token from `friday token-add NAME --scope read-write`")
    base = os.environ.get("FRIDAY_SERVER", f"http://127.0.0.1:{port}")
    app = server(forward(base, token, query_by_get))

    async def main() -> None:
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    anyio.run(main)
