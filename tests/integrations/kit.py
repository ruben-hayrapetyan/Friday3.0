"""The fake-service kit (C96's testing plan): each service Friday connects to has a stand-in here that answers the
parts of its API Friday uses, from the service's own documentation (and, refreshed by scripts/live-check.py, its real
answers). A test seeds it, points Friday at it (`sync.TRANSPORTS`), and reads back every request Friday sent. It also
misbehaves on purpose: a refused token, "slow down", an outage, a timeout. Nothing reaches a real service.

`Harness` says, for one integration, how to seed and read its fake, so tests/integrations/test_contract.py can run
the same contract against every integration."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


class FakeService:
    """A stand-in API: checks the token, records requests, fails when told to, else answers with `respond`."""

    host = "example.invalid"

    def __init__(self, token: str):
        self.token = token
        self.requests: list[httpx.Request] = []
        self.failures: list[tuple[int, dict[str, str]] | str] = []

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def fail_next(self, status: int, times: int = 1, headers: dict[str, str] | None = None) -> None:
        self.failures += [(status, headers or {})] * times

    def time_out_next(self, times: int = 1) -> None:
        self.failures += ["timeout"] * times

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failures:
            failure = self.failures.pop(0)
            if failure == "timeout":
                raise httpx.ReadTimeout("no answer", request=request)
            status, headers = failure
            return httpx.Response(status, headers=headers, json={"error": "made to fail"})
        if not self.authorized(request):
            return httpx.Response(401, json={"error": "Invalid token"})
        return self.respond(request)

    def authorized(self, request: httpx.Request) -> bool:
        return request.headers.get("authorization") == f"Bearer {self.token}"

    def respond(self, request: httpx.Request) -> httpx.Response:
        raise NotImplementedError

    def writes(self) -> list[str]:
        """The changing requests Friday sent: "POST /tasks/7/close"."""
        return [f"{r.method} {self.path(r)}" for r in self.requests if r.method != "GET"]

    def path(self, request: httpx.Request) -> str:
        return request.url.path

    @staticmethod
    def body(request: httpx.Request) -> Any:
        return json.loads(request.content or b"null")


@dataclass
class Harness:
    """One integration, as the contract drives it through its fake."""

    kind: str
    token: str
    fake: Callable[[str], FakeService]  # a fresh fake that accepts this token
    add: Callable[..., str]  # (fake, title, due=None, minutes=None) → its id there
    move: Callable[[Any, str, str], None]  # (fake, id, new due) as edited there
    rename: Callable[[Any, str, str], None]  # (fake, id, new title)
    finish: Callable[[Any, str], None]  # completed (or deleted) there
    is_done: Callable[[Any, str], bool]  # done there now?
    two_way: bool = True
    lengths: bool = False  # the service keeps a length


def serve(fake: FakeService) -> tuple[str, Callable[[], None]]:
    """The fake on a real port, for system tests: its address (http://127.0.0.1:N) and how to stop it."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def answer(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            body = self.rfile.read(length) if length else b""
            request = httpx.Request(self.command, f"https://{fake.host}{self.path}", headers=dict(self.headers),
                                    content=body)  # fmt: skip
            response = fake.handle(request)
            self.send_response(response.status_code)
            for k, v in response.headers.items():
                if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("content-length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = answer

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}", server.shutdown
