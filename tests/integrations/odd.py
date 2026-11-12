"""A stand-in that answers one request oddly: everything as its fake answers, except the one path (and, for a GraphQL
service, the one operation) that comes back with `answer`, a shape the service's documentation doesn't promise or
something that isn't JSON at all. The glass-box tests use it to see each odd answer said in words, never a crash."""

from typing import Any

import httpx

from tests.integrations.kit import FakeService


def odd(fake: FakeService, path: str, answer: Any, op: str | None = None, status: int = 200) -> httpx.MockTransport:
    """The fake, but `path` (by the fake's own path, its prefix taken off) answers `answer`: bytes as they are, else
    as JSON; with `op`, only a GraphQL request for that operation."""

    def handle(request: httpx.Request) -> httpx.Response:
        if fake.path(request) == path and (op is None or fake.body(request).get("operationName") == op):
            fake.requests.append(request)
            if isinstance(answer, bytes):
                return httpx.Response(status, content=answer, headers={"content-type": "text/html"})
            return httpx.Response(status, json=answer)
        return fake.handle(request)

    return httpx.MockTransport(handle)
