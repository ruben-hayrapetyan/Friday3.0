"""Pins (DESIGN §9.3): place an item at a time, preferred or locked; or let Friday decide again."""

from friday.api.commands import Changed, PinInput, UnpinInput
from friday.commands.fields import require_item
from friday.commands.registry import Ctx, command
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.time import format_utc, parse_utc
from friday.planner.progress import minutes_by_item, remaining_minutes


@command("pin", affects_plan=True)
def pin(ctx: Ctx, inp: PinInput) -> Changed:
    """Place an item at a time; `locked` holds it there, `preferred` asks for it. Replaces the pins it overlaps."""
    item = require_item(ctx, inp.id)
    if item.when == "fixed" or item.status != "todo":
        raise FieldError("id", "That can't be pinned: it's an event at a set time, or it's done")
    start = parse_utc(ctx.utc(inp.start, "start"))
    if inp.end is not None:
        end = parse_utc(ctx.utc(inp.end, "end"))
    else:
        left = remaining_minutes(item, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0))
        end = start + (left if left else 60)
    if end <= start:
        raise FieldError("end", "must be after the start")
    replaced = [(start, end)]
    if inp.from_start and inp.from_end:
        moved_from = parse_utc(ctx.utc(inp.from_start, "from_start")), parse_utc(ctx.utc(inp.from_end, "from_end"))
        replaced.append(moved_from)
    for old in rows(ctx.conn, "SELECT * FROM pins WHERE user_id = ? AND item_id = ?", [ctx.user_id, inp.id]):
        lo, hi = parse_utc(old["start_utc"]), parse_utc(old["end_utc"])
        if any(lo < b and a < hi for a, b in replaced):
            ctx.db.delete("pins", {"id": old["id"]})
    ctx.db.insert(
        "pins",
        {
            "item_id": inp.id,
            "start_utc": format_utc(start),
            "end_utc": format_utc(end),
            "kind": inp.kind,
            "created_utc": ctx.now_text,
        },
    )
    return Changed(
        message=f"Pinned {item.title} {ctx.local(format_utc(start))}–{ctx.local(format_utc(end))[-5:]} ({inp.kind})"
    )


@command("unpin", affects_plan=True)
def unpin(ctx: Ctx, inp: UnpinInput) -> Changed:
    """Remove an item's pins (or one of them), so Friday decides again."""
    found = rows(ctx.conn, "SELECT id FROM pins WHERE user_id = ? AND item_id = ?", [ctx.user_id, inp.id])
    chosen = [r for r in found if inp.pin_id is None or r["id"] == inp.pin_id]
    if not chosen:
        raise FieldError("pin_id", "That pin isn't there any more: reload the page")
    for row in chosen:
        ctx.db.delete("pins", {"id": row["id"]})
    return Changed(message=f"Unpinned T{inp.id}")
