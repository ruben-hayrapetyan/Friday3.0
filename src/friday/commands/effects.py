"""What answering an event in the inbox would do (29 Oct: "when i am looking at whether to accept or decline events,
can you provide an idea of the repercussions of accepting/declining the event?").

Accepting: the events it clashes with, the work planned in its time now (which moves), and the work that would be
later for it, estimated as `What gives` estimates (`planner.service.what_if`: construction and repair, a few seconds,
no anneal). That estimate wobbles by a quarter or half hour between two problems, so only work due after the event
starts, and half an hour or more later, is said. Declining changes nothing in the plan; there is nothing to work out.
A full preview (a warm solve) took over a minute on a real fortnight and called forty blocks moved for one hour."""

import json
from dataclasses import replace
from typing import Any

from friday.api.commands import EffectInput
from friday.api.views import EffectLate, EffectOut, EffectSpan
from friday.commands.registry import Ctx, query
from friday.core.db import one, rows
from friday.core.items import FieldError, Item
from friday.core.time import format_utc, parse_utc
from friday.planner.prepare import build_input
from friday.planner.service import what_if
from friday.planner.snapshot import take_snapshot
from friday.planner.store import current_plan

LATER_MIN_HOURS = 0.5  # below this, the estimate's own wobble


@query("suggestion_effect")
def suggestion_effect(ctx: Ctx, inp: EffectInput) -> EffectOut:
    """For a waiting suggestion of an event (at `start`–`end` when you've edited its time): what accepting it would
    clash with, take the time of, and make later."""
    found = one(ctx.conn, "SELECT * FROM suggestions WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None or found["status"] != "pending":
        raise FieldError("id", f"no pending suggestion {inp.id}")
    fields: dict[str, Any] = json.loads(found["input"] or "{}")
    start, end = inp.start or fields.get("start"), inp.end or fields.get("end")
    if found["command"] not in ("add", "edit") or not start or not end:
        return EffectOut(event=False)
    lo, hi = parse_utc(ctx.utc(start, "start")), parse_utc(ctx.utc(end, "end"))
    if hi <= lo:
        raise FieldError("end", "the event ends before it starts")
    snapshot = take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id)
    replaces = fields.get("id") if found["command"] == "edit" else found["duplicate_of"]
    clashes = [
        span(ctx, i.title, i.start_utc, i.end_utc)
        for i in snapshot.items
        if i.when == "fixed" and i.status == "todo" and i.blocks_time and i.id != replaces and overlaps(i, lo, hi)
    ]
    saved = current_plan(ctx.conn, ctx.user_id)
    takes = [
        span(ctx, r["title"], r["start_utc"], r["end_utc"])
        for r in rows(
            ctx.conn,
            "SELECT b.start_utc, b.end_utc, i.title FROM blocks b JOIN items i ON i.id = b.item_id "
            "WHERE b.plan_id = ? AND b.start_utc < ? AND b.end_utc > ? ORDER BY b.start_utc",
            [saved["id"] if saved else -1, format_utc(hi), format_utc(lo)],
        )
    ]
    event = Item(id=-1, title=str(fields.get("title") or "Event"), preset="Event", when="fixed",
                 start_utc=format_utc(lo), end_utc=format_utc(hi), blocks_time=True)  # fmt: skip

    def accepted(inp_: Any) -> Any:
        kept = tuple(i for i in inp_.items if i.id != replaces)  # an edit moves the event; a duplicate is updated
        return replace(inp_, items=(*kept, event))

    extra = what_if(build_input(snapshot), accepted)
    items = {i.id: i for i in snapshot.items}
    later = sorted(
        (
            EffectLate(title=items[k].title, hours=round(h, 1), due=ctx.local(items[k].due_utc))
            for k, h in extra.items()
            if k in items and items[k].due_utc and parse_utc(items[k].due_utc) > lo and h >= LATER_MIN_HOURS
        ),
        key=lambda x: -x.hours,
    )
    return EffectOut(event=True, clashes=clashes, takes=takes, later=later)


def overlaps(item: Item, lo: int, hi: int) -> bool:
    return bool(item.start_utc and item.end_utc) and parse_utc(item.start_utc) < hi and parse_utc(item.end_utc) > lo


def span(ctx: Ctx, title: str, start: str | None, end: str | None) -> EffectSpan:
    return EffectSpan(title=title, start=ctx.local(start) or "", end=ctx.local(end) or "")
