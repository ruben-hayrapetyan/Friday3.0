"""Which events you could skip in a week with more due than fits (personal's, COMBINED.md 56): each upcoming event's
title rated once by the AI and kept (kv `event_ratings`), and the ones you said you go to (kv `events_going`), which
are never offered again. Triage reads both; the job loop rates new titles as they arrive."""

import json
import sqlite3
from typing import Any

from friday.api.commands import Changed, EventGoingInput
from friday.commands.registry import Ctx, command
from friday.core.calendars import rating_key
from friday.core.db import rows
from friday.core.time import format_utc
from friday.ingest import llm
from friday.ingest.rating import guessed, rate
from friday.planner.store import kv_get, kv_set, load_settings

AHEAD_DAYS = 14


def rate_upcoming(conn: sqlite3.Connection, now_utc: int, user_id: int = 1, client: Any | None = None) -> int:
    """Rate the titles of the next two weeks' events not rated yet, and once a day those only guessed from their words
    (no AI then, or it failed: every call did while the event list went to the command as an option); returns how
    many were asked."""
    found = rows(
        conn,
        "SELECT DISTINCT title FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status = 'todo' "
        "AND start_utc >= ? AND start_utc < ?",
        [user_id, format_utc(now_utc), format_utc(now_utc + AHEAD_DAYS * 1440)],
    )
    kept = kv_get(conn, "event_ratings", {}, user_id)
    today = format_utc(now_utc)[:10]
    retry = kv_get(conn, "event_ratings_retried", None, user_id) != today
    new = sorted(
        {r["title"] for r in found if (k := rating_key(r["title"])) not in kept or (retry and guessed(kept[k]))}
    )
    if not new:
        return 0
    settings = load_settings(conn, user_id)
    rated = rate(new, client if client is not None else llm.client(), settings["llm"].small_model)
    kv_set(conn, "event_ratings", kept | rated, user_id)
    if retry:
        kv_set(conn, "event_ratings_retried", today, user_id)
    return len(new)


@command("event_going")
def event_going(ctx: Ctx, inp: EventGoingInput) -> Changed:
    """You go to this event: Friday stops offering to skip it."""
    going = sorted(set(kv_get(ctx.conn, "events_going", [], ctx.user_id)) | {rating_key(inp.title)})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "events_going"}, {"value": json.dumps(going)})
    return Changed(message=f"Won't suggest skipping {inp.title}")
