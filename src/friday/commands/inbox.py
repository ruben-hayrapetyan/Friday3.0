"""The inbox (DESIGN §22.1): sources, suggestions and what you decide about them. Accepting runs the suggested
`add` (or `edit`) as you, so it is logged and undoable like anything else. Fetching and extracting run in the job
loop (`commands/fetching.py`), never in a request.
"""

import hashlib
import json
from typing import Any

from friday.api.commands import (
    AddInput,
    AskInput,
    BatchInput,
    Changed,
    DocumentInput,
    EditInput,
    ItemRef,
    SourceEditInput,
    SourceInput,
    SourceRemoveInput,
    SuggestionInput,
)
from friday.api.types import Empty
from friday.api.views import InboxOut, SourceOut, SuggestionOut
from friday.commands.items import add, drop, edit, find_item, guessed_minutes
from friday.commands.registry import Ctx, command, query
from friday.commands.series import attach_to_series, imported_fields
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.recurrence import describe
from friday.core.textnorm import course_tag
from friday.ingest import extract, llm
from friday.planner.store import area_names, kv_get

FIXED_FIRST = ("Class", "Exam", "Meeting", "Appointment", "Event")  # events before the prep that comes `before:` them


def source_row(ctx: Ctx, source_id: int) -> dict[str, Any]:
    found = one(ctx.conn, "SELECT * FROM sources WHERE user_id = ? AND id = ?", [ctx.user_id, source_id])
    if found is None:
        raise FieldError("id", f"no source {source_id}")
    return found


@command("source_add")
def source_add(ctx: Ctx, inp: SourceInput) -> Changed:
    """Add a calendar feed to read into the inbox."""
    ctx.db.insert(
        "sources",
        {"kind": inp.kind, "name": inp.name, "config": json.dumps({"url": inp.url}), "trusted": int(inp.trusted)},
    )
    return Changed(message=f"Added {inp.name}; it syncs within a minute")


@command("source_edit")
def source_edit(ctx: Ctx, inp: SourceEditInput) -> Changed:
    """Rename a source, change its URL, trust it, or switch it off."""
    found = source_row(ctx, inp.id)
    changes: dict[str, Any] = {}
    if inp.name is not None:
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
        for r in rows(ctx.conn, "SELECT id FROM raw_inputs WHERE source_id = ?", [inp.id]):
            for s in rows(ctx.conn, "SELECT id FROM suggestions WHERE raw_input_id = ?", [r["id"]]):
                ctx.db.delete("suggestions", {"id": s["id"]})
            ctx.db.delete("raw_inputs", {"id": r["id"]})
        ctx.db.delete("sources", {"id": inp.id})
        return Changed(message=f"Removed {found['name']} and what it brought in")
    ctx.db.update("sources", {"id": inp.id}, {"enabled": 0})
    return Changed(message=f"Stopped reading {found['name']}")


@command("sync_now")
def sync_now(ctx: Ctx, inp: Empty) -> Changed:
    """Read every source within the minute instead of at the next poll."""
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sync_now"}, {"value": json.dumps(ctx.now_text)})
    return Changed(message="Syncing within a minute")


@command("document_add")
def document_add(ctx: Ctx, inp: DocumentInput) -> Changed:
    """A document to read for tasks (a syllabus, a handout): it is read within a minute, into the inbox."""
    if len(inp.content) > 14_000_000:
        raise FieldError("content", "too big; the limit is about 10 MB")
    source = one(ctx.conn, "SELECT id FROM sources WHERE user_id = ? AND kind = 'upload'", [ctx.user_id])
    source_id = source["id"] if source else ctx.db.insert("sources", {"kind": "upload", "name": "Uploads"})
    digest = hashlib.sha256(inp.content.encode()).hexdigest()
    ctx.db.insert(
        "raw_inputs",
        {
            "source_id": source_id,
            "external_id": digest[:24],
            "received_utc": ctx.now_text,
            "content_hash": digest,
            "title": inp.name,
            "media_type": inp.media_type,
            "content": inp.content,
        },
    )
    return Changed(message=f"Reading {inp.name}; its suggestions come into the inbox within a minute")


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
    return Changed(message="Accepted")


def apply(ctx: Ctx, suggestion: dict[str, Any], fields: dict[str, Any]) -> int | None:
    """Run the suggested command; returns the item it made or changed."""
    before = fields.pop("before_title", None)
    if suggestion["command"] == "drop":
        return drop(ctx, ItemRef(id=fields["id"])).item.id
    if suggestion["command"] == "edit" or suggestion["duplicate_of"]:
        target = fields.pop("id", None) or suggestion["duplicate_of"]
        keep = {k: v for k, v in fields.items() if k in ("title", "due", "start", "end", "duration_min", "release")}
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
    made = add(ctx, AddInput(**{k: v for k, v in fields.items() if k in AddInput.model_fields}))
    if made.item and repeating:
        attach_to_series(ctx, made.item.id, suggestion["batch"])
    return made.item.id if made.item else None


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
    client = llm.client()
    if client is None:
        raise FieldError("text", "no Anthropic key: set ANTHROPIC_API_KEY or secrets.toml")
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
        )
        for r in rows(ctx.conn, "SELECT * FROM sources WHERE user_id = ? ORDER BY id", [ctx.user_id])
    ]
    budget = ctx.settings["llm"]
    used = spend(ctx.conn, ctx.user_id, ctx.today.isoformat())
    llm_state = {
        "key": llm.api_key() is not None or llm.cli_path() is not None,  # an AI to read with: a key or the command
        "calls": used["calls"],
        "daily_calls": budget.daily_calls,
        "tokens": used["tokens"],
        "daily_tokens": budget.daily_tokens,
        "model": budget.model,
    }
    return InboxOut(suggestions=suggestions, sources=sources, llm=llm_state, repeats=repeats["n"] if repeats else 0)
