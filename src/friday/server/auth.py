"""Who a request is from (DESIGN §23 seam 4). The personal build has one user and no login; an assistant or script
carries a token (`token_add`) and acts as `mcp:<name>`, within its scope."""

import sqlite3

from fastapi import HTTPException
from starlette.requests import Request

from friday.commands.tokens import agent

# The CLI says who it is; anything else without a token is you in the web app.
CLIENT_ACTORS = {"cli": "cli"}


def user_of(request: Request) -> int:
    return 1


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


def actor_of(request: Request, conn: sqlite3.Connection, now_utc: int, writes: bool = False) -> str:
    token = bearer(request)
    if token is None:
        return CLIENT_ACTORS.get(request.headers.get("x-friday-client", ""), "you")
    found = agent(conn, user_of(request), token, now_utc)
    if found is None:
        raise HTTPException(401, "unknown token")
    name, scope = found
    if writes and scope != "read-write":
        raise HTTPException(403, f"the token {name} can only read")
    return f"mcp:{name}"
