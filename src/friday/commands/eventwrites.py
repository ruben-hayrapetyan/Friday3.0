"""Your events, changed in Friday, saved back to Google Calendar (COMBINED.md 69), and to the Mac's calendars.

A change you make to an event read from a calendar you may edit, or an event you make while `gcal.new_events_to`
names a calendar, is queued in `event_writes` by the command, in its transaction (so undoing the command before the
job runs takes it back). The server's job loop sends the queue once a minute. After a write, the raw input the sync
keeps for that event is brought up to date with what Google gave back, so the next sync sees nothing new instead of
suggesting your own change back to you. A new event gets a raw input and an accepted suggestion of its own, as if it
had been read from the calendar: from then on it is one of that calendar's events, changed there or here. Each change
goes through the Google account the calendar is read through.

An event read from one of the Mac's calendars is changed by the Mac app, through EventKit (so a Google calendar the Mac
reads gets it from the Mac's own sync): it asks for the queue (`mac_writes`) and says what it made of each change
(`mac_written`). The job here leaves those to it.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from friday.api.commands import Changed
from friday.api.types import Empty
from friday.commands.calendars import editable
from friday.commands.registry import Ctx, command
from friday.core.db import one, rows
from friday.core.items import Item
from friday.core.time import format_utc, parse_utc, to_local
from friday.planner.store import event_links, kv_get, load_item, load_settings
from friday.sync import gcal, google_auth

MAX_TRIES = 5
EDITING = (google_auth.EVENTS_SCOPE,)


def queue_event_write(ctx: Ctx, item: Item, op: str, target: str | None = None) -> bool:
    """Queue a save or a delete of an event, when its calendar takes changes from Friday; says whether it did. Changes
    the sync makes (an event changed in Google) are never written back. A new event goes to `target` when given (""
    keeps it only in Friday), else to the calendar Settings names for new events."""
    if item.when != "fixed" or item.id is None or ctx.actor.startswith("sync:"):
        return False
    link = event_links(ctx.conn, ctx.user_id).get(item.id)
    if link is None:
        target = ctx.settings["gcal"].new_events_to if target is None else (target or None)
        if item.id in (kv_get(ctx.conn, "friday_only_events", [], ctx.user_id) or []):
            return False  # you kept it only in Friday
        if op != "save" or target is None or item.event_kind == "shove":
            return False
        if target not in new_event_calendars(ctx.conn, ctx.user_id):
            return False  # its account was removed: kept only in Friday until you choose another calendar
        waiting = one(
            ctx.conn,
            "SELECT 1 FROM event_writes WHERE user_id = ? AND item_id = ? AND op = 'save' AND done_utc IS NULL "
            "AND tries < ?",
            [ctx.user_id, item.id, MAX_TRIES],
        )
        if waiting:
            return False  # it's still to be made, and is made as it is then: a second would make it twice
    elif not writes_to(ctx.conn, ctx.user_id, link.source_id):
        return False
    ctx.db.insert("event_writes", {"item_id": item.id, "op": op, "calendar_id": target, "queued_utc": ctx.now_text})
    return True


@command("events_to_calendar")
def events_to_calendar(ctx: Ctx, inp: Empty) -> Changed:
    """Put the events made in Friday that are still to come and on no calendar yet on the one new events go to, so
    your calendar has what Friday has (28 Oct: "put all new events that are in friday also on google"): those made
    before a calendar was chosen for new events, and every time of a repeat made here. One you kept only in Friday
    stays there, and one read from a calendar feed (Canvas) is that feed's."""
    if not ctx.settings["gcal"].new_events_to:
        return Changed(message="Choose where new events go first, in Settings → Calendars")
    from friday.commands.series import calendar_of  # series imports this module

    links = event_links(ctx.conn, ctx.user_id)
    fed = {
        r["item_id"]
        for r in rows(
            ctx.conn,
            "SELECT s.item_id FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
            "JOIN sources src ON src.id = r.source_id "
            "WHERE s.user_id = ? AND s.item_id IS NOT NULL AND src.kind = 'ics'",
            [ctx.user_id],
        )
    }
    sent = 0
    for r in rows(
        ctx.conn,
        "SELECT i.id, i.series_id, s.external_id FROM items i LEFT JOIN series s ON s.id = i.series_id "
        "WHERE i.user_id = ? AND i.when_kind = 'fixed' AND i.status = 'todo' AND i.end_utc > ? ORDER BY i.start_utc",
        [ctx.user_id, ctx.now_text],
    ):
        if r["id"] in links or r["id"] in fed or r["external_id"]:
            continue
        item = load_item(ctx.conn, r["id"], ctx.user_id)
        target = calendar_of(ctx, r["series_id"]) if r["series_id"] else None
        if item is not None and queue_event_write(ctx, item, "save", target=target):
            sent += 1
    if not sent:
        return Changed(message="Every event of yours is on a calendar already")
    return Changed(message=f"{sent} event{'s' if sent != 1 else ''} on the way to your calendar")


def new_event_calendars(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """The calendars a new event can be saved to: Google's, through your accounts, and the Mac's that may be changed,
    through the Mac app (27 Oct: your Gmail calendar comes in through the Mac, so a new event goes there that way)."""
    google = {c["id"] for c in kv_get(conn, "google_calendars", [], user_id)}
    return google | mac_calendar_ids(conn, user_id)


def mac_calendar_ids(conn: sqlite3.Connection, user_id: int) -> set[str]:
    """The Mac's calendars a new event may be made on."""
    return {c["id"] for c in kv_get(conn, "mac_calendars", [], user_id) if c.get("writable")}


def writes_to(conn: sqlite3.Connection, user_id: int, source_id: int) -> bool:
    """Whether changes here go back to the event's calendar: a Google one or one of the Mac's that may be changed."""
    source = one(conn, "SELECT kind, config FROM sources WHERE id = ?", [source_id])
    if source is None or source["kind"] not in ("gcal", "mac"):
        return False
    config = json.loads(source["config"])
    key = "google_calendars" if source["kind"] == "gcal" else "mac_calendars"
    listed = {c["id"]: c for c in kv_get(conn, key, [], user_id)}
    return editable(config, listed.get(config.get("calendar"), {}))


def event_body(item: Item, tz: str) -> dict[str, Any]:
    """The fields Friday owns: title, notes, place and times (whole days for an all-day event)."""
    assert item.start_utc and item.end_utc
    start, end = parse_utc(item.start_utc), parse_utc(item.end_utc)
    body: dict[str, Any] = {"summary": item.title, "description": item.notes}
    if item.location:
        body["location"] = item.location
    local_start, local_end = to_local(start, tz), to_local(end, tz)
    if local_start.hour == local_start.minute == 0 and local_end.hour == local_end.minute == 0 and end > start:
        body |= {"start": {"date": local_start.date().isoformat()}, "end": {"date": local_end.date().isoformat()}}
    else:
        body |= {"start": {"dateTime": gcal.rfc3339(start)}, "end": {"dateTime": gcal.rfc3339(end)}}
    return body


def change_body(conn: sqlite3.Connection, item: Item, tz: str) -> dict[str, Any]:
    """What a change to an event already on a calendar sends: its times, and its title only if you renamed it here.
    Friday tidies titles as it reads them ("Chem 2090 Lec (room 200)" is "Chem 2090 Lecture" here) and never reads
    descriptions, so sending either back as it stands would overwrite what the calendar says."""
    body = event_body(item, tz)
    kept = {"start": body["start"], "end": body["end"]}
    place = {"location": item.location or ""} if relocated(conn, item) else {}
    return kept | ({"summary": item.title} if renamed(conn, item) else {}) | place


def renamed(conn: sqlite3.Connection, item: Item) -> bool:
    """Whether the title isn't the one Friday made of the calendar's: the latest it accepted from the calendar."""
    for r in rows(
        conn,
        "SELECT input FROM suggestions WHERE item_id = ? AND status = 'accepted' ORDER BY id DESC",
        [item.id],
    ):
        title = json.loads(r["input"] or "{}").get("title")
        if title:
            return title != item.title
    return False


def relocated(conn: sqlite3.Connection, item: Item) -> bool:
    """Whether its place isn't the calendar's: the latest Friday accepted from the calendar (none, before places were
    read, is no place)."""
    for r in rows(
        conn,
        "SELECT input FROM suggestions WHERE item_id = ? AND status = 'accepted' ORDER BY id DESC",
        [item.id],
    ):
        read = json.loads(r["input"] or "{}")
        if "title" in read or "location" in read:
            return (read.get("location") or None) != (item.location or None)
    return False


class NeedsSignIn(Exception):
    """The calendar's account signed in before "Edit here", so Google won't take changes until it signs in again."""


def write_events(
    conn: sqlite3.Connection, now_utc: int, user_id: int = 1, folder: Path | None = None, google: Any = None
) -> int:
    """Send what's queued, each through its calendar's account; returns how many were saved or deleted. Failures are
    kept and tried again later; changes to an account that needs to sign in again wait for it."""
    links = event_links(conn, user_id)
    mac = mac_calendar_ids(conn, user_id)
    pending = [
        job
        for job in rows(
            conn,
            "SELECT * FROM event_writes WHERE user_id = ? AND done_utc IS NULL AND tries < ? ORDER BY id",
            [user_id, MAX_TRIES],
        )
        # The Mac app makes those (`mac_writes`): changes to the Mac's events, and new ones for its calendars.
        if not on_mac(links.get(job["item_id"])) and not (job["item_id"] not in links and job["calendar_id"] in mac)
    ]
    if not pending:
        return 0
    apis = google_auth.per_account(google, folder, google_auth.calendar)
    if not apis:
        return 0
    # A stand-in (tests, the demo) may change anything; a real account only once it allowed changing events.
    allowed = None if google is not None or folder is None else google_auth.accounts(folder, EDITING)
    owners = {c["id"]: c.get("account", google_auth.LEGACY) for c in kv_get(conn, "google_calendars", [], user_id)}
    made: dict[str, Any] = {}

    def google_for(calendar_id: str) -> Any:
        if calendar_id not in owners:
            raise LookupError("that calendar isn't in your Google accounts any more")
        account = google_auth.which(apis, owners[calendar_id])
        if account is None:
            raise LookupError(f"{owners[calendar_id]} isn't connected any more")
        if allowed is not None and account not in allowed:
            raise NeedsSignIn(account)
        if account not in made:
            made[account] = apis[account]()
        if made[account] is None:
            raise LookupError(f"{account or 'your Google account'} isn't connected any more")
        return made[account]

    settings = load_settings(conn, user_id)
    written = 0
    for job in pending:
        try:
            send(conn, google_for, job, settings, now_utc, user_id)
            conn.execute(
                "UPDATE event_writes SET done_utc = ?, error = NULL WHERE id = ?", [format_utc(now_utc), job["id"]]
            )
            written += 1
        except NeedsSignIn:
            continue  # the status line asks you to connect that account again
        except Exception as error:  # Google down, a revoked token, an event deleted there: kept, tried again
            conn.execute(
                "UPDATE event_writes SET tries = tries + 1, error = ? WHERE id = ?",
                [f"{type(error).__name__}: {error}"[:300], job["id"]],
            )
    return written


def on_mac(link: Any) -> bool:
    return link is not None and link.kind == "mac"


def failed_writes(conn: sqlite3.Connection, user_id: int = 1) -> list[str]:
    """Changes Friday gave up saving to Google, for the status line."""
    found = rows(
        conn,
        "SELECT w.item_id, i.title, w.error FROM event_writes w JOIN items i ON i.id = w.item_id "
        "WHERE w.user_id = ? AND w.done_utc IS NULL AND w.tries >= ? ORDER BY w.id DESC LIMIT 3",
        [user_id, MAX_TRIES],
    )
    links = event_links(conn, user_id)
    where = {r["item_id"]: "your calendar" if on_mac(links.get(r["item_id"])) else "Google" for r in found}
    return [f"Couldn't save {r['title']} to {where[r['item_id']]} ({r['error']})" for r in found]


def send(
    conn: sqlite3.Connection,
    google_for: Callable[[str], Any],
    job: dict[str, Any],
    settings: dict,
    now_utc: int,
    user_id: int,
) -> None:
    item = load_item(conn, job["item_id"], user_id)
    link = event_links(conn, user_id).get(job["item_id"])
    tz = settings["time"].timezone
    if link is not None and link.kind != "gcal":
        return  # queued before its calendar turned out to be the Mac's: nothing to send to Google
    if job["op"] == "repeat":
        if item is not None and item.start_utc and link is not None and link.calendar_id:
            repeat_there(conn, google_for(link.calendar_id), link, item, job["rule"], tz)
        return
    if job["op"] == "delete" or item is None:
        if link is not None and link.calendar_id:
            gcal.delete_event(google_for(link.calendar_id), link.calendar_id, link.event_id)
        return
    if item.status != "todo":
        return  # a change saved before it was ticked done (or skipped): nothing to send, and nothing to delete
    if link is not None and link.calendar_id:
        body = change_body(conn, item, tz)
        made = gcal.save_event(google_for(link.calendar_id), link.calendar_id, link.event_id, body)
        remember(conn, link.source_id, made, tz, settings, now_utc, user_id, None)
        return
    calendar = job["calendar_id"]
    source = one(
        conn,
        "SELECT id FROM sources WHERE user_id = ? AND kind = 'gcal' AND json_extract(config, '$.calendar') = ?",
        [user_id, calendar],
    )
    made = gcal.save_event(google_for(calendar), calendar, None, event_body(item, tz))
    # Tied to the event either way: a calendar Friday doesn't read gets a source of its own, switched off, so the
    # next change patches this event (instead of making another) and a delete finds it.
    source_id = source["id"] if source is not None else quiet_source(conn, calendar, user_id)
    remember(conn, source_id, made, tz, settings, now_utc, user_id, item)


def repeat_there(conn: sqlite3.Connection, service: Any, link: Any, item: Item, rule: str, tz: str) -> None:
    """The event made to repeat in its calendar; this time is now the repeat's first, which Google lists under an id
    of its own (the event's and its start), so the event's raw input takes that id at once: the next sync finds this
    time rather than dropping it as gone (the later times join the series). Then, if Google says, what it says of it,
    so that sync finds it unchanged; if it doesn't, the sync reads this time as an edit, which follows the calendar.
    A repeating event's times name their zone, as Google asks (an event Friday made gave only an offset)."""
    body = event_body(item, tz)
    for side in ("start", "end"):
        if "dateTime" in body[side]:
            body[side] = body[side] | {"timeZone": tz}
    gcal.save_event(
        service,
        link.calendar_id,
        link.event_id,
        {"recurrence": [f"RRULE:{google_rule(rule, tz)}"], "start": body["start"], "end": body["end"]},
    )
    start = datetime.fromtimestamp(parse_utc(item.start_utc) * 60, UTC)
    first_id = (
        f"{link.event_id}_{start:%Y%m%d}" if "date" in body["start"] else f"{link.event_id}_{start:%Y%m%dT%H%M%SZ}"
    )
    if not one(
        conn, "SELECT 1 AS yes FROM raw_inputs WHERE source_id = ? AND external_id = ?", [link.source_id, first_id]
    ):
        conn.execute(
            "UPDATE raw_inputs SET external_id = ?, content_hash = '' WHERE source_id = ? AND external_id = ?",
            [first_id, link.source_id, link.event_id],
        )
    try:
        first = gcal.first_instance(service, link.calendar_id, link.event_id, gcal.rfc3339(parse_utc(item.start_utc)))
    except Exception:  # Google down a moment: the sync reads it instead
        return
    if first is not None and first["id"] == first_id:
        text, digest = event_digest(first)
        conn.execute(
            "UPDATE raw_inputs SET content = ?, content_hash = ?, title = ? WHERE source_id = ? AND external_id = ?",
            [text, digest, (first.get("summary") or "").strip(), link.source_id, first_id],
        )


def google_rule(rule: str, tz: str) -> str:
    """A rule as Google takes it for a timed event: an end (`UNTIL`) in UTC, as RFC 5545 asks."""
    parts = []
    for part in rule.split(";"):
        if part.startswith("UNTIL=") and not part.endswith("Z") and "T" in part:
            local = datetime.strptime(part.removeprefix("UNTIL="), "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo(tz))
            part = f"UNTIL={local.astimezone(UTC):%Y%m%dT%H%M%SZ}"
        parts.append(part)
    return ";".join(parts)


def quiet_source(conn: sqlite3.Connection, calendar: str, user_id: int) -> int:
    """A switched-off source for a Google calendar Friday writes new events to but doesn't read."""
    listed = next((c for c in kv_get(conn, "google_calendars", [], user_id) if c["id"] == calendar), {})
    name = base = listed.get("source_name") or listed.get("name") or calendar
    n = 1
    while one(conn, "SELECT 1 FROM sources WHERE user_id = ? AND kind = 'gcal' AND name = ?", [user_id, name]):
        n += 1
        name = f"{base} {n}"
    return int(
        conn.execute(
            "INSERT INTO sources (user_id, kind, name, config, trusted, enabled) VALUES (?, 'gcal', ?, ?, 0, 0)",
            [user_id, name, json.dumps({"calendar": calendar})],
        ).lastrowid
        or 0
    )


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
        fields = {"title": new_item.title, "when": "fixed", "location": new_item.location or None}
        conn.execute(
            "INSERT INTO suggestions (user_id, raw_input_id, command, input, status, created_utc, decided_utc, "
            "item_id) VALUES (?, ?, 'add', ?, 'accepted', ?, ?, ?)",
            [user_id, raw, json.dumps(fields), format_utc(now_utc), format_utc(now_utc), new_item.id],
        )


def event_digest(event: dict[str, Any]) -> tuple[str, str]:
    """An event's text and hash exactly as `ics.google_event` makes them, so the next sync finds it unchanged."""
    summary = (event.get("summary") or "").strip() or "Busy"
    location = (event.get("location") or "").strip()
    text = json.dumps(
        {"summary": summary, "start": event.get("start", {}), "end": event.get("end", {})}
        | ({"location": location} if location else {}),
        sort_keys=True,
    )
    return text, hashlib.sha256(text.encode()).hexdigest()
