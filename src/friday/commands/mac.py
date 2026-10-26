"""The Mac's calendars (COMBINED.md 4), fed in by the Mac app: it posts what EventKit sees, and the sync job reads each
calendar you switched on from that, as it reads Google's, within the minute. A Mac calendar starts on unless it is a
copy of one Friday reads from Google (the same name), a subscription or birthdays; its events skip the inbox, as they
did in the Mac app.

Changes go the other way too: an event of a Mac calendar that may be changed, edited or deleted here, is queued
(`eventwrites.queue_event_write`), and the Mac app makes the change through EventKit (`mac_writes`, then
`mac_written`), so a Google calendar on the Mac gets it from the Mac's own sync. A one-off event's id carries its
start, so a move gives it a new one: the answer brings the event as it now is, and its raw input (and the last
reading the Mac posted) take the new id and times, so the next sync finds nothing new rather than a vanished event
and a new one."""

import json
import re
from datetime import date, datetime
from typing import Any

from friday.api.commands import Changed, MacCalendar, MacEvent, MacSyncInput, MacWrittenInput
from friday.api.types import Empty
from friday.api.views import GoogleCalendarOut, MacWriteOut
from friday.commands.calendars import editable, natural, source_of
from friday.commands.eventwrites import MAX_TRIES, event_body, event_digest, renamed
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.time import format_local, local_midnight, parse_utc, to_local, to_utc
from friday.planner.store import event_links, kv_get, load_item

OFF_TYPES = ("subscription", "birthday")
OCCURRENCE = re.compile(r"^(.+)@(\d+)$")  # the Mac app's "<EventKit identifier>@<occurrence start, Unix seconds>"


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
    seed(ctx, inp.calendars, named)
    keep_one_offs(ctx, inp.events)
    put(ctx, "mac_calendars", listed)
    put(ctx, "mac_events", events)
    put(ctx, "mac_window", window)
    put(ctx, "mac_sync_now", ctx.now_text)
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
                editable=editable(config, c),  # the Mac app saves changes made here back to it
                account=c.get("account") or None,
                also_google=c["name"] in google,
            )
        )
    return sorted(out, key=lambda c: natural(c.name))


@query("mac_writes")
def mac_writes(ctx: Ctx, inp: Empty) -> list[MacWriteOut]:
    """Changes to the Mac's events waiting for the Mac app, oldest first: an event's times, and its title
    only if you renamed it here (never its notes, which Friday doesn't read from the Mac); or a delete."""
    links = event_links(ctx.conn, ctx.user_id)
    out = []
    for job in rows(
        ctx.conn,
        "SELECT * FROM event_writes WHERE user_id = ? AND done_utc IS NULL AND tries < ? ORDER BY id",
        [ctx.user_id, MAX_TRIES],
    ):
        link = links.get(job["item_id"])
        if link is None or link.kind != "mac" or not link.calendar_id:
            continue
        item = load_item(ctx.conn, job["item_id"], ctx.user_id)
        where = {
            "id": job["id"],
            "calendar": link.calendar_id,
            "event": occurrence_of(ctx, link.source_id, link.event_id),
        }
        if job["op"] == "delete":
            out.append(MacWriteOut(op="delete", **where))
        elif item is not None and item.status == "todo" and item.start_utc and item.end_utc:
            body = event_body(item, ctx.tz)
            day = "date" in body["start"]
            when = "date" if day else "dateTime"
            title = item.title if renamed(ctx.conn, item) else None
            start, end = body["start"][when], body["end"][when]
            out.append(MacWriteOut(op="save", title=title, start=start, end=end, all_day=day, **where))
    return out


@command("mac_written", logged=False)  # the Mac app's report, like `mac_sync`: nothing of yours to undo
def mac_written(ctx: Ctx, inp: MacWrittenInput) -> Changed:
    """What the Mac app made of a change: done, with the event as it now is; or why not, tried again
    up to five times (then the status line says so)."""
    job = one(ctx.conn, "SELECT * FROM event_writes WHERE id = ? AND user_id = ?", [inp.id, ctx.user_id])
    if job is None:
        raise FieldError("id", f"no change {inp.id} is waiting")
    if job["done_utc"]:
        return Changed(message="Already saved")
    if not inp.ok:
        ctx.db.update(
            "event_writes", {"id": inp.id}, {"tries": job["tries"] + 1, "error": (inp.error or "failed")[:300]}
        )
        return Changed(message="Kept, to try again")
    ctx.db.update("event_writes", {"id": inp.id}, {"done_utc": ctx.now_text, "error": None})
    if inp.event is not None and job["op"] == "save":
        settle(ctx, job["item_id"], inp.event)
    return Changed(message="Saved to your calendar" if job["op"] == "save" else "Deleted from your calendar")


def settle(ctx: Ctx, item_id: int, event: MacEvent) -> None:
    """The event as the Mac app left it becomes what Friday last read of it: the raw input takes its (maybe new) id
    and times, and so does the last reading the Mac posted, in case the sync job reads that before the next one."""
    link = event_links(ctx.conn, ctx.user_id).get(item_id)
    if link is None or link.kind != "mac":
        return
    shaped = google_shape(event)
    text, digest = event_digest(shaped)
    raw = one(
        ctx.conn, "SELECT id FROM raw_inputs WHERE source_id = ? AND external_id = ?", [link.source_id, link.event_id]
    )
    taken = one(
        ctx.conn,
        "SELECT id FROM raw_inputs WHERE source_id = ? AND external_id = ? AND external_id != ?",
        [link.source_id, event.id, link.event_id],
    )
    if raw is not None and taken is None:
        title = (shaped.get("summary") or "").strip()
        ctx.db.update(
            "raw_inputs",
            {"id": raw["id"]},
            {"external_id": event.id, "content": text, "content_hash": digest, "title": title},
        )
    posted = kv_get(ctx.conn, "mac_events", {}, ctx.user_id)
    if link.calendar_id in posted:
        posted[link.calendar_id] = [shaped if e.get("id") == link.event_id else e for e in posted[link.calendar_id]]
        put(ctx, "mac_events", posted)


def event_id(e: MacEvent) -> str:
    """The event's id in Friday: a repeat's occurrence keeps the start the Mac app adds (that's what tells its
    occurrences apart), a one-off event drops it, so moving it in Calendar keeps it the same event."""
    found = OCCURRENCE.match(e.id)
    return found[1] if found and not e.series else e.id


def keep_one_offs(ctx: Ctx, events: list[MacEvent]) -> None:
    """One-off events read before their ids lost the start (`event_id`) take the new id, so they aren't taken for
    gone and made again: each raw input whose id is that event's identifier and a start, if it's the only one."""
    by_calendar: dict[str, list[MacEvent]] = {}
    for e in events:
        if not e.series and event_id(e) != e.id:
            by_calendar.setdefault(e.calendar, []).append(e)
    for calendar, found in by_calendar.items():
        source = source_of(ctx, calendar, "mac")
        if source is None:
            continue
        stored = rows(  # what's still current: an event moved before had its old reading set aside as gone
            ctx.conn,
            "SELECT id, external_id FROM raw_inputs WHERE source_id = ? AND status != 'ignored'",
            [source["id"]],
        )
        have = {r["external_id"] for r in stored}
        old: dict[str, list[int]] = {}
        for r in stored:
            if m := OCCURRENCE.match(r["external_id"]):
                old.setdefault(m[1], []).append(r["id"])
        for e in found:
            bare = event_id(e)
            if bare not in have and len(old.get(bare, [])) == 1:
                ctx.db.update("raw_inputs", {"id": old[bare][0]}, {"external_id": bare})
                have.add(bare)


def occurrence_of(ctx: Ctx, source_id: int, external_id: str) -> str:
    """The id the Mac app finds an event by: a one-off's (`event_id`) with its start on the calendar put back."""
    if OCCURRENCE.match(external_id):
        return external_id
    raw = one(
        ctx.conn, "SELECT content FROM raw_inputs WHERE source_id = ? AND external_id = ?", [source_id, external_id]
    )
    start = (json.loads(raw["content"] or "{}").get("start") or {}) if raw else {}
    if "dateTime" in start:
        seconds = int(datetime.fromisoformat(start["dateTime"]).timestamp())
    elif "date" in start:
        seconds = to_utc(local_midnight(date.fromisoformat(start["date"])), ctx.tz) * 60
    else:
        return external_id
    return f"{external_id}@{seconds}"


def google_shape(e: MacEvent) -> dict[str, Any]:
    """An event as Google gives one, so the Mac's go through the same reading (`ics.google_event`)."""
    when = "date" if e.all_day else "dateTime"
    shaped: dict[str, Any] = {"id": event_id(e), "summary": e.title, "start": {when: e.start}, "end": {when: e.end}}
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
            name = free_name(ctx, named[c.id])  # a calendar renamed away may still hold it until it's seen below
            ctx.db.insert("sources", {"kind": "mac", "name": name, "config": config, "trusted": 1, "enabled": int(on)})
        elif source["name"] != named[c.id]:
            taken = ctx.conn.execute(
                "SELECT 1 FROM sources WHERE user_id = ? AND kind = 'mac' AND name = ?", [ctx.user_id, named[c.id]]
            ).fetchone()
            if not taken:
                ctx.db.update("sources", {"id": source["id"]}, {"name": named[c.id]})


def free_name(ctx: Ctx, name: str) -> str:
    """The name, or numbered ("Work 2") while another of the Mac's sources has it."""
    base, n = name, 1
    while ctx.conn.execute(
        "SELECT 1 FROM sources WHERE user_id = ? AND kind = 'mac' AND name = ?", [ctx.user_id, name]
    ).fetchone():
        n += 1
        name = f"{base} {n}"
    return name


def put(ctx: Ctx, key: str, value: Any) -> None:
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": key}, {"value": json.dumps(value)})
