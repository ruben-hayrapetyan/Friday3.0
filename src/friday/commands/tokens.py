"""Tokens for assistants and scripts (DESIGN §22.8): `token_add` makes one and shows it once; only its hash is
kept (kv `agent_tokens`). A request carrying it as a bearer token acts as `mcp:<name>`, within its scope."""

import hashlib
import json
import secrets
import sqlite3
from typing import Any

from friday.api.commands import Changed, TokenInput, TokenMade, TokenRef
from friday.api.types import Empty
from friday.api.views import TokenOut
from friday.commands.registry import Ctx, command, query
from friday.core.items import FieldError
from friday.core.time import format_utc
from friday.planner.store import kv_get


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def saved(conn: sqlite3.Connection, user_id: int) -> dict[str, dict[str, Any]]:
    return kv_get(conn, "agent_tokens", {}, user_id) or {}


def keep(conn: sqlite3.Connection, user_id: int, tokens: dict[str, dict[str, Any]]) -> None:
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'agent_tokens', ?) ON CONFLICT (user_id, key) "
        "DO UPDATE SET value = excluded.value",
        [user_id, json.dumps(tokens)],
    )


# Unlogged: the command log keeps every result, and this one is a secret.
@command("token_add", logged=False)
def token_add(ctx: Ctx, inp: TokenInput) -> TokenMade:
    """Make a token for an assistant (MCP) or a script; it is shown once."""
    tokens = saved(ctx.conn, ctx.user_id)
    if inp.name in tokens:
        raise FieldError("name", f"there is already a token named {inp.name}")
    token = "fr_" + secrets.token_urlsafe(24)
    tokens[inp.name] = {"hash": digest(token), "scope": inp.scope, "created": ctx.now_text, "last_used": None}
    keep(ctx.conn, ctx.user_id, tokens)
    return TokenMade(name=inp.name, scope=inp.scope, token=token)


@command("token_remove")
def token_remove(ctx: Ctx, inp: TokenRef) -> Changed:
    """Revoke a token."""
    tokens = saved(ctx.conn, ctx.user_id)
    if tokens.pop(inp.name, None) is None:
        raise FieldError("name", f"no token named {inp.name}")
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "agent_tokens"}, {"value": json.dumps(tokens)})
    return Changed(message=f"Revoked {inp.name}")


@query("tokens")
def tokens(ctx: Ctx, inp: Empty) -> list[TokenOut]:
    """Tokens, with when each was last used."""
    return [
        TokenOut(name=n, scope=t["scope"], created=ctx.local(t["created"]) or "", last_used=ctx.local(t["last_used"]))
        for n, t in saved(ctx.conn, ctx.user_id).items()
    ]


def agent(conn: sqlite3.Connection, user_id: int, token: str, now_utc: int) -> tuple[str, str] | None:
    """The token's name and scope, noting its use; None for a token that doesn't exist (any more)."""
    found = saved(conn, user_id)
    for name, t in found.items():
        if secrets.compare_digest(t["hash"], digest(token)):
            t["last_used"] = format_utc(now_utc)
            keep(conn, user_id, found)
            return name, t["scope"]
    return None
