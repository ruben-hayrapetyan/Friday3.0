"""Undo (DESIGN §9.2): restore the rows a command changed, if nothing has changed them since."""

import json

from friday.api.commands import Changed, UndoInput
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
    try:
        ctx.db.revert(json.loads(logged["undo"]), LaterCommands(ctx.conn, inp.command_id, ctx.user_id))
    except StaleUndo as stale:
        raise FieldError("command_id", f"That can't be undone any more: {stale}") from stale
    # The log isn't undo data, so these two marks are kept by hand.
    ctx.conn.execute("UPDATE command_log SET undone_by = ? WHERE id = ?", [ctx.command_id, inp.command_id])
    if logged["command"] == "undo":
        target = json.loads(logged["input"])["command_id"]
        ctx.conn.execute("UPDATE command_log SET undone_by = NULL WHERE id = ?", [target])
    return Changed(message=f"Undid C{inp.command_id} ({logged['command']})")
