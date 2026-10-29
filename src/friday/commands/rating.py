"""Which events you could skip in a week with more due than fits (personal's, COMBINED.md 56): each upcoming event's
title rated once by the AI and kept (kv `event_ratings`), and the ones you said you go to (kv `events_going`), which
are never offered again. Triage reads both; the job loop rates new titles as they arrive."""

import json
import sqlite3
from typing import Any

from friday.api.commands import Changed, EventGoingInput, EventHoldInput, EventKeepInput
from friday.commands.fields import require_item
from friday.commands.registry import Ctx, command
from friday.core.calendars import rating_key
from friday.core.db import rows
from friday.core.items import FieldError
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
    settings = load_settings(conn, user_id)
    categories = [c.name for c in settings["categories"].categories]
    # Rated before it was asked for a category: once a day, again, so its events get their colour.
    uncolored = lambda k: retry and bool(categories) and "category" not in kept[k]  # noqa: E731
    new = sorted(
        {
            r["title"]
            for r in found
            if (k := rating_key(r["title"])) not in kept or (retry and guessed(kept[k])) or uncolored(k)
        }
    )
    if not new:
        return 0
    rated = rate(
        new, client if client is not None else llm.client(settings["llm"]), settings["llm"].small_model, categories
    )
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


@command("event_hold", affects_plan=True)
def event_hold(ctx: Ctx, inp: EventHoldInput) -> Changed:
    """An event whose time is for a task: the planner puts the task there, from the start for as long as it has
    left, and keeps other work off all of it (planner/holds.py). No task makes it an event like any other again.
    27 Oct: "A4dd" is when you write "CS A4 Design Doc"."""
    event = require_item(ctx, inp.id)
    if event.when != "fixed":
        raise FieldError("id", f"{event.title} isn't an event")
    holds = {str(k): v for k, v in (kv_get(ctx.conn, "event_holds", {}, ctx.user_id) or {}).items()}
    if inp.task_id is None:
        holds.pop(str(event.id), None)
        said = f"{event.title} is an event like any other again"
    else:
        task = require_item(ctx, inp.task_id)
        if task.when == "fixed" or task.status != "todo":
            raise FieldError("task_id", f"{task.title} isn't a task to do")
        holds[str(event.id)] = task.id
        said = f"{event.title}'s time is for {task.title}"
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "event_holds"}, {"value": json.dumps(holds)})
    # Said again (or let go), it holds as firmly as at first: no longer loosened by a lock that made work late.
    loose = [e for e in kv_get(ctx.conn, "event_holds_loose", [], ctx.user_id) or [] if e != event.id]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "event_holds_loose"}, {"value": json.dumps(loose)})
    return Changed(message=said)


@command("event_keep", affects_plan=True)
def event_keep(ctx: Ctx, inp: EventKeepInput) -> Changed:
    """Go to an optional event this time (gym on Thursday): work keeps off it as off any event. `going` false
    leaves it to Friday again, to give to work when work needs it."""
    item = require_item(ctx, inp.id)
    kept = set(kv_get(ctx.conn, "events_kept", [], ctx.user_id))
    kept = kept | {item.id} if inp.going else kept - {item.id}
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "events_kept"}, {"value": json.dumps(sorted(kept))})
    said = f"Going to {item.title}: work keeps off it" if inp.going else f"{item.title}: Friday decides"
    return Changed(message=said)
