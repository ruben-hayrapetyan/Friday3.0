"""The FastAPI app (DESIGN §9.1): one route per registry entry, so HTTP, OpenAPI and the CLI agree by construction.

- Commands: `POST /api/c/<name>` with the input as the body, `?preview=true` (or `full`, which adds a warm solve's
  change list), and an optional `Idempotency-Key` header. The answer is the command's result with its id and
  provisional placement.
- Queries: `GET /api/q/<name>` with the input as query parameters (`POST` for the one or two whose input has a
  mapping, which a query string can't carry).
- `GET /events`: the SSE stream.
- `/mcp`: the MCP server for assistants (`server/mcp.py`), with a bearer token.
- `GET /api/backup`: a copy of the whole database, made online like the nightly backup (Settings → Back up).

Each request opens its own SQLite connection: WAL lets reads run beside a write, and `BEGIN IMMEDIATE` queues
writers.
"""

import inspect
import json
import shutil
import tempfile
import time
from collections.abc import AsyncIterable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import anyio
from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError, create_model
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import Scope

from friday.api.types import CommandResult
from friday.commands.all import REGISTRY
from friday.commands.registry import Spec, run
from friday.commands.tokens import agent
from friday.core.db import connect
from friday.core.items import FieldError
from friday.notify import webhooks
from friday.notify.channels import vapid_keys
from friday.planner.store import generation, load_settings
from friday.server import mcp
from friday.server.auth import actor_of, user_of
from friday.server.events import Hub
from friday.server.jobs import JobLoop, backup
from friday.server.plugins import PLUGIN_DIR, load_plugins
from friday.server.worker import Supervisor, set_problem


def wall_clock() -> int:
    return int(time.time() // 60)


class Services:
    """What the routes share: where the database is, the clock, the SSE hub and (when running) the worker."""

    def __init__(self, db_path: Path, clock: Callable[[], int], plugin_dir: Path):
        self.db_path, self.clock, self.plugin_dir = db_path, clock, plugin_dir
        self.hub = Hub()
        self.supervisor: Supervisor | None = None
        self.jobs: JobLoop | None = None

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def start(self, background: bool) -> None:
        with self.connection() as conn:
            errors = load_plugins(self.plugin_dir) if load_settings(conn)["server"].allow_plugins else []
            set_problem(conn, 1, "plugins", "; ".join(f"plugin skipped: {e}" for e in errors) or None)
            # The browser subscribes to Web Push with the server's public key, read through the `push_key` query.
            public = vapid_keys(self.db_path.parent)[1]
            conn.execute(
                "INSERT INTO kv (user_id, key, value) VALUES (1, 'vapid_public', ?) "
                "ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value",
                [json.dumps(public)],
            )
        if background:
            self.supervisor = Supervisor(self.db_path, self.hub, self.clock, self.plugin_dir)
            self.supervisor.start()
            self.supervisor.request(0, reason="start")  # also loads the kernel, so the next plan is quick
            self.jobs = JobLoop(self.db_path, self.hub, self.supervisor, self.clock)
            self.jobs.start()

    def stop(self) -> None:
        self.hub.close()
        if self.jobs:
            self.jobs.stop()
        if self.supervisor:
            self.supervisor.stop()


def create_app(
    db_path: Path,
    clock: Callable[[], int] = wall_clock,
    background: bool = True,
    plugin_dir: Path = PLUGIN_DIR,
    web_dist: Path | None = None,
) -> FastAPI:
    """`background=False` leaves out the worker and job loop: `replan` then solves in the request (tests)."""
    services = Services(db_path, clock, plugin_dir)

    async def call_tool(name: str, arguments: dict[str, Any], request: Request) -> Any:
        return await anyio.to_thread.run_sync(lambda: run_tool(services, name, arguments, request))

    def has_token(token: str) -> bool:
        with services.connection() as conn:
            return agent(conn, 1, token, services.clock()) is not None

    mcp_app, mcp_sessions = mcp.http_app(call_tool, has_token)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        services.start(background)
        async with mcp_sessions.run():
            yield
        services.stop()

    app = FastAPI(title="Friday", lifespan=lifespan)
    app.state.services = services
    app.add_exception_handler(FieldError, field_error)
    app.add_exception_handler(ValidationError, validation_error)
    for spec in REGISTRY.values():
        if spec.mutates:
            add_command_route(app, spec, services)
        else:
            add_query_route(app, spec, services)

    app.router.routes.append(Route("/mcp", endpoint=mcp_app, methods=["GET", "POST", "DELETE"]))

    @app.get("/api/backup", include_in_schema=False)
    def download_backup() -> FileResponse:
        folder = Path(tempfile.mkdtemp(prefix="friday-backup-"))
        with services.connection() as conn:
            today = date.today()
            path = backup(conn, folder, 1, today)
        return FileResponse(path, filename=path.name, background=BackgroundTask(shutil.rmtree, folder))

    @app.get("/events", response_class=EventSourceResponse)
    async def events() -> AsyncIterable[ServerSentEvent]:
        async for message in services.hub.stream():
            yield message

    if web_dist is not None and web_dist.is_dir():
        app.mount("/", Website(directory=web_dist, html=True), name="web")
    return app


class Website(StaticFiles):
    """The website, its own pages' addresses (/settings, /todo) answered with its index.html so a reload or a link
    opens that page rather than Not Found. A missing file (a dot in its name) or API route is still Not Found."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or "." in path.rsplit("/", 1)[-1] or path.split("/", 1)[0] in ("api", "mcp"):
                raise
            return await super().get_response("index.html", scope)


def field_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, FieldError)
    return JSONResponse({"field": error.field, "message": str(error)}, status_code=422)


def validation_error(request: Request, error: Exception) -> JSONResponse:
    # Pydantic errors raised inside a command (a settings value, say), not the request's own validation.
    assert isinstance(error, ValidationError)
    first = error.errors()[0]
    field = ".".join(str(p) for p in first["loc"]) or "input"
    return JSONResponse({"field": field, "message": f"{field}: {first['msg']}"}, status_code=422)


Preview = Literal["false", "true", "full"]
PREVIEW: dict[str, bool | Literal["full"]] = {"false": False, "true": True, "full": "full"}


def add_command_route(app: FastAPI, spec: Spec, services: Services) -> None:
    result_type = create_model(f"{camel(spec.name)}Result", __base__=CommandResult, result=(spec.output_type, ...))

    def endpoint(request: Request, inp: Any, preview: Preview = "false", idempotency_key: str | None = None) -> Any:
        return execute(services, spec, request, inp if inp is not None else {}, PREVIEW[preview], idempotency_key)

    body = (
        Annotated[spec.input_type, Body()]
        if has_required(spec.input_type)
        else Annotated[spec.input_type | None, Body()]
    )
    endpoint.__signature__ = signature(  # type: ignore[attr-defined]
        ("request", Request, inspect.Parameter.empty),
        ("inp", body, inspect.Parameter.empty if has_required(spec.input_type) else None),
        ("preview", Preview, "false"),
        ("idempotency_key", Annotated[str | None, Header()], None),
    )
    app.post(f"/api/c/{spec.name}", response_model=result_type, summary=spec.summary, operation_id=spec.name)(endpoint)


def execute(
    services: Services,
    spec: Spec,
    request: Request,
    inp: Any,
    preview: bool | Literal["full"] = False,
    idempotency_key: str | None = None,
) -> CommandResult:
    """Run a command for a request (the HTTP API or an MCP call), then tell the app and the planner."""
    with services.connection() as conn:
        user, now = user_of(request), services.clock()
        actor = actor_of(request, conn, now, writes=True)
        supervisor = services.supervisor
        solver = (lambda reason: supervisor.solve_now(reason, generation(conn, user))) if supervisor else None
        out = run(
            conn,
            spec.name,
            inp,
            now_utc=now,
            actor=actor,
            user_id=user,
            preview=preview,
            idempotency_key=idempotency_key,
            solver=solver,
        )
        settings = load_settings(conn, user)
    if not out.preview and not out.repeated and spec.logged:
        announce(services, spec, out, settings["planner"].debounce_s)
        if spec.name == "done":
            webhooks.fire(settings["webhooks"], "item.done", out.result)
    return out


def run_tool(services: Services, name: str, arguments: dict[str, Any], request: Request) -> Any:
    spec = REGISTRY[name]
    if not spec.mutates:
        with services.connection() as conn:
            actor = actor_of(request, conn, services.clock())
            return run(conn, name, arguments, now_utc=services.clock(), actor=actor, user_id=user_of(request)).result
    preview = bool(arguments.pop("preview", False)) and mcp.previewable(spec)
    return execute(services, spec, request, arguments, preview).model_dump(mode="json")


def query_by_get(spec: Spec) -> bool:
    """A query whose input fits in a query string is a GET; one with a mapping is a POST."""
    return all(query_safe(f.annotation) for f in spec.input_type.model_fields.values())


def announce(services: Services, spec: Spec, out: CommandResult, debounce_s: float) -> None:
    services.hub.publish("items.changed")
    if spec.affects_plan:
        if services.supervisor is not None:
            services.supervisor.request(debounce_s)
        if out.provisional is not None:
            services.hub.publish("plan.provisional", [b.model_dump(mode="json") for b in out.provisional])


def add_query_route(app: FastAPI, spec: Spec, services: Services) -> None:
    def endpoint(request: Request, inp: Any) -> Any:
        with services.connection() as conn:
            user, now = user_of(request), services.clock()
            return run(conn, spec.name, inp, now_utc=now, actor=actor_of(request, conn, now), user_id=user).result

    as_query = query_by_get(spec)
    where = Query() if as_query else Body()
    default = inspect.Parameter.empty if has_required(spec.input_type) or as_query else None
    endpoint.__signature__ = signature(  # type: ignore[attr-defined]
        ("request", Request, inspect.Parameter.empty),
        ("inp", Annotated[spec.input_type if default is inspect.Parameter.empty else spec.input_type | None, where],
         default),
    )  # fmt: skip
    route = app.get if as_query else app.post
    route(f"/api/q/{spec.name}", response_model=spec.output_type, summary=spec.summary, operation_id=spec.name)(
        endpoint
    )


def signature(*params: tuple[str, Any, Any]) -> inspect.Signature:
    kind = inspect.Parameter.POSITIONAL_OR_KEYWORD
    return inspect.Signature([inspect.Parameter(n, kind, annotation=a, default=d) for n, a, d in params])


def has_required(model: type[BaseModel]) -> bool:
    return any(f.is_required() for f in model.model_fields.values())


def query_safe(annotation: Any) -> bool:
    """Scalars, optional scalars and lists of scalars fit in a query string; mappings and models don't."""
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return all(query_safe(a) for a in get_args(annotation))
    if origin is list:
        return all(query_safe(a) for a in get_args(annotation)) and not any(get_origin(a) for a in get_args(annotation))
    return not (origin is dict or isinstance(annotation, type) and issubclass(annotation, BaseModel))


def camel(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))
