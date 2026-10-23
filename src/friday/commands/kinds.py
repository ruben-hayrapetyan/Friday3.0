"""Kinds (presets) you add and delete (M12b). Deleting moves what used the kind to another one: its items, series,
priority place and buffer; a calendar reading into it goes back to deciding per event."""

import json
from typing import Any

from friday.api.commands import Changed, KindAddInput, KindRemoveInput
from friday.commands.registry import Ctx, command
from friday.commands.settings import write_setting
from friday.core.db import rows
from friday.core.items import FieldError

READ_INTO = ("Assignment", "Exam prep", "Class", "Exam", "Event")  # calendars and mail are read into these


def presets_json(ctx: Ctx) -> dict[str, Any]:
    return {name: p.model_dump(exclude_none=True) for name, p in ctx.settings["presets"].items()}


@command("kind_add")
def kind_add(ctx: Ctx, inp: KindAddInput) -> Changed:
    """A new kind, starting as a copy of one you have."""
    presets, name = presets_json(ctx), inp.name.strip()
    if not name or name.lower() in (p.lower() for p in presets):
        raise FieldError("name", f"there is already a kind called {name}" if name else "give it a name")
    if inp.like not in presets:
        raise FieldError("like", f"no kind called {inp.like}")
    write_setting(ctx, "presets", presets | {name: presets[inp.like]})
    return Changed(message=f"Added {name}")


@command("kind_remove", affects_plan=True)
def kind_remove(ctx: Ctx, inp: KindRemoveInput) -> Changed:
    """Delete a kind; what used it moves to `move_to`."""
    presets = presets_json(ctx)
    if inp.name not in presets:
        raise FieldError("name", f"no kind called {inp.name}")
    if inp.name in READ_INTO:
        raise FieldError("name", f"calendars and mail are read into {inp.name}, so it stays")
    if inp.move_to not in presets or inp.move_to == inp.name:
        raise FieldError("move_to", "pick another kind for what used it")
    bound = [r.name for r in ctx.settings["rules"] if (r.scope or {}).get("preset") == inp.name]
    if bound:
        raise FieldError("name", f"the rule {bound[0]} is about {inp.name}; change or delete it first")
    moved = move_items(ctx, inp.name, inp.move_to)
    drop_mentions(ctx, inp.name)
    write_setting(ctx, "presets", {k: v for k, v in presets.items() if k != inp.name})
    return Changed(message=f"Deleted {inp.name}" + (f"; {moved} moved to {inp.move_to}" if moved else ""))


def move_items(ctx: Ctx, name: str, move_to: str) -> int:
    """Its items, series and suggestions waiting in the inbox; returns how many items."""
    found = rows(ctx.conn, "SELECT id FROM items WHERE user_id = ? AND preset = ?", [ctx.user_id, name])
    for r in found:
        ctx.db.update("items", {"id": r["id"]}, {"preset": move_to})
    for s in rows(ctx.conn, "SELECT id, template FROM series WHERE user_id = ?", [ctx.user_id]):
        template = json.loads(s["template"])
        if template.get("preset") == name:
            ctx.db.update("series", {"id": s["id"]}, {"template": json.dumps(template | {"preset": move_to})})
    for s in rows(
        ctx.conn, "SELECT id, input FROM suggestions WHERE user_id = ? AND status = 'pending'", [ctx.user_id]
    ):
        fields = json.loads(s["input"])
        if fields.get("preset") == name:
            ctx.db.update("suggestions", {"id": s["id"]}, {"input": json.dumps(fields | {"preset": move_to})})
    return len(found)


def drop_mentions(ctx: Ctx, name: str) -> None:
    """Its place in the priority order, its buffer and any calendar reading into it."""
    if name in ctx.settings["kind_order"]:
        write_setting(ctx, "kind_order", [k for k in ctx.settings["kind_order"] if k != name])
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    for r in rules:
        r["params"].get("by_preset", {}).pop(name, None)
    if rules != [r.model_dump() for r in ctx.settings["rules"]]:
        write_setting(ctx, "rules", rules)
    for s in rows(
        ctx.conn, "SELECT id, config FROM sources WHERE user_id = ? AND kind IN ('gcal', 'mac')", [ctx.user_id]
    ):
        config = json.loads(s["config"])
        if config.get("kind") == name:
            ctx.db.update("sources", {"id": s["id"]}, {"config": json.dumps(config | {"kind": None})})
