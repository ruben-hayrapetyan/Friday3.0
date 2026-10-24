"""Google calendars in Settings (M12b): every calendar the last sync saw, alphabetized, each switched on or off and
read as one kind or per event. The choice lives in `sources`; `gcal.read` in friday.toml only picks the first ones.
The Mac's calendars (`commands/mac.py`) are switched the same way, with `mac`."""

import json
import re
from typing import Any

from friday.api.commands import CalendarSetInput, Changed
from friday.api.types import Empty
from friday.api.views import GoogleCalendarOut
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.time import format_local, format_utc, parse_utc, to_local
from friday.planner.store import event_links, kv_get


def natural(name: str) -> list[Any]:
    """ "2. To-Do" before "10. Later", ignoring case."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part.lower()) for part in re.split(r"(\d+)", name)]


@query("google_calendars")
def google_calendars(ctx: Ctx, inp: Empty) -> list[GoogleCalendarOut]:
    """Your Google calendars as of the last sync, alphabetized, with whether each is read and how."""
    out = []
    for c in kv_get(ctx.conn, "google_calendars", [], ctx.user_id):
        source = source_of(ctx, c["id"])
        config = json.loads(source["config"]) if source else {}
        synced = source and source["last_sync_utc"]
        out.append(
            GoogleCalendarOut(
                id=c["id"],
                name=c["name"],
                primary=c["primary"],
                on=bool(source and source["enabled"]),
                kind=config.get("kind") or "auto",
                trusted=bool(source and source["trusted"]),
                last_sync=format_local(to_local(parse_utc(synced), ctx.tz)) if synced else None,
                error=source["last_error"] if source else None,
                writable=c.get("writable", False),
                editable=editable(config, c),
            )
        )
    return sorted(out, key=lambda c: natural(c.name))


@command("calendar_set", affects_plan=True)
def calendar_set(ctx: Ctx, inp: CalendarSetInput) -> Changed:
    """Read a Google calendar (or, with `mac`, one of the Mac's) or stop, as one kind or per event, trusted or
    through the inbox."""
    kind = "mac" if inp.mac else "gcal"
    listed = {c["id"]: c for c in kv_get(ctx.conn, "mac_calendars" if inp.mac else "google_calendars", [], ctx.user_id)}
    if inp.id not in listed:
        where = (
            "on the Mac (as the Mac app last saw them)" if inp.mac else "in your Google account (as of the last sync)"
        )
        raise FieldError("id", f"no such calendar {where}")
    if inp.kind not in (None, "auto") and inp.kind not in ctx.settings["presets"]:
        raise FieldError("kind", f"no kind called {inp.kind}")
    name = listed[inp.id].get("source_name", listed[inp.id]["name"])
    source = source_of(ctx, inp.id, kind)
    if source is None:
        config = json.dumps({"calendar": inp.id})
        source_id = ctx.db.insert("sources", {"kind": kind, "name": name, "config": config, "enabled": 0})
        source = ctx.db.fetch("sources", {"id": source_id})
        assert source is not None
    changes: dict[str, Any] = {}
    if inp.on is not None:
        changes["enabled"] = int(inp.on)
    if inp.trusted is not None:
        changes["trusted"] = int(inp.trusted)
    if inp.editable is not None:
        if inp.editable and inp.mac:
            raise FieldError("editable", "Friday doesn't change the Mac's calendars yet")
        if inp.editable and not listed[inp.id].get("writable", False):
            raise FieldError("editable", "Google doesn't let you change this calendar's events")
        config = json.loads(changes.get("config") or source["config"])
        changes["config"] = json.dumps(config | {"editable": inp.editable})
    if inp.kind is not None:
        kind = None if inp.kind == "auto" else inp.kind
        changes["config"] = json.dumps(json.loads(changes.get("config") or source["config"]) | {"kind": kind})
    if inp.on is False or (inp.on and not source["enabled"]):
        config = json.loads(changes.get("config") or source["config"])
        changes["config"] = json.dumps(put_away(ctx, source["id"], config) if not inp.on else bring_back(ctx, config))
    ctx.db.update("sources", {"id": source["id"]}, changes)
    if inp.on is not None or inp.kind is not None:
        forget_unanswered(ctx, source["id"])
        ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sync_now"}, {"value": json.dumps(ctx.now_text)})
    return Changed(
        message=f"Reading {name}" if inp.on else f"Stopped reading {name}" if inp.on is False else f"Saved {name}"
    )


def editable(config: dict[str, Any], listed: dict[str, Any]) -> bool:
    """Whether Friday saves changes back to a calendar: as you said, else whenever Google lets you write to it."""
    if not listed.get("writable", False):
        return False
    return bool(config.get("editable", True))


def source_of(ctx: Ctx, calendar_id: str, kind: str = "gcal") -> dict[str, Any] | None:
    return one(
        ctx.conn,
        "SELECT * FROM sources WHERE user_id = ? AND kind = ? AND json_extract(config, '$.calendar') = ? ORDER BY id",
        [ctx.user_id, kind, calendar_id],
    )


def reread_calendars(ctx: Ctx) -> None:
    """Every calendar read again on the next sync, which is now, as when one changes kind."""
    for source in ctx.conn.execute(
        "SELECT id FROM sources WHERE user_id = ? AND kind IN ('gcal', 'mac')", [ctx.user_id]
    ):
        forget_unanswered(ctx, source[0])
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sync_now"}, {"value": json.dumps(ctx.now_text)})


def put_away(ctx: Ctx, source_id: int, config: dict[str, Any]) -> dict[str, Any]:
    """A calendar you stop reading leaves your calendar and planning: its events from now on are put away and its
    repeats paused, and which is kept in its config so switching it back on brings them back. Switching off one
    that's already off puts away what's still out."""
    linked = [item_id for item_id, link in event_links(ctx.conn, ctx.user_id).items() if link.source_id == source_id]
    marks = ", ".join("?" * len(linked)) or "NULL"
    items = [
        r["id"]
        for r in rows(
            ctx.conn,
            f"SELECT id FROM items WHERE id IN ({marks}) AND when_kind = 'fixed' AND status = 'todo' AND end_utc > ?",
            [*linked, format_utc(ctx.now_utc)],
        )
    ]
    series = [
        r["id"]
        for r in rows(
            ctx.conn,
            f"SELECT id FROM series WHERE active = 1 AND id IN (SELECT series_id FROM items WHERE id IN ({marks}))",
            linked,
        )
    ]
    for item_id in items:
        ctx.db.update("items", {"id": item_id}, {"status": "dropped"})
    for series_id in series:
        ctx.db.update("series", {"id": series_id}, {"active": 0})
    away = config.get("put_away") or {}
    return config | {"put_away": {"items": away.get("items", []) + items, "series": away.get("series", []) + series}}


def bring_back(ctx: Ctx, config: dict[str, Any]) -> dict[str, Any]:
    """What `put_away` put away and nothing else has touched since: back on your calendar, the repeats running."""
    away = config.pop("put_away", None) or {}
    for item_id in away.get("items", []):
        if (found := ctx.db.fetch("items", {"id": item_id})) and found["status"] == "dropped":
            ctx.db.update("items", {"id": item_id}, {"status": "todo"})
    for series_id in away.get("series", []):
        if ctx.db.fetch("series", {"id": series_id}):
            ctx.db.update("series", {"id": series_id}, {"active": 1})
    return config


def forget_unanswered(ctx: Ctx, source_id: int) -> None:
    """Withdraw what it suggested that you haven't answered, and mark it unread, so the next sync suggests it again
    (the new way, or once it is back on). What you accepted or rejected stays."""
    for s in ctx.conn.execute(
        "SELECT s.id FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id WHERE r.source_id = ? "
        "AND s.status = 'pending'",
        [source_id],
    ).fetchall():
        ctx.db.update("suggestions", {"id": s[0]}, {"status": "superseded"})
    for r in ctx.conn.execute(
        "SELECT id FROM raw_inputs r WHERE source_id = ? AND NOT EXISTS (SELECT 1 FROM suggestions s WHERE "
        "s.raw_input_id = r.id AND s.status IN ('accepted', 'rejected'))",
        [source_id],
    ).fetchall():
        ctx.db.update("raw_inputs", {"id": r[0]}, {"content_hash": ""})  # seen as changed: suggested afresh
