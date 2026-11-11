"""Apps on this Mac through Friday's Mac app (C100 Apple Reminders, C108 Things; integrations/reminders.py): what it
reads goes in through the shared sync, what you mark done here goes back through it. Nothing of yours to undo in any
of these: they're the Mac app's readings and reports, as `mac_sync` is."""

import json

from friday.api.commands import (
    Changed,
    MacAppInput,
    ReminderJob,
    RemindersSyncInput,
    ReminderWritesOut,
    ReminderWrittenInput,
)
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.integrations import sync
from friday.planner.store import kv_set

DENIED = "macOS didn't let Friday read your reminders: System Settings → Privacy & Security → Reminders → Friday"
SAID = {  # macOS saying no, and the app not being there, by kind
    "reminders": (DENIED, "Reminders isn't on this Mac"),
    "things": (
        "macOS didn't let Friday use Things: System Settings → Privacy & Security → Automation → Friday → Things 3",
        "Things isn't on this Mac: install Things 3, then open it once",
    ),
}
MAC_KINDS = tuple(SAID)


def connected(ctx: Ctx, kind: str = "reminders") -> dict | None:
    return one(ctx.conn, "SELECT * FROM sources WHERE user_id = ? AND kind = ? AND enabled = 1 "
               "ORDER BY id DESC LIMIT 1", [ctx.user_id, kind])  # fmt: skip


@command("reminders_sync", logged=False)
def reminders_sync(ctx: Ctx, inp: RemindersSyncInput) -> Changed:
    """Your open to-dos as the Mac app reads them (Reminders, Things); read into Friday within the minute."""
    connector = sync.CONNECTORS[inp.kind]
    source = connected(ctx, inp.kind)
    if source is None:
        raise FieldError("reminders", f"{connector.name} isn't connected (Settings → Integrations)")
    if inp.denied or inp.missing:
        ctx.db.update("sources", {"id": source["id"]}, {"last_error": SAID[inp.kind][0 if inp.denied else 1]})
        return Changed(message=f"Waiting for {connector.name}")
    sent = {"at": ctx.now_text, "lists": inp.lists, "reminders": [r.model_dump() for r in inp.reminders]}
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": connector.kv}, {"value": json.dumps(sent)})
    kv_set(ctx.conn, "integrations_now", True, ctx.user_id)
    n = len(inp.reminders)
    return Changed(message=f"Read {n} to-do{'' if n == 1 else 's'} from {connector.name}")


@query("reminder_writes")
def reminder_writes(ctx: Ctx, inp: MacAppInput) -> ReminderWritesOut:
    """Whether the Mac app should read that app, and what you marked done or opened again here, to make there."""
    source = connected(ctx, inp.kind)
    if source is None:
        return ReminderWritesOut(wanted=False)
    waiting = rows(
        ctx.conn,
        "SELECT id, external_id, op FROM source_writes WHERE source_id = ? AND done_utc IS NULL AND tries < ? "
        "ORDER BY id",
        [source["id"], sync.MAX_TRIES],
    )
    return ReminderWritesOut(wanted=True, jobs=[ReminderJob(**w) for w in waiting])


@command("reminder_written", logged=False)
def reminder_written(ctx: Ctx, inp: ReminderWrittenInput) -> Changed:
    """The Mac app's report on one: made in that app, or why not (kept to try again, then said on the box)."""
    found = one(
        ctx.conn,
        "SELECT w.*, s.name, s.kind FROM source_writes w JOIN sources s ON s.id = w.source_id "
        f"WHERE w.id = ? AND w.user_id = ? AND s.kind IN ({', '.join('?' * len(MAC_KINDS))})",
        [inp.id, ctx.user_id, *MAC_KINDS],
    )
    if found is None:
        raise FieldError("id", "no such change waits for an app on this Mac")
    name = sync.CONNECTORS[found["kind"]].name
    if inp.ok:
        ctx.db.update("source_writes", {"id": inp.id}, {"done_utc": ctx.now_text, "error": None})
        return Changed(message=f"Made in {name}")
    ctx.db.update("source_writes", {"id": inp.id}, {"tries": found["tries"] + 1, "error": inp.error})
    if found["tries"] + 1 >= sync.MAX_TRIES:
        said = f"Couldn't change a to-do in {name}: {inp.error or 'it said no'}"
        ctx.db.update("sources", {"id": found["source_id"]}, {"last_error": said})
    return Changed(message="Kept to try again")
