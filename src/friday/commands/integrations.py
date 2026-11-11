"""Connecting, setting and disconnecting integrations (C96): Todoist and the others that follow. A token is checked
with the service before anything is kept, and kept only in secrets.toml (these commands aren't logged); the first
read waits in the Inbox to be reviewed together unless you choose otherwise (the setting shows once connected);
disconnecting asks whether what it brought in stays (your answer, 10 Nov). One with lists (Notion's databases, C101)
has a switch for each; one switched off asks the same of what that list brought in."""

import json
import re
import sqlite3
import time
from typing import Any

from friday.api.commands import (
    ArrivalInput,
    Connected,
    ConnectInput,
    ConnectOutput,
    DisconnectInput,
    ListSetInput,
    ListsInput,
    SignInInput,
    SignInOut,
    TodoListOut,
    TokenPageInput,
    TokenPageOut,
)
from friday.api.types import Empty
from friday.commands.registry import Ctx, command, query, run
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.integrations import oauth, outlook, sync
from friday.integrations.base import ConnectorError
from friday.planner.store import kv_set, load_settings


@command("integration_connect", logged=False)  # a token is never logged
def integration_connect(ctx: Ctx, inp: ConnectInput) -> ConnectOutput:
    if not sync.is_integration(inp.kind):
        raise FieldError("kind", f"Friday doesn't connect to “{inp.kind}”")
    make = sync.CONNECTORS[inp.kind]
    wanted = getattr(make, "fields", ())
    given = {k: v.strip() for k, v in inp.fields.items() if k in wanted}
    try:
        connector = make(inp.token, given, sync.TRANSPORTS.get(inp.kind))
        account = connector.check()
    except ConnectorError as error:
        raise FieldError("token", str(error)) from error
    given |= getattr(connector, "kept", {})  # as the connector reads them (Jira's site as its address)
    source_id = add_source(ctx.conn, ctx.user_id, inp.kind, inp.token, given, account)
    said = f"{make.name} connected ({account}): its to-dos come to your Inbox within the minute, to review together"
    if make.caps.on_mac:  # Apple Reminders: the Mac app reads them, once macOS lets it
        said = f"{make.name} connected: Friday's Mac app reads them once you allow it (macOS asks)"
    return ConnectOutput(message=said, source=connected(ctx, source_id))


def add_source(
    conn: sqlite3.Connection, user_id: int, kind: str, token: str, given: dict[str, str], account: str
) -> int:
    """A connected integration's row, its token kept in secrets.toml (none for one on the Mac), read in the minute."""
    make = sync.CONNECTORS[kind]
    taken = {r["name"] for r in rows(conn, "SELECT name FROM sources WHERE kind = ?", [kind])}
    name = next(n for n in [make.name, *(f"{make.name} {i}" for i in range(2, 99))] if n not in taken)
    arrival = getattr(make, "arrival", "inbox_first")
    cursor = conn.execute(
        "INSERT INTO sources (user_id, kind, name, config, trusted) VALUES (?, ?, ?, ?, 0)",
        [user_id, kind, name, json.dumps({"arrival": arrival, "account": account} | given)],
    )
    source_id = int(cursor.lastrowid or 0)
    if not make.caps.on_mac:  # Apple Reminders has no token: macOS asks instead
        sync.keep_token(source_id, kind, token)
    kv_set(conn, "integrations_now", True, user_id)
    return source_id


LOOPBACK = re.compile(r"^http://(127\.0\.0\.1|localhost):\d{2,5}$")


@command("integration_sign_in", logged=False)  # nothing to undo: the service's page opens, nothing changes yet
def integration_sign_in(ctx: Ctx, inp: SignInInput) -> SignInOut:
    """The service's own sign-in page, for one connected by signing in (Microsoft, TickTick, Slack): open it, allow
    Friday, and the page sends you back here (/oauth/callback), which connects it."""
    make = signs_in().get(inp.kind)
    provider = getattr(make, "provider", None)
    if provider is None:
        raise FieldError("kind", f"{inp.kind} isn't connected by signing in")
    if not LOOPBACK.match(inp.origin):
        raise FieldError("origin", "Sign in from Friday on this Mac")
    wanted = getattr(make, "fields", ())
    given = {k: v.strip() for k, v in inp.fields.items() if k in wanted} | {"_user": str(ctx.user_id)}
    try:
        return SignInOut(url=oauth.begin(provider, f"{inp.origin}/oauth/callback", given))
    except ConnectorError as error:
        raise FieldError("kind", str(error)) from error


def signs_in() -> dict[str, Any]:
    """What's connected by signing in, by kind: integrations (Microsoft To Do…) and mailboxes (Outlook)."""
    return {k: c for k, c in sync.CONNECTORS.items() if hasattr(c, "provider")} | {
        outlook.OUTLOOK.kind: outlook.GraphMailService
    }


def signed_in(conn: sqlite3.Connection, state: str, code: str | None, error: str | None) -> tuple[bool, str]:
    """The service sent your browser back (GET /oauth/callback): connected, or why not, in words for the page."""
    if error or not code:
        with oauth.LOCK:
            pending = oauth.PENDING.pop(state, None)
        name = pending.provider.name if pending else "The service"
        return False, f"{name} didn't connect: {'you said no' if error == 'access_denied' else error or 'no answer'}"
    try:
        pending, token = oauth.finish(state, code)
        kind = pending.provider.kind
        given = {k: v for k, v in pending.fields.items() if not k.startswith("_")}
        connector = signs_in()[kind](token, given, sync.TRANSPORTS.get(kind))
        account = connector.check()
    except ConnectorError as error:
        return False, str(error)
    user_id = int(pending.fields.get("_user", 1))
    if getattr(connector, "mail", False):  # a mailbox (Outlook): read as the others are, a mail source of its own
        outlook.keep(account, token)
        if not load_settings(conn, user_id)["gmail"].enabled:  # the mail settings every mailbox shares
            gmail = load_settings(conn, user_id)["gmail"].model_dump() | {"enabled": True}
            run(conn, "settings_set", {"key": "gmail", "value": gmail}, now_utc=int(time.time() // 60),
                actor="you", user_id=user_id, provisional=False)  # fmt: skip
        kv_set(conn, "sync_now", True, user_id)
        conn.commit()
        return True, f"Friday reads {account}'s new mail from now on. You can close this tab and go back to Friday."
    add_source(conn, user_id, kind, token, given | getattr(connector, "kept", {}), account)
    conn.commit()
    return (
        True,
        f"Friday is connected to {pending.provider.name} ({account}). You can close this tab and go back to Friday.",
    )


@command("integration_set")
def integration_set(ctx: Ctx, inp: ArrivalInput) -> Connected:
    source = require(ctx, inp.id)
    config = json.loads(source["config"] or "{}") | {"arrival": inp.arrival}
    ctx.db.update("sources", {"id": inp.id}, {"config": json.dumps(config)})
    return connected(ctx, inp.id)


@command("integration_disconnect", affects_plan=True)
def integration_disconnect(ctx: Ctx, inp: DisconnectInput) -> Connected:
    source = require(ctx, inp.id)
    if not inp.keep:
        from friday.api.commands import ItemRef
        from friday.commands.items import drop  # in this command's own transaction, so one undo brings them back

        for item in made(ctx, inp.id):
            drop(ctx, ItemRef(id=item))
    ctx.db.update("sources", {"id": inp.id}, {"enabled": 0})
    ctx.conn.execute("UPDATE source_writes SET done_utc = ? WHERE source_id = ? AND done_utc IS NULL",
                     [ctx.now_text, inp.id])  # fmt: skip
    sync.forget_token(int(source["id"]))
    return connected(ctx, inp.id)


@query("integration_token_page")
def integration_token_page(ctx: Ctx, inp: TokenPageInput) -> TokenPageOut:
    """Where the service gives you a token for this copy of Friday (Trello's Allow page carries Friday's app key)."""
    if not sync.is_integration(inp.kind) and inp.kind not in signs_in():
        raise FieldError("kind", f"Friday doesn't connect to “{inp.kind}”")
    make = signs_in().get(inp.kind) or sync.CONNECTORS[inp.kind]
    page = getattr(make, "token_page", None)
    url = page() if page else None
    provider = getattr(make, "provider", None)
    return TokenPageOut(url=url, ready=provider.ready() if provider else not page or url is not None)


@query("integration_lists")
def integration_lists(ctx: Ctx, inp: ListsInput) -> list[TodoListOut]:
    """The service's to-do lists, asked of it now, each with whether it's read and what it brought in."""
    source = require(ctx, inp.id)
    connector = sync.connector_for(source)
    if not connector.caps.lists:
        raise FieldError("id", f"{source['name']} has no lists to choose from")
    try:
        found = connector.lists()
    except ConnectorError as error:
        raise FieldError("id", str(error)) from error
    return [TodoListOut(id=t.id, name=t.name, on=connector.on(t), team=t.team, made=len(made(ctx, inp.id, t.id)))
            for t in found]  # fmt: skip


@command("integration_list_set", affects_plan=True)
def integration_list_set(ctx: Ctx, inp: ListSetInput) -> Connected:
    """Read one of its lists, or not. Off, its to-dos are no longer kept in step: kept as they are, or dropped."""
    source = require(ctx, inp.id)
    if not sync.CONNECTORS[source["kind"]].caps.lists:
        raise FieldError("id", f"{source['name']} has no lists to choose from")
    config = json.loads(source["config"] or "{}")
    config["lists"] = (config.get("lists") or {}) | {inp.list: inp.on}
    ctx.db.update("sources", {"id": inp.id}, {"config": json.dumps(config)})
    if not inp.on:
        if not inp.keep:
            from friday.api.commands import ItemRef
            from friday.commands.items import drop

            for item in made(ctx, inp.id, inp.list):
                drop(ctx, ItemRef(id=item))
        # let go: not taken as done when it isn't read (read again, switched back on, it's in step again)
        for r in rows(ctx.conn, "SELECT id FROM raw_inputs WHERE source_id = ? AND external_id LIKE ? AND status != "
                      "'ignored'", [inp.id, f"{inp.list}/%"]):  # fmt: skip
            for pending in rows(ctx.conn, "SELECT id FROM suggestions WHERE raw_input_id = ? AND status = 'pending'",
                                [r["id"]]):  # fmt: skip
                ctx.db.update("suggestions", {"id": pending["id"]}, {"status": "superseded"})
            ctx.db.update("raw_inputs", {"id": r["id"]}, {"status": "ignored"})
    kv_set(ctx.conn, "integrations_now", True, ctx.user_id)
    return connected(ctx, inp.id)


@query("integrations")
def integrations(ctx: Ctx, inp: Empty) -> list[Connected]:
    """Integrations connected now."""
    found = rows(ctx.conn, "SELECT id, kind FROM sources WHERE user_id = ? AND enabled = 1", [ctx.user_id])
    return [connected(ctx, int(r["id"])) for r in found if sync.is_integration(r["kind"])]


def require(ctx: Ctx, source_id: int) -> dict:
    found = one(ctx.conn, "SELECT * FROM sources WHERE id = ? AND user_id = ?", [source_id, ctx.user_id])
    if not found or not sync.is_integration(found["kind"]):
        raise FieldError("id", "That integration isn't connected")
    return found


def made(ctx: Ctx, source_id: int, in_list: str | None = None) -> list[int]:
    """The open items it brought in (from one of its lists)."""
    return [
        int(r["id"])
        for r in rows(
            ctx.conn,
            "SELECT DISTINCT i.id FROM raw_inputs r JOIN suggestions s ON s.raw_input_id = r.id "
            "JOIN items i ON i.id = s.item_id WHERE r.source_id = ? AND s.status = 'accepted' AND i.status = 'todo'"
            " AND r.external_id LIKE ?",
            [source_id, f"{in_list}/%" if in_list else "%"],
        )
    ]


def connected(ctx: Ctx, source_id: int) -> Connected:
    s = one(ctx.conn, "SELECT * FROM sources WHERE id = ?", [source_id])
    assert s is not None
    config = json.loads(s["config"] or "{}")
    return Connected(
        id=source_id,
        kind=s["kind"],
        name=s["name"],
        arrival=config.get("arrival", "inbox_first"),
        two_way=sync.CONNECTORS[s["kind"]].caps.two_way,
        last_sync=ctx.local(s["last_sync_utc"]) if s["last_sync_utc"] else None,
        last_error=s["last_error"],
        made=len(made(ctx, source_id)),
        waiting=waiting(ctx, source_id),
        lists=sync.CONNECTORS[s["kind"]].caps.lists,
        signs_in=hasattr(sync.CONNECTORS[s["kind"]], "provider"),
    )


def waiting(ctx: Ctx, source_id: int) -> int:
    found = one(
        ctx.conn,
        "SELECT COUNT(*) AS n FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "WHERE r.source_id = ? AND s.status = 'pending'",
        [source_id],
    )
    return int(found["n"]) if found else 0
