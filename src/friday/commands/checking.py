"""Checking your tasks: copies of the same task, and going over what Friday brought in again.

The same deadline on two of your calendars at once (the Mac's iCloud copy of a Google calendar, say) made two tasks
from one event. `duplicates` finds open tasks with the same words (a repeat's occurrences aren't copies of each
other); `duplicates_merge` keeps one of each and moves the others' time logged onto it; `not_duplicates` remembers
that some aren't the same. `review_again` lists every open task Friday brought in from a calendar or mail for you
to go over once more; `reviewed` ticks them off, keeping them or taking them off your list. Taking a task off never
touches the calendar it came from.
"""

import json
from collections import defaultdict
from typing import Any

from friday.api.commands import Changed, ItemIds, MergeInput, ReviewedInput
from friday.api.types import Empty
from friday.api.views import DuplicateGroup, DuplicatesOut, ToReviewOut
from friday.commands.fields import item_out
from friday.commands.items import set_status
from friday.commands.registry import Ctx, command, query
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.rows import item_from_row
from friday.core.textnorm import identity_text, norm
from friday.planner.progress import minutes_by_item
from friday.planner.store import kv_get


@query("duplicates")
def duplicates(ctx: Ctx, inp: Empty) -> DuplicatesOut:
    """Open tasks that look like copies of each other, with the one Friday would keep."""
    rules = ctx.settings["text"].rules()
    apart = {tuple(sorted(ids)) for ids in kv_get(ctx.conn, "not_duplicates", [], ctx.user_id)}
    found = rows(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND when_kind != 'fixed' AND series_id IS NULL "
        "ORDER BY id",
        [ctx.user_id],
    )
    by_words: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in found:
        words = identity_text(norm(r["title"], rules))
        if words:
            by_words[words].append(r)
    done = minutes_by_item(ctx.conn, ctx.user_id)
    sources = made_from(ctx)
    read = reading(ctx)
    groups = []
    for words, copies in by_words.items():
        ids = tuple(sorted(r["id"] for r in copies))
        if len(copies) < 2 or ids in apart:
            continue
        keep = max(copies, key=lambda r: (done.get(r["id"], 0), sources.get(r["id"]) in read, -r["id"]))["id"]
        items = [item_out(ctx, item_from_row(r), done.get(r["id"], 0)) for r in copies]
        groups.append(DuplicateGroup(key=words, keep=keep, items=items))
    groups.sort(key=lambda g: g.key)
    return DuplicatesOut(groups=groups, sources={i.id: sources.get(i.id, "you") for g in groups for i in g.items})


@command("duplicates_merge", affects_plan=True)
def duplicates_merge(ctx: Ctx, inp: MergeInput) -> Changed:
    """Keep one copy of each, with the time logged on the others moved onto it; the others leave your list."""
    gone = 0
    for group in inp.groups:
        if group.keep in group.drop:
            raise FieldError("keep", f"T{group.keep} can't be both kept and removed")
        for item_id in group.drop:
            for r in rows(ctx.conn, "SELECT id FROM progress WHERE item_id = ?", [item_id]):
                ctx.db.update("progress", {"id": r["id"]}, {"item_id": group.keep})
            for r in rows(ctx.conn, "SELECT id, depends_on_id FROM dependencies WHERE item_id = ?", [item_id]):
                ctx.db.update("dependencies", {"id": r["id"]}, {"item_id": group.keep})
            for r in rows(ctx.conn, "SELECT id FROM dependencies WHERE depends_on_id = ?", [item_id]):
                ctx.db.update("dependencies", {"id": r["id"]}, {"depends_on_id": group.keep})
            for r in rows(ctx.conn, "SELECT id FROM pins WHERE item_id = ?", [item_id]):
                ctx.db.delete("pins", {"id": r["id"]})
            set_status(ctx, item_id, "dropped")  # not `drop`: the calendar it came from keeps its event
            gone += 1
    return Changed(message=f"Removed {gone} cop{'y' if gone == 1 else 'ies'}; one of each kept")


@command("not_duplicates")
def not_duplicates(ctx: Ctx, inp: ItemIds) -> Changed:
    """These look alike but aren't the same: stop asking."""
    apart = kv_get(ctx.conn, "not_duplicates", [], ctx.user_id) + [sorted(inp.ids)]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "not_duplicates"}, {"value": json.dumps(apart)})
    return Changed(message="Kept apart")


@command("review_again")
def review_again(ctx: Ctx, inp: Empty) -> Changed:
    """Every open task Friday brought in from a calendar or mail, to go over again; until you do, they stay planned."""
    sources = made_from(ctx)
    ids = [
        r["id"]
        for r in rows(
            ctx.conn,
            "SELECT id FROM items WHERE user_id = ? AND status = 'todo' AND when_kind != 'fixed' ORDER BY id",
            [ctx.user_id],
        )
        if r["id"] in sources
    ]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "to_review"}, {"value": json.dumps(ids)})
    return Changed(message=f"{len(ids)} task{'' if len(ids) == 1 else 's'} to go over")


@query("to_review")
def to_review(ctx: Ctx, inp: Empty) -> ToReviewOut:
    """What's left to go over, soonest due first."""
    ids = kv_get(ctx.conn, "to_review", None, ctx.user_id)
    if ids is None:
        return ToReviewOut(items=[], sources={}, started=False)
    marks = ", ".join("?" * len(ids)) or "NULL"
    found = rows(
        ctx.conn,
        f"SELECT * FROM items WHERE id IN ({marks}) AND status = 'todo' ORDER BY due_utc IS NULL, due_utc, id",
        ids,
    )
    done = minutes_by_item(ctx.conn, ctx.user_id)
    sources = made_from(ctx)
    items = [item_out(ctx, item_from_row(r), done.get(r["id"], 0)) for r in found]
    return ToReviewOut(items=items, sources={i.id: sources.get(i.id, "you") for i in items}, started=bool(items))


@command("reviewed", affects_plan=True)
def reviewed(ctx: Ctx, inp: ReviewedInput) -> Changed:
    """Gone over: kept as they are, or taken off your list."""
    ids = kv_get(ctx.conn, "to_review", [], ctx.user_id)
    left = [i for i in ids if i not in inp.ids]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "to_review"}, {"value": json.dumps(left)})
    if not inp.keep:
        for item_id in inp.ids:
            set_status(ctx, item_id, "dropped")
    n = len(inp.ids)
    return Changed(message=f"{'Kept' if inp.keep else 'Removed'} {n} task{'' if n == 1 else 's'}")


def made_from(ctx: Ctx) -> dict[int, str]:
    """Each item a calendar, a feed or mail brought in, by the source's name."""
    found = rows(
        ctx.conn,
        "SELECT s.item_id, src.name FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "JOIN sources src ON src.id = r.source_id WHERE s.user_id = ? AND s.item_id IS NOT NULL "
        "AND s.status = 'accepted' ORDER BY s.id",
        [ctx.user_id],
    )
    return {r["item_id"]: r["name"] for r in found}


def reading(ctx: Ctx) -> set[str]:
    return {
        r["name"] for r in rows(ctx.conn, "SELECT name FROM sources WHERE user_id = ? AND enabled = 1", [ctx.user_id])
    }
