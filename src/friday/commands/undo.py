"""Undo (DESIGN §9.2): restore the rows a command changed, if nothing has changed them since."""

import json
from typing import Any

from friday.api.commands import Changed, UndoInput
from friday.commands.eventwrites import put_back
from friday.commands.registry import Ctx, command
from friday.commands.writer import LaterCommands, StaleUndo
from friday.core.db import one
from friday.core.items import FieldError


@command("undo", affects_plan=True)
def undo(ctx: Ctx, inp: UndoInput) -> Changed:
    """Undo a command. Undo is itself a command, so it can be undone."""
    logged = one(ctx.conn, "SELECT * FROM command_log WHERE user_id = ? AND id = ?", [ctx.user_id, inp.command_id])
    if logged is None:
        raise FieldError("command_id", f"There's nothing to undo (no change C{inp.command_id})")
    if logged["undone_by"] is not None:
        raise FieldError("command_id", "That was undone already")
    if not logged["undo"]:
        raise FieldError("command_id", "That change left nothing to undo")
    changes = json.loads(logged["undo"])
    # A delete already sent to a calendar stays sent (its job is the calendar's history, not this command's to take
    # back); the event goes back there instead (C68's open list, 9 Nov).
    sent = [c for c in changes if sent_write(ctx, c, "delete")]
    try:
        ctx.db.revert([c for c in changes if c not in sent], LaterCommands(ctx.conn, inp.command_id, ctx.user_id))
    except StaleUndo as stale:
        raise FieldError("command_id", f"That can't be undone any more: {stale}") from stale
    for change in sent:
        put_back(ctx, change["after"]["item_id"])
    # The log isn't undo data, so these two marks are kept by hand.
    ctx.conn.execute("UPDATE command_log SET undone_by = ? WHERE id = ?", [ctx.command_id, inp.command_id])
    if logged["command"] == "undo":
        target = json.loads(logged["input"])["command_id"]
        ctx.conn.execute("UPDATE command_log SET undone_by = NULL WHERE id = ?", [target])
    return Changed(message=f"Undid C{inp.command_id} ({logged['command']})")


def sent_write(ctx: Ctx, change: dict[str, Any], op: str) -> bool:
    """A change that queued a calendar write of `op` the job has since sent."""
    if change["table"] != "event_writes" or change["op"] != "insert" or change["after"].get("op") != op:
        return False
    now = ctx.db.fetch("event_writes", change["key"])
    return now is not None and now["done_utc"] is not None
