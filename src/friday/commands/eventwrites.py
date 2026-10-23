"""Your events, changed in Friday, saved back to Google Calendar (COMBINED.md 69).

A change you make to an event read from a calendar you may edit, or an event you make while `gcal.new_events_to`
names a calendar, is queued in `event_writes` by the command, in its transaction (so undoing the command before the
job runs takes it back). The server's job loop sends the queue once a minute. After a write, the raw input the sync
keeps for that event is brought up to date with what Google gave back, so the next sync sees nothing new instead of
suggesting your own change back to you. A new event gets a raw input and an accepted suggestion of its own, as if it
had been read from the calendar: from then on it is one of that calendar's events, changed there or here.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from friday.commands.calendars import editable
from friday.commands.registry import Ctx
from friday.core.db import one, rows
from friday.core.items import Item
from friday.core.time import format_utc, parse_utc, to_local
from friday.planner.store import event_links, kv_get, load_item, load_settings
from friday.sync import gcal, google_auth

MAX_TRIES = 5


def queue_event_write(ctx: Ctx, item: Item, op: str) -> None:
    """Queue a save or a delete of an event, when its calendar takes changes from Friday. Changes the sync makes (an
    event changed in Google) are never written back."""
    if item.when != "fixed" or item.id is None or ctx.actor.startswith("sync:"):
        return
    link = event_links(ctx.conn, ctx.user_id).get(item.id)
    target = None
    if link is None:
        target = ctx.settings["gcal"].new_events_to
        if op != "save" or target is None or item.event_kind == "shove":
            return
    elif not writes_to(ctx.conn, ctx.user_id, link.source_id):
        return
    ctx.db.insert("event_writes", {"item_id": item.id, "op": op, "calendar_id": target, "queued_utc": ctx.now_text})


def writes_to(conn: sqlite3.Connection, user_id: int, source_id: int) -> bool:
    source = one(conn, "SELECT config FROM sources WHERE id = ?", [source_id])
    if source is None:
        return False
    config = json.loads(source["config"])
    listed = {c["id"]: c for c in kv_get(conn, "google_calendars", [], user_id)}
    return editable(config, listed.get(config.get("calendar"), {}))


def event_body(item: Item, tz: str) -> dict[str, Any]:
    """The fields Friday owns: title, notes and times (whole days for an all-day event)."""
    assert item.start_utc and item.end_utc
    start, end = parse_utc(item.start_utc), parse_utc(item.end_utc)
    body: dict[str, Any] = {"summary": item.title, "description": item.notes}
    local_start, local_end = to_local(start, tz), to_local(end, tz)
    if local_start.hour == local_start.minute == 0 and local_end.hour == local_end.minute == 0 and end > start:
        body |= {"start": {"date": local_start.date().isoformat()}, "end": {"date": local_end.date().isoformat()}}
    else:
        body |= {"start": {"dateTime": gcal.rfc3339(start)}, "end": {"dateTime": gcal.rfc3339(end)}}
    return body


def write_events(
    conn: sqlite3.Connection, now_utc: int, user_id: int = 1, folder: Path | None = None, google: Any = None
) -> int:
    """Send what's queued; returns how many were saved or deleted. Failures are kept and tried again later."""
    pending = rows(
        conn,
        "SELECT * FROM event_writes WHERE user_id = ? AND done_utc IS NULL AND tries < ? ORDER BY id",
        [user_id, MAX_TRIES],
    )
    if not pending:
        return 0
    google = google or (google_auth.calendar(folder) if folder else None)
    if google is None:
        return 0
    settings = load_settings(conn, user_id)
    written = 0
    for job in pending:
        try:
            send(conn, google, job, settings, now_utc, user_id)
            conn.execute(
                "UPDATE event_writes SET done_utc = ?, error = NULL WHERE id = ?", [format_utc(now_utc), job["id"]]
            )
            written += 1
        except Exception as error:  # Google down, a revoked token, an event deleted there: kept, tried again
            conn.execute(
                "UPDATE event_writes SET tries = tries + 1, error = ? WHERE id = ?",
                [f"{type(error).__name__}: {error}"[:300], job["id"]],
            )
    return written


def failed_writes(conn: sqlite3.Connection, user_id: int = 1) -> list[str]:
    """Changes Friday gave up saving to Google, for the status line."""
    found = rows(
        conn,
        "SELECT i.title, w.error FROM event_writes w JOIN items i ON i.id = w.item_id "
        "WHERE w.user_id = ? AND w.done_utc IS NULL AND w.tries >= ? ORDER BY w.id DESC LIMIT 3",
        [user_id, MAX_TRIES],
    )
    return [f"Couldn't save {r['title']} to Google ({r['error']})" for r in found]


def send(
    conn: sqlite3.Connection, google: Any, job: dict[str, Any], settings: dict, now_utc: int, user_id: int
) -> None:
    item = load_item(conn, job["item_id"], user_id)
    link = event_links(conn, user_id).get(job["item_id"])
    tz = settings["time"].timezone
    if job["op"] == "delete" or item is None or item.status != "todo":
        if link is not None and link.calendar_id:
            gcal.delete_event(google, link.calendar_id, link.event_id)
        return
    if link is not None and link.calendar_id:
        made = gcal.save_event(google, link.calendar_id, link.event_id, event_body(item, tz))
        remember(conn, link.source_id, made, tz, settings, now_utc, user_id, None)
        return
    calendar = job["calendar_id"]
    source = one(
        conn,
        "SELECT id FROM sources WHERE user_id = ? AND kind = 'gcal' AND json_extract(config, '$.calendar') = ?",
        [user_id, calendar],
    )
    made = gcal.save_event(google, calendar, None, event_body(item, tz))
    if source is not None:
        remember(conn, source["id"], made, tz, settings, now_utc, user_id, item)


def remember(
    conn: sqlite3.Connection,
    source_id: int,
    event: dict[str, Any],
    tz: str,
    settings: dict,
    now_utc: int,
    user_id: int,
    new_item: Item | None,
) -> None:
    """Keep what Google gave back as the event's raw input, as the sync would have read it; a new event also gets
    the accepted suggestion that ties it to the item, the way a calendar's events are tied to theirs."""
    text, digest = event_digest(event)
    title = (event.get("summary") or "").strip()
    seen = one(conn, "SELECT id FROM raw_inputs WHERE source_id = ? AND external_id = ?", [source_id, event["id"]])
    if seen is not None:
        conn.execute(
            "UPDATE raw_inputs SET content = ?, content_hash = ?, title = ?, received_utc = ?, status = 'extracted' "
            "WHERE id = ?",
            [text, digest, title, format_utc(now_utc), seen["id"]],
        )
        return
    raw = conn.execute(
        "INSERT INTO raw_inputs (user_id, source_id, external_id, received_utc, content_hash, title, content, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'extracted')",
        [user_id, source_id, event["id"], format_utc(now_utc), digest, title, text],
    ).lastrowid
    if new_item is not None:
        fields = {"title": new_item.title, "when": "fixed"}
        conn.execute(
            "INSERT INTO suggestions (user_id, raw_input_id, command, input, status, created_utc, decided_utc, "
            "item_id) VALUES (?, ?, 'add', ?, 'accepted', ?, ?, ?)",
            [user_id, raw, json.dumps(fields), format_utc(now_utc), format_utc(now_utc), new_item.id],
        )


def event_digest(event: dict[str, Any]) -> tuple[str, str]:
    """An event's text and hash exactly as `ics.google_event` makes them, so the next sync finds it unchanged."""
    summary = (event.get("summary") or "").strip() or "Busy"
    text = json.dumps(
        {"summary": summary, "start": event.get("start", {}), "end": event.get("end", {})}, sort_keys=True
    )
    return text, hashlib.sha256(text.encode()).hexdigest()
