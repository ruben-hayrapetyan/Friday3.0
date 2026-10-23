"""The Mac's calendars (COMBINED.md 4), fed in by the Mac app: it posts what EventKit sees, and the sync job reads each
calendar you switched on from that, as it reads Google's, within the minute. A Mac calendar starts on unless it is a
copy of one Friday reads from Google (the same name), a subscription or birthdays; its events skip the inbox, as they
did in the Mac app."""

import json
from typing import Any

from friday.api.commands import Changed, MacCalendar, MacEvent, MacSyncInput
from friday.api.types import Empty
from friday.api.views import GoogleCalendarOut
from friday.commands.calendars import natural, source_of
from friday.commands.registry import Ctx, command, query
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.time import format_local, parse_utc, to_local
from friday.planner.store import kv_get

OFF_TYPES = ("subscription", "birthday")


@command("mac_sync", logged=False)  # a reading of the Mac's calendars, like the sync job's of Google: nothing to undo
def mac_sync(ctx: Ctx, inp: MacSyncInput) -> Changed:
    """The Mac's calendars and their events between `since` and `until`, from the Mac app."""
    try:
        window = {"since": parse_utc(inp.since), "until": parse_utc(inp.until)}
    except ValueError as error:
        raise FieldError("since", f"times need an offset: {error}") from None
    if window["until"] <= window["since"]:
        raise FieldError("until", "until comes before since")
    named = source_names(inp.calendars)
    known = {c.id for c in inp.calendars}
    strays = {e.calendar for e in inp.events} - known
    if strays:
        raise FieldError("events", f"events on calendars not listed: {', '.join(sorted(strays))}")
    events: dict[str, list[dict[str, Any]]] = {c.id: [] for c in inp.calendars}
    for e in inp.events:
        events[e.calendar].append(google_shape(e))
    listed = [c.model_dump() | {"source_name": named[c.id]} for c in inp.calendars]
    put(ctx, "mac_calendars", listed)
    put(ctx, "mac_events", events)
    put(ctx, "mac_window", window)
    put(ctx, "mac_sync_now", ctx.now_text)
    seed(ctx, inp.calendars, named)
    n = len(inp.events)
    return Changed(message=f"Read {n} event{'' if n == 1 else 's'} on {len(inp.calendars)} Mac calendars")


@query("mac_calendars")
def mac_calendars(ctx: Ctx, inp: Empty) -> list[GoogleCalendarOut]:
    """The Mac's calendars as the Mac app last saw them, alphabetized, with whether each is read and how."""
    google = {c["name"] for c in kv_get(ctx.conn, "google_calendars", [], ctx.user_id)}
    out = []
    for c in kv_get(ctx.conn, "mac_calendars", [], ctx.user_id):
        source = source_of(ctx, c["id"], "mac")
        config = json.loads(source["config"]) if source else {}
        synced = source and source["last_sync_utc"]
        out.append(
            GoogleCalendarOut(
                id=c["id"],
                name=c["source_name"],
                primary=False,
                on=bool(source and source["enabled"]),
                kind=config.get("kind") or "auto",
                trusted=bool(source and source["trusted"]),
                last_sync=format_local(to_local(parse_utc(synced), ctx.tz)) if synced else None,
                error=source["last_error"] if source else None,
                writable=c.get("writable", False),
                editable=False,  # Friday doesn't change the Mac's calendars yet
                account=c.get("account") or None,
                also_google=c["name"] in google,
            )
        )
    return sorted(out, key=lambda c: natural(c.name))


def google_shape(e: MacEvent) -> dict[str, Any]:
    """An event as Google gives one, so the Mac's go through the same reading (`ics.google_event`)."""
    when = "date" if e.all_day else "dateTime"
    shaped: dict[str, Any] = {"id": e.id, "summary": e.title, "start": {when: e.start}, "end": {when: e.end}}
    if e.series:
        shaped["recurringEventId"] = e.series
    if e.free:
        shaped["transparency"] = "transparent"
    if e.declined:
        shaped["attendees"] = [{"self": True, "responseStatus": "declined"}]
    return shaped


def source_names(calendars: list[MacCalendar]) -> dict[str, str]:
    """Each calendar's name in Friday: its own, or with its account when two share a name ("Calendar (iCloud)")."""
    counts: dict[str, int] = {}
    for c in calendars:
        counts[c.name] = counts.get(c.name, 0) + 1
    named = {c.id: f"{c.name} ({c.account or c.type})" if counts[c.name] > 1 else c.name for c in calendars}
    seen: dict[str, int] = {}
    for c in calendars:  # the same name and account twice: numbered, so every calendar is its own source
        seen[named[c.id]] = seen.get(named[c.id], 0) + 1
        if seen[named[c.id]] > 1:
            named[c.id] = f"{named[c.id]} {seen[named[c.id]]}"
    return named


def default_on(c: MacCalendar, google: set[str]) -> bool:
    return c.type not in OFF_TYPES and c.name not in google


def seed(ctx: Ctx, calendars: list[MacCalendar], named: dict[str, str]) -> None:
    """A calendar seen for the first time becomes a source; after that Settings decides. A renamed one keeps its
    source and takes the new name."""
    google = {c["name"] for c in kv_get(ctx.conn, "google_calendars", [], ctx.user_id)}
    for c in calendars:
        source = source_of(ctx, c.id, "mac")
        listed = {x.id for x in calendars}
        if source is None:
            stale = rows(
                ctx.conn,
                "SELECT * FROM sources WHERE user_id = ? AND kind = 'mac' AND name = ?",
                [ctx.user_id, named[c.id]],
            )
            if stale and json.loads(stale[0]["config"]).get("calendar") not in listed:
                # the calendar made again under the same name: it takes over the old one's source and settings
                config = json.loads(stale[0]["config"]) | {"calendar": c.id}
                ctx.db.update("sources", {"id": stale[0]["id"]}, {"config": json.dumps(config)})
                continue
            config = json.dumps({"calendar": c.id})
            on = default_on(c, google)
            ctx.db.insert(
                "sources", {"kind": "mac", "name": named[c.id], "config": config, "trusted": 1, "enabled": int(on)}
            )
        elif source["name"] != named[c.id]:
            taken = ctx.conn.execute(
                "SELECT 1 FROM sources WHERE user_id = ? AND kind = 'mac' AND name = ?", [ctx.user_id, named[c.id]]
            ).fetchone()
            if not taken:
                ctx.db.update("sources", {"id": source["id"]}, {"name": named[c.id]})


def put(ctx: Ctx, key: str, value: Any) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": key}, {"value": json.dumps(value)})
