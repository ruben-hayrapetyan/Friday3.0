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

import html
import inspect
import logging
import shutil
import tempfile
import threading
import time
from collections.abc import AsyncIterable, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin
from urllib.parse import urlsplit

import anyio
from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError, create_model
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.routing import Route
from starlette.types import Scope

from friday.api.types import CommandResult
from friday.commands import phones
from friday.commands.all import REGISTRY
from friday.commands.integrations import signed_in
from friday.commands.registry import Spec, run
from friday.commands.tokens import agent
from friday.core.db import connect
from friday.core.items import FieldError
from friday.integrations import sync as integrations
from friday.notify import webhooks
from friday.planner.store import generation, load_settings
from friday.server import mcp
from friday.server.auth import actor_of, bearer, user_of
from friday.server.events import Hub
from friday.server.jobs import JobLoop, backup
from friday.server.phone import PAIR_PAGE, Tailnet, refusal
from friday.server.placer import Placer
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
        self.sender: integrations.Sender | None = None
        self.placer = Placer(db_path, self.hub, clock, plugin_dir)
        self.placing = False  # the placer's thread is running: a change answers before its quick placement

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
        if background:
            self.placer.start()
            self.placing = True
            self.supervisor = Supervisor(self.db_path, self.hub, self.clock, self.plugin_dir)
            self.supervisor.start()
            self.supervisor.request(0, reason="start")  # also loads the kernel, so the next plan is quick
            self.jobs = JobLoop(self.db_path, self.hub, self.supervisor, self.clock)
            self.jobs.start()
            self.sender = integrations.Sender(self.db_path, self.clock)  # done goes back to its app at once (C97)
            self.sender.start()

    def stop(self) -> None:
        """The placer, the job loop and the solver stop side by side: one after another, each waiting on its own
        process, made quitting the Mac app take a second (28 Oct)."""
        self.hub.close()
        parts = [part for part in (self.placer if self.placing else None, self.jobs, self.supervisor, self.sender)
                 if part]  # fmt: skip
        stopping = [threading.Thread(target=part.stop, name=f"stop-{type(part).__name__}") for part in parts]
        for thread in stopping:
            thread.start()
        for thread in stopping:
            thread.join()


def create_app(
    db_path: Path,
    clock: Callable[[], int] = wall_clock,
    background: bool = True,
    plugin_dir: Path = PLUGIN_DIR,
    web_dist: Path | None = None,
    tailnet: Tailnet | None = None,
) -> FastAPI:
    """`background=False` leaves out the worker and job loop: `replan` then solves in the request (tests). `tailnet`:
    where Friday answers on your tailnet (server/phone.py), kept up to date by the listener there."""
    services = Services(db_path, clock, plugin_dir)
    tailnet = tailnet or Tailnet()

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
    app.add_exception_handler(Exception, unexpected_error)
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

    @app.middleware("http")
    async def own_address_and_paired(request: Request, call_next: Any) -> Any:
        """Only Friday's own addresses, and from another device only a paired phone (server/phone.py)."""
        client = request.client.host if request.client else None

        def paired() -> bool:
            session, token = request.cookies.get(phones.COOKIE), bearer(request)
            with services.connection() as conn:
                if session and phones.known(conn, 1, session, services.clock()):
                    return True
                return bool(token and agent(conn, 1, token, services.clock()))

        refused = await anyio.to_thread.run_sync(
            lambda: refusal(request.url.path, request.headers.get("host"), client, tailnet.names(), paired)
        )
        if refused is None:
            return await call_next(request)
        status, words = refused
        if request.url.path.startswith(("/api/", "/mcp", "/events")):
            return JSONResponse({"field": None, "message": words}, status_code=status)
        return HTMLResponse(f"<!doctype html><meta name=viewport content='width=device-width'><p>{words}</p>", status)

    @app.get("/oauth/callback", response_class=HTMLResponse, include_in_schema=False)
    def oauth_callback(state: str = "", code: str | None = None, error: str | None = None) -> HTMLResponse:
        """A service's sign-in page sends your browser back here (commands/integrations.py integration_sign_in)."""

        def finish() -> tuple[bool, str]:
            with services.connection() as conn:
                return signed_in(conn, state, code, error)

        ok, words = finish()  # connected: its first read is due within the minute (integrations_now)
        head = "Connected" if ok else "Not connected"
        page = (
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Friday</title>"
            "<body style='font: 16px -apple-system, system-ui; margin: 3em auto; max-width: 32em'>"
            f"<h1 style='font-size: 20px'>{head}</h1><p>{html.escape(words)}</p>"
        )
        return HTMLResponse(page, status_code=200 if ok else 400)

    @app.get("/pair", response_class=HTMLResponse)
    def pair_page() -> HTMLResponse:
        return HTMLResponse(PAIR_PAGE)

    @app.post("/api/pair")
    def pair(body: Annotated[dict[str, Any], Body()], request: Request) -> JSONResponse:
        """A phone's camera opened the pairing code: it gets a sign-in of its own, kept until you remove it."""
        device = str(body.get("device") or "Phone")[:40]
        with services.connection() as conn:
            session = phones.pair(conn, 1, str(body.get("code") or ""), device, services.clock())
        if session is None:
            words = "That pairing code has expired or was used. On your Mac, open Settings → Phone and pair again."
            return JSONResponse({"field": "code", "message": words}, status_code=403)
        answer = JSONResponse({"paired": True})
        answer.set_cookie(phones.COOKIE, session, max_age=10 * 365 * 86400, httponly=True, samesite="lax",
                          secure=request.url.scheme == "https", path="/")  # fmt: skip
        return answer

    @app.middleware("http")
    async def own_pages_only(request: Request, call_next: Any) -> Any:
        """A change comes only from Friday's own pages (the app, the Mac app's window, a dev server on this Mac), an
        assistant or a script: a page from anywhere else in the same browser is refused, so it can't change where
        your mail is read or what your plan holds (28 Oct)."""
        # A read too, when the browser says another site asked for it (the audit, 8 Nov: an <img> on any page could
        # make `ai_models` send your key where the page said); the CLI, assistants and scripts send no such header.
        cross = request.headers.get("sec-fetch-site") == "cross-site"
        if request.url.path.startswith("/api/") and (
            cross or (request.method != "GET" and foreign(request.headers.get("origin"), request.headers.get("host")))
        ):
            return JSONResponse(
                {"field": "origin", "message": "Friday takes changes only from its own pages"}, status_code=403
            )
        return await call_next(request)

    @app.get("/events", response_class=EventSourceResponse)
    async def events() -> AsyncIterable[ServerSentEvent]:
        async for message in services.hub.stream():
            yield message

    if web_dist is not None and web_dist.is_dir():
        app.mount("/", Website(directory=web_dist, html=True), name="web")
    return app


LOOPBACK = ("localhost", "127.0.0.1", "::1")


def foreign(origin: str | None, host: str | None) -> bool:
    """Whether a request's Origin is another site's: neither this server's own (the Host it was sent to) nor this
    Mac's (localhost, at any port: the Vite dev server). No Origin at all is a script, the CLI or an assistant."""
    if origin is None:
        return False
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return True  # "null": a file, a sandboxed frame
    return parts.hostname not in LOOPBACK and parts.netloc != (host or "")


class Website(StaticFiles):
    """The website, its own pages' addresses (/settings, /todo) answered with its index.html so a reload or a link
    opens that page rather than Not Found. A missing file (a dot in its name) or API route is still Not Found.

    The page, its service worker and manifest are asked about again every time (an unchanged one is a quick 304), and
    the build's hashed files kept for good: without a word on caching a browser kept the page from a deploy before,
    and its service worker went on serving it (31 Oct)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or "." in path.rsplit("/", 1)[-1] or path.split("/", 1)[0] in ("api", "mcp"):
                raise
            response = await super().get_response("index.html", scope)
        hashed = path.startswith("assets/")
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if hashed else "no-cache"
        return response


def field_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, FieldError)
    return JSONResponse({"field": error.field, "message": str(error)}, status_code=422)


UNEXPECTED = (
    "Something went wrong inside Friday ({kind}). Try again; if it keeps happening, the details are in Settings → "
    "Advanced → Diagnose."
)


def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Anything else a command or a page's question raised (8 Nov: the toast said "500 Internal Server Error"): said
    as what happened and what to do, the traceback in the log. A logged command's changes are rolled back with it,
    but not every failure is one (review, 8 Nov), so it doesn't promise that nothing changed."""
    logging.getLogger("friday.server").error("%s %s failed", request.method, request.url.path, exc_info=error)
    return JSONResponse({"field": None, "message": UNEXPECTED.format(kind=type(error).__name__)}, status_code=500)


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
            provisional=bool(preview),  # a preview shows its placement; a change answers first (server/placer.py)
        )
        settings = load_settings(conn, user)
        if out._placing is not None and not out.preview:
            services.placer.request(user, out._placing)
            # Placed before answering where there's no thread to do it (tests), or for the command line, which says
            # where a new task will probably go ("Probably Tue 2pm").
            if not services.placing or request.headers.get("x-friday-client") == "cli":
                try:
                    out.provisional = services.placer.place(conn, user, here=True)
                except Exception:  # the change is saved: said as done, not as failed (the CLI added it again)
                    logging.getLogger("friday.server").exception("quick placement after %s", spec.name)
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
    asked = bool(arguments.pop("preview", False))  # one that can't be previewed is refused, not done (audit)
    preview = asked
    return execute(services, spec, request, arguments, preview).model_dump(mode="json")


def query_by_get(spec: Spec) -> bool:
    """A query whose input fits in a query string is a GET; one with a mapping is a POST."""
    return all(query_safe(f.annotation) for f in spec.input_type.model_fields.values())


def announce(services: Services, spec: Spec, out: CommandResult, debounce_s: float) -> None:
    """Tell the app what changed, by command: it refreshes only what that command touches (web/src/api/events.ts),
    every refresh being work done on the same Mac (12 Nov: each click had the app read some 35 things again, and the
    next click waited behind them); and the planner to plan again."""
    services.hub.publish("items.changed", {"command": spec.name})
    if spec.affects_plan and services.supervisor is not None:
        services.supervisor.request(debounce_s)


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
