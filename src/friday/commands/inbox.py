"""The inbox (DESIGN §22.1): sources, suggestions and what you decide about them. Accepting runs the suggested
`add` (or `edit`) as you, so it is logged and undoable like anything else. Fetching and extracting run in the job
loop (`commands/fetching.py`), never in a request.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any

from friday.api.commands import (
    AddInput,
    AskInput,
    BatchInput,
    Changed,
    DocumentInput,
    EditInput,
    ItemRef,
    SeriesRef,
    SourceEditInput,
    SourceInput,
    SourceRemoveInput,
    SuggestionInput,
)
from friday.api.types import Empty
from friday.api.views import DocumentOut, InboxOut, SetAsideOut, SourceOut, SuggestionOut
from friday.commands.duplicates import RESTORED, set_aside_waiting
from friday.commands.fields import require_item
from friday.commands.items import add, drop, edit, find_item, guessed_minutes
from friday.commands.registry import Ctx, command, query
from friday.commands.series import attach_to_series, imported_fields, load_series, series_stop
from friday.core.db import one, rows
from friday.core.html_text import html_text, looks_like_html
from friday.core.items import FieldError
from friday.core.recurrence import describe
from friday.core.textnorm import course_tag
from friday.core.time import format_utc
from friday.ingest import extract, llm
from friday.integrations.links import LINKS
from friday.planner.store import area_names, kv_get

FIXED_FIRST = ("Class", "Exam", "Meeting", "Appointment", "Event")  # events before the prep that comes `before:` them


def source_row(ctx: Ctx, source_id: int) -> dict[str, Any]:
    found = one(ctx.conn, "SELECT * FROM sources WHERE user_id = ? AND id = ?", [ctx.user_id, source_id])
    if found is None:
        raise FieldError("id", f"no source {source_id}")
    return found


@command("source_add")
def source_add(ctx: Ctx, inp: SourceInput) -> Changed:
    """Add a calendar feed to read into the inbox; one from a service's box is read as that service's (C96)."""
    config: dict[str, Any] = {"url": inp.url}
    trusted = inp.trusted
    if inp.service is not None:
        service = LINKS.get(inp.service)
        if service is None:
            raise FieldError("service", f"Friday doesn't know “{inp.service}”")
        config |= {"service": inp.service, "kind": service.kind}
        trusted = trusted or service.trusted
    added = {"kind": inp.kind, "name": inp.name, "config": json.dumps(config), "trusted": int(trusted)}
    same = one(ctx.conn, "SELECT id, enabled FROM sources WHERE user_id = ? AND kind = ? AND name = ?",
               [ctx.user_id, inp.kind, inp.name])  # fmt: skip
    if same and same["enabled"]:
        raise FieldError("name", f"You already read a link called {inp.name}: remove it first, or give this one a name")
    if same:  # one you removed (10 Nov: adding it again was refused, the name taken): read again, at its new address
        again = {"enabled": 1, "last_error": None, "failures": 0, "last_sync_utc": None}
        ctx.db.update("sources", {"id": same["id"]}, added | again)
    else:
        ctx.db.insert("sources", added)
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sync_now"}, {"value": json.dumps(ctx.now_text)})
    return Changed(message=f"Added {inp.name}; it syncs within a minute")


@command("source_edit")
def source_edit(ctx: Ctx, inp: SourceEditInput) -> Changed:
    """Rename a source, change its URL, trust it, or switch it off."""
    found = source_row(ctx, inp.id)
    changes: dict[str, Any] = {}
    if inp.name is not None:
        taken = one(ctx.conn, "SELECT 1 AS yes FROM sources WHERE user_id = ? AND kind = ? AND name = ? AND id != ?",
                    [ctx.user_id, found["kind"], inp.name, inp.id])  # fmt: skip
        if taken:  # was a database error (audit, 12 Nov)
            raise FieldError("name", f"You already read one called {inp.name}: give this one another name")
        changes["name"] = inp.name
    if inp.url is not None:
        changes["config"] = json.dumps(json.loads(found["config"]) | {"url": inp.url})
    if inp.trusted is not None:
        changes["trusted"] = int(inp.trusted)
    if inp.enabled is not None:
        changes["enabled"] = int(inp.enabled)
    ctx.db.update("sources", {"id": inp.id}, changes)
    return Changed(message=f"Saved {changes.get('name', found['name'])}")


@command("source_remove")
def source_remove(ctx: Ctx, inp: SourceRemoveInput) -> Changed:
    """Stop reading a source; with `forget`, also delete what it brought in that you haven't accepted."""
    found = source_row(ctx, inp.id)
    if inp.forget:
        kept = 0
        for r in rows(ctx.conn, "SELECT id FROM raw_inputs WHERE source_id = ?", [inp.id]):
            for s in rows(ctx.conn, "SELECT id, status FROM suggestions WHERE raw_input_id = ?", [r["id"]]):
                if s["status"] == "accepted":
                    # yours now (audit, 12 Nov: forgetting deleted these too): let go of the input, whose delete
                    # would otherwise take it along
                    ctx.db.update("suggestions", {"id": s["id"]}, {"raw_input_id": None})
                    kept += 1
                else:
                    ctx.db.delete("suggestions", {"id": s["id"]})
            ctx.db.delete("raw_inputs", {"id": r["id"]})
        ctx.db.delete("sources", {"id": inp.id})
        what = f"; the {kept} you accepted stay" if kept > 1 else "; the one you accepted stays" if kept else ""
        return Changed(message=f"Removed {found['name']} and what it brought in{what}")
    ctx.db.update("sources", {"id": inp.id}, {"enabled": 0})
    return Changed(message=f"Stopped reading {found['name']}")


@command("sync_now")
def sync_now(ctx: Ctx, inp: Empty) -> Changed:
    """Read every source within the minute instead of at the next poll."""
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sync_now"}, {"value": json.dumps(ctx.now_text)})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "integrations_now"}, {"value": json.dumps(True)})  # C96
    return Changed(message="Syncing within a minute")


@command("document_add")
def document_add(ctx: Ctx, inp: DocumentInput) -> Changed:
    """A document to read for tasks (a syllabus, a handout): it is read within a minute, into the inbox."""
    if len(inp.content) > 14_000_000:
        raise FieldError("content", "too big; the limit is about 10 MB")
    content, media_type = inp.content, inp.media_type
    if looks_like_html(inp.name, media_type, content):  # a saved web page: read as the text a reader sees
        content, media_type = html_text(content), "text/plain"
        if not content:
            raise FieldError("content", f"{inp.name} has no text in it")
    source = one(ctx.conn, "SELECT id FROM sources WHERE user_id = ? AND kind = 'upload'", [ctx.user_id])
    source_id = source["id"] if source else ctx.db.insert("sources", {"kind": "upload", "name": "Uploads"})
    digest = hashlib.sha256(inp.content.encode()).hexdigest()
    # The same file again (29 Oct: a syllabus uploaded twice was a server error): what became of it, or, if it
    # couldn't be read, read again.
    before = one(ctx.conn, "SELECT * FROM raw_inputs WHERE source_id = ? AND external_id = ?", [source_id, digest[:24]])
    if before is not None:
        if before["status"] == "failed":
            ctx.db.update("raw_inputs", {"id": before["id"]}, {"status": "new", "error": None})
            return Changed(message=f"Reading {inp.name} again; its suggestions come into the inbox within a minute")
        return Changed(message=f"You uploaded {inp.name} already: {became(ctx, before)}")
    ctx.db.insert(
        "raw_inputs",
        {
            "source_id": source_id,
            "external_id": digest[:24],
            "received_utc": ctx.now_text,
            "content_hash": digest,
            "title": inp.name,
            "media_type": media_type,
            "content": content,
        },
    )
    return Changed(message=f"Reading {inp.name}; its suggestions come into the inbox within a minute")


def became(ctx: Ctx, raw: dict) -> str:
    """What an uploaded document came to, in a few words: still being read, or what it found and where that went."""
    if raw["status"] == "new":
        return "it's still being read"
    twins = dict(kv_get(ctx.conn, "set_aside_twins", {}, ctx.user_id) or {})
    found = rows(ctx.conn, "SELECT id, status, duplicate_of FROM suggestions WHERE raw_input_id = ?", [raw["id"]])
    if not found:
        return "it was read, and had nothing to plan in it"

    def count(test: Any) -> int:
        return sum(1 for s in found if test(s))

    parts = [
        (count(lambda s: s["status"] == "pending"), "waiting in your Inbox"),
        (count(lambda s: s["status"] == "accepted"), "added"),
        (count(lambda s: s["status"] == "superseded" and s["duplicate_of"] is not None), "you have already"),
        (count(lambda s: s["status"] == "superseded" and str(s["id"]) in twins), "in your Inbox from elsewhere"),
        (count(lambda s: s["status"] == "rejected"), "turned down"),
    ]
    return f"it found {len(found)}: " + ", ".join(f"{n} {say}" for n, say in parts if n)


@query("documents")
def documents(ctx: Ctx, inp: Empty) -> list[DocumentOut]:
    """Every syllabus or handout you uploaded, newest first: read or not (and why), and what it found."""
    twins = dict(kv_get(ctx.conn, "set_aside_twins", {}, ctx.user_id) or {})  # set aside for the same one waiting
    out = []
    for r in rows(
        ctx.conn,
        "SELECT r.*, (SELECT count(*) FROM suggestions s WHERE s.raw_input_id = r.id) AS found, "
        "(SELECT count(*) FROM suggestions s WHERE s.raw_input_id = r.id AND s.status = 'pending') AS waiting, "
        "(SELECT count(*) FROM suggestions s WHERE s.raw_input_id = r.id AND s.status = 'accepted') AS accepted, "
        "(SELECT count(*) FROM suggestions s WHERE s.raw_input_id = r.id AND s.status = 'superseded' "
        "AND s.duplicate_of IS NOT NULL) AS aside, "
        "(SELECT group_concat(s.id) FROM suggestions s WHERE s.raw_input_id = r.id AND s.status = 'superseded' "
        "AND s.duplicate_of IS NULL) AS twins "
        "FROM raw_inputs r JOIN sources src ON src.id = r.source_id WHERE r.user_id = ? AND src.kind = 'upload' "
        "ORDER BY r.received_utc DESC, r.id DESC",
        [ctx.user_id],
    ):
        media = r["media_type"] or ""
        status = {"new": "reading", "failed": "failed", "ignored": "skipped"}.get(r["status"], "read")
        out.append(
            DocumentOut(
                id=r["id"],
                name=r["title"] or "Untitled",
                kind="pdf" if media == "application/pdf" else "image" if media.startswith("image/") else "text",
                received=ctx.local(r["received_utc"]) or "",
                status=status,
                error=r["error"] if status == "failed" else None,
                found=r["found"],
                waiting=r["waiting"],
                accepted=r["accepted"],
                aside=r["aside"],
                elsewhere=sum(1 for i in (r["twins"] or "").split(",") if i and i in twins),
            )
        )
    return out


@command("document_retry")
def document_retry(ctx: Ctx, inp: ItemRef) -> Changed:
    """Read a document again that couldn't be read (now that it can be: a PDF's text is read out for the claude
    command); it's read within a minute, into the inbox."""
    found = one(
        ctx.conn,
        "SELECT r.* FROM raw_inputs r JOIN sources s ON s.id = r.source_id WHERE r.id = ? AND r.user_id = ? "
        "AND s.kind = 'upload'",
        [inp.id, ctx.user_id],
    )
    if found is None:
        raise FieldError("id", f"no uploaded document {inp.id}")
    if found["status"] != "failed":
        raise FieldError("id", f"{found['title']} isn't one that failed")
    ctx.db.update("raw_inputs", {"id": inp.id}, {"status": "new", "error": None})
    return Changed(message=f"Reading {found['title']} again; what it finds comes into the inbox within a minute")


@command("suggestion_accept", affects_plan=True)
def suggestion_accept(ctx: Ctx, inp: SuggestionInput) -> Changed:
    """Accept a suggestion (with your edits): its item is added, or the item it duplicates or changes is edited,
    or, for an event that was cancelled, dropped."""
    found = one(ctx.conn, "SELECT * FROM suggestions WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None or found["status"] != "pending":
        raise FieldError("id", f"no pending suggestion {inp.id}")
    item_id = apply(ctx, found, json.loads(found["input"]) | inp.edits)
    ctx.db.update(
        "suggestions", {"id": inp.id}, {"status": "accepted", "decided_utc": ctx.now_text, "item_id": item_id}
    )
    # What it made may be what another suggestion proposes too (the same assignment from mail and from Canvas).
    gone = set_aside_waiting(
        ctx.conn, ctx.settings, ctx.user_id, ctx.now_utc, lambda i, f: ctx.db.update("suggestions", {"id": i}, f)
    )
    return Changed(message=f"Accepted; set aside {gone} you now have" if gone else "Accepted")


@command("suggestion_restore")
def suggestion_restore(ctx: Ctx, inp: SuggestionInput) -> Changed:
    """Ask about a suggestion set aside as a duplicate after all ("Add anyway"): back in the inbox, never set aside
    again."""
    found = one(ctx.conn, "SELECT status FROM suggestions WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None or found["status"] != "superseded":
        raise FieldError("id", f"no suggestion {inp.id} set aside")
    ctx.db.update("suggestions", {"id": inp.id}, {"status": "pending", "duplicate_of": None})
    kept = [*(kv_get(ctx.conn, RESTORED, [], ctx.user_id) or []), inp.id]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": RESTORED}, {"value": json.dumps(kept)})
    return Changed(message="Back in your inbox")


EVENT_MIN = 60  # an event read with a start and no end lasts this long until you say otherwise


def with_end(fields: dict[str, Any], presets: dict[str, Any]) -> dict[str, Any]:
    """An event read with a start and no end ("the social starts at 10pm") ends an hour later: without an end it
    couldn't be added, and accepting it failed (27 Oct, "Salsa Halloween Social"). You can change the end before."""
    preset = presets.get(fields.get("preset"))
    if preset is None or preset.when != "fixed" or not fields.get("start") or fields.get("end"):
        return fields
    try:
        start = datetime.fromisoformat(str(fields["start"]))
    except ValueError:
        return fields
    return fields | {"end": (start + timedelta(minutes=EVENT_MIN)).isoformat(timespec="minutes")}


def apply(ctx: Ctx, suggestion: dict[str, Any], fields: dict[str, Any]) -> int | None:
    """Run the suggested command; returns the item it made or changed."""
    before = fields.pop("before_title", None)
    # A feed's repeat changed or gone is the whole repeat, not its first time (audit, 8 Nov); Google's and the Mac's
    # say each time on its own, so a moved time there is that time.
    calendar = source_kind(ctx, suggestion)
    whole = calendar == "ics"
    if suggestion["command"] == "drop":
        item = require_item(ctx, fields["id"])
        if whole and item.series_id is not None and not load_series(ctx, item.series_id)["external_id"]:
            series_stop(ctx, SeriesRef(id=item.series_id))
            return item.id if one(ctx.conn, "SELECT 1 FROM items WHERE id = ?", [item.id]) else None
        return drop(ctx, ItemRef(id=fields["id"])).item.id
    if suggestion["command"] == "edit" or suggestion["duplicate_of"]:
        target = fields.pop("id", None) or suggestion["duplicate_of"]
        # What a reading says again; an event's place too (27 Oct), when it's an event that changed.
        kept = ("title", "due", "start", "end", "duration_min", "release") + (
            ("location",) if suggestion["command"] == "edit" else ()
        )
        keep = {k: v for k, v in fields.items() if k in kept}
        if calendar in CALENDARS and suggestion["command"] == "edit" and "start" in fields:
            # timed or all day, free or busy, as the calendar says now (audit, 8 Nov: made all day there, it stayed
            # 9–5 here; made busy there, it stayed free)
            keep["blocks_time"] = fields.get("blocks_time", True)
            keep["free"] = bool(fields.get("free", False))
        item = require_item(ctx, target)
        typed = keep.get("title") != json.loads(suggestion["input"]).get("title")  # a name you typed is yours
        if "title" in keep and not typed and not source_named_it(ctx, suggestion, item.title):
            del keep["title"]  # your name for it stays (9 Nov: "Chem 2090 Problem Set 11" became the mail's "PS11")
        if whole and item.series_id is not None and item.occurrence_date and suggestion["command"] == "edit":
            keep["from_date"] = item.occurrence_date
        return edit(ctx, EditInput(id=target, **keep)).item.id
    if before:
        exam = find_item(ctx, before)
        fields["before"] = [exam] if exam else []
    if not fields.get("area"):  # "CS 2110 A5" goes under the CS 2110 tag, once there is one
        tags = list(area_names(ctx.conn, ctx.user_id).values())
        found = course_tag(str(fields.get("title", "")), tags)
        fields["area"] = found if found in tags else None
    repeating = (suggestion["batch"] or "").startswith("repeat:")
    if repeating:
        fields |= imported_fields(ctx, suggestion["batch"], fields)
    fields = with_end(fields, ctx.settings["presets"])  # one suggested before events read without an end got one
    if calendar in CALENDARS:  # a feed's or a calendar's own: it stays theirs, never copied to another
        fields["calendar"] = ""  # (audit, 8 Nov: a Canvas repeat's times were copied into Google every night)
    made = add(ctx, AddInput(**{k: v for k, v in fields.items() if k in AddInput.model_fields}))
    if made.item and repeating:
        attach_to_series(ctx, made.item.id, suggestion["batch"])
    if made.item is None and made.series_id is not None:  # a repeat: tied to its first time, so a later reading finds
        first = one(  # what it made (audit: a moved or removed repeat in the feed was made again beside it)
            ctx.conn, "SELECT id FROM items WHERE series_id = ? ORDER BY start_utc, id LIMIT 1", [made.series_id]
        )
        return first["id"] if first else None
    return made.item.id if made.item else None


CALENDARS = ("ics", "gcal", "mac")


def source_named_it(ctx: Ctx, suggestion: dict[str, Any], title: str) -> bool:
    """The item still has the name its source gave it, so a new reading may rename it: an event a calendar renamed is
    renamed here. One you named, or renamed since, keeps your name: a match to something you already have (an email's
    "PS11" for your "Chem 2090 Problem Set 11") never renames it."""
    if suggestion["duplicate_of"] and suggestion["command"] != "edit":
        return False
    earlier = one(
        ctx.conn,
        "SELECT input FROM suggestions WHERE raw_input_id = ? AND id != ? AND status = 'accepted' ORDER BY id DESC",
        [suggestion["raw_input_id"], suggestion["id"]],
    )
    return earlier is not None and json.loads(earlier["input"]).get("title") == title


def source_kind(ctx: Ctx, suggestion: dict[str, Any]) -> str | None:
    found = one(
        ctx.conn,
        "SELECT src.kind FROM raw_inputs r JOIN sources src ON src.id = r.source_id WHERE r.id = ?",
        [suggestion["raw_input_id"]],
    )
    return found["kind"] if found else None


@command("suggestion_reject")
def suggestion_reject(ctx: Ctx, inp: SuggestionInput) -> Changed:
    """Turn a suggestion down."""
    found = one(ctx.conn, "SELECT status FROM suggestions WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None or found["status"] != "pending":
        raise FieldError("id", f"no pending suggestion {inp.id}")
    ctx.db.update("suggestions", {"id": inp.id}, {"status": "rejected", "decided_utc": ctx.now_text})
    return Changed(message="Rejected")


@command("batch_accept", affects_plan=True)
def batch_accept(ctx: Ctx, inp: BatchInput) -> Changed:
    """Accept every pending suggestion of a batch (a syllabus, or a repeating event's instances): events first, so
    prep can come before them."""
    found = pending_batch(ctx, inp.batch)
    found.sort(key=lambda s: (json.loads(s["input"]) | inp.edits).get("preset") not in FIXED_FIRST)
    for s in found:
        item_id = apply(ctx, s, json.loads(s["input"]) | inp.edits)
        ctx.db.update(
            "suggestions", {"id": s["id"]}, {"status": "accepted", "decided_utc": ctx.now_text, "item_id": item_id}
        )
    return Changed(message=f"Accepted {len(found)}")


def pending_batch(ctx: Ctx, batch: str) -> list[dict[str, Any]]:
    found = rows(
        ctx.conn,
        "SELECT * FROM suggestions WHERE user_id = ? AND batch = ? AND status = 'pending' ORDER BY id",
        [ctx.user_id, batch],
    )
    if not found:
        raise FieldError("batch", "nothing pending in that batch")
    return found


@command("ask_ai", logged=False)
def ask_ai(ctx: Ctx, inp: AskInput) -> dict[str, Any]:
    """Read a quick-add line the grammar can't, with the LLM (§22.7): the fields it would add, for you to confirm."""
    client = llm.client(ctx.settings["llm"])
    if client is None:
        raise FieldError("text", llm.missing(ctx.settings["llm"]))
    spend_check(ctx)
    fields, used = extract.quick_add(
        client,
        ctx.settings["llm"].model,
        inp.text,
        ctx.today,
        ctx.tz,
        list(area_names(ctx.conn, ctx.user_id).values()),
        list(ctx.settings["presets"]),
        ctx.settings["notes"],
    )
    record_spend(ctx.conn, ctx.user_id, ctx.today.isoformat(), used)
    return fields


def spend(conn: Any, user_id: int, day: str) -> dict[str, int]:
    return (kv_get(conn, "llm_usage", {}, user_id) or {}).get(day, {"calls": 0, "tokens": 0})


def spend_check(ctx: Ctx) -> None:
    used, budget = spend(ctx.conn, ctx.user_id, ctx.today.isoformat()), ctx.settings["llm"]
    if used["calls"] >= budget.daily_calls or used["tokens"] >= budget.daily_tokens:
        raise FieldError("text", "today's AI budget is spent (llm.daily_calls, llm.daily_tokens)")


def record_spend(conn: Any, user_id: int, day: str, tokens: int) -> None:
    usage = kv_get(conn, "llm_usage", {}, user_id) or {}
    today = usage.get(day, {"calls": 0, "tokens": 0})
    usage = {day: {"calls": today["calls"] + 1, "tokens": today["tokens"] + tokens}}  # only today is kept
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, 'llm_usage', ?) ON CONFLICT (user_id, key) "
        "DO UPDATE SET value = excluded.value",
        [user_id, json.dumps(usage)],
    )


def source_text(s: dict[str, Any]) -> str | None:
    if s["content"] is None or s["kind"] in ("ics", "gcal") or not str(s["media_type"]).startswith("text/"):
        return None  # a calendar event's text is its raw lines; the quotes say enough
    return s["content"][:20_000]


def repeat_words(every: str | None) -> str | None:
    if not every:
        return None
    return describe(every.removeprefix("rrule:")) if every.startswith("rrule:") else f"every {every}"


SET_ASIDE_DAYS = 14


def set_aside_of(ctx: Ctx) -> list[SetAsideOut]:
    """The last two weeks' suggestions set aside as what you have, newest first, each with why."""
    twins = kv_get(ctx.conn, "set_aside_twins", {}, ctx.user_id) or {}
    since = format_utc(ctx.now_utc - SET_ASIDE_DAYS * 1440)
    found = rows(
        ctx.conn,
        "SELECT s.id, s.input, s.created_utc, s.duplicate_of, i.title AS of_title, i.status AS of_status "
        "FROM suggestions s LEFT JOIN items i ON i.id = s.duplicate_of WHERE s.user_id = ? AND s.status = 'superseded' "
        "AND s.created_utc >= ? AND s.command = 'add' ORDER BY s.id DESC LIMIT 60",
        [ctx.user_id, since],
    )
    out = []
    for r in found:
        if r["duplicate_of"] is None and str(r["id"]) not in twins:
            continue  # set aside by a newer reading of the same mail or feed, not as a duplicate
        why = (
            "Also waiting in your inbox"
            if r["duplicate_of"] is None
            else f"You have {r['of_title']}"
            if r["of_status"] == "todo"
            else f"Done: {r['of_title']}"
            if r["of_status"] == "done"
            else f"You deleted {r['of_title']}"
        )
        title = json.loads(r["input"] or "{}").get("title") or ""
        out.append(SetAsideOut(id=r["id"], title=title, why=why, created=ctx.local(r["created_utc"]) or ""))
    return out


@query("inbox")
def inbox(ctx: Ctx, inp: Empty) -> InboxOut:
    """Pending suggestions, the newest reads first and each read's in date order, with where each came from; the
    sources and today's AI spend."""
    found = rows(
        ctx.conn,
        "SELECT s.*, r.title AS origin, r.content, r.media_type, src.name AS source, src.kind FROM suggestions s "
        "LEFT JOIN raw_inputs r ON r.id = s.raw_input_id LEFT JOIN sources src ON src.id = r.source_id "
        "WHERE s.user_id = ? AND s.status = 'pending' AND (s.batch IS NULL OR s.batch NOT LIKE 'repeat:%') "
        "ORDER BY substr(s.created_utc, 1, 16) DESC, "
        "coalesce(json_extract(s.input, '$.due'), json_extract(s.input, '$.start'), '9999'), s.id",
        [ctx.user_id],
    )
    repeats = one(  # waiting to be imported in Settings → Repeating, not here
        ctx.conn,
        "SELECT COUNT(DISTINCT batch) AS n FROM suggestions WHERE user_id = ? AND status = 'pending' "
        "AND batch LIKE 'repeat:%'",
        [ctx.user_id],
    )
    set_aside = set_aside_of(ctx)
    suggestions = [
        SuggestionOut(
            id=s["id"],
            source=s["source"] or "",
            origin=s["origin"] or "",
            command=s["command"],
            input=json.loads(s["input"]),
            quotes=json.loads(s["quotes"]),
            confidence=s["confidence"],
            duplicate_of=s["duplicate_of"],
            batch=s["batch"],
            created=ctx.local(s["created_utc"]) or "",
            repeat=repeat_words(json.loads(s["input"]).get("every")),
            source_kind=s["kind"] or "",
            source_text=source_text(s),
            guess_min=guessed_minutes(ctx, json.loads(s["input"])) if s["command"] == "add" else None,
        )
        for s in found
    ]
    sources = [
        SourceOut(
            id=r["id"],
            kind=r["kind"],
            name=r["name"],
            trusted=bool(r["trusted"]),
            enabled=bool(r["enabled"]),
            last_sync=ctx.local(r["last_sync_utc"]),
            last_error=r["last_error"],
            service=json.loads(r["config"] or "{}").get("service"),
        )
        for r in rows(ctx.conn, "SELECT * FROM sources WHERE user_id = ? ORDER BY id", [ctx.user_id])
    ]
    budget = ctx.settings["llm"]
    used = spend(ctx.conn, ctx.user_id, ctx.today.isoformat())
    llm_state = {
        **llm.describe(budget),  # which AI, whether it can be asked ("ready"), whether a key is saved ("key")
        "calls": used["calls"],
        "daily_calls": budget.daily_calls,
        "tokens": used["tokens"],
        "daily_tokens": budget.daily_tokens,
        "model": budget.model,
    }
    return InboxOut(
        set_aside=set_aside,
        suggestions=suggestions,
        sources=sources,
        llm=llm_state,
        repeats=repeats["n"] if repeats else 0,
    )
