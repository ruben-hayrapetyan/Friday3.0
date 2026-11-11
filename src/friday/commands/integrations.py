"""Connecting, setting and disconnecting integrations (C96): Todoist and the others that follow. A token is checked
with the service before anything is kept, and kept only in secrets.toml (these commands aren't logged); the first
read waits in the Inbox to be reviewed together unless you choose otherwise (the setting shows once connected);
disconnecting asks whether what it brought in stays (your answer, 10 Nov)."""

import json

from friday.api.commands import ArrivalInput, Connected, ConnectInput, ConnectOutput, DisconnectInput
from friday.api.types import Empty
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.integrations import sync
from friday.integrations.base import ConnectorError
from friday.planner.store import kv_set


@command("integration_connect", logged=False)  # a token is never logged
def integration_connect(ctx: Ctx, inp: ConnectInput) -> ConnectOutput:
    if not sync.is_integration(inp.kind):
        raise FieldError("kind", f"Friday doesn't connect to “{inp.kind}”")
    make = sync.CONNECTORS[inp.kind]
    try:
        account = make(inp.token, {}, sync.TRANSPORTS.get(inp.kind)).check()
    except ConnectorError as error:
        raise FieldError("token", str(error)) from error
    taken = {r["name"] for r in rows(ctx.conn, "SELECT name FROM sources WHERE kind = ?", [inp.kind])}
    name = next(n for n in [make.name, *(f"{make.name} {i}" for i in range(2, 99))] if n not in taken)
    cursor = ctx.conn.execute(
        "INSERT INTO sources (user_id, kind, name, config, trusted) VALUES (?, ?, ?, ?, 0)",
        [ctx.user_id, inp.kind, name, json.dumps({"arrival": "inbox_first", "account": account})],
    )
    source_id = int(cursor.lastrowid or 0)
    if not make.caps.on_mac:  # Apple Reminders has no token: macOS asks instead
        sync.keep_token(source_id, inp.kind, inp.token)
    kv_set(ctx.conn, "integrations_now", True, ctx.user_id)
    said = f"{make.name} connected ({account}): its to-dos come to your Inbox within the minute, to review together"
    if make.caps.on_mac:  # Apple Reminders: the Mac app reads them, once macOS lets it
        said = f"{make.name} connected: Friday's Mac app reads them once you allow it (macOS asks)"
    return ConnectOutput(message=said, source=connected(ctx, source_id))


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


def made(ctx: Ctx, source_id: int) -> list[int]:
    """The open items it brought in."""
    return [
        int(r["id"])
        for r in rows(
            ctx.conn,
            "SELECT DISTINCT i.id FROM raw_inputs r JOIN suggestions s ON s.raw_input_id = r.id "
            "JOIN items i ON i.id = s.item_id WHERE r.source_id = ? AND s.status = 'accepted' AND i.status = 'todo'",
            [source_id],
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
    )


def waiting(ctx: Ctx, source_id: int) -> int:
    found = one(
        ctx.conn,
        "SELECT COUNT(*) AS n FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "WHERE r.source_id = ? AND s.status = 'pending'",
        [source_id],
    )
    return int(found["n"]) if found else 0
