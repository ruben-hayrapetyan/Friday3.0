"""Work that's pointless once late, archived when its due passes (20 Nov, a user's notes: "overdue tasks from that
exam have not been cleared although the deadline was hard (hourglass icon → no point doing it after the exam is over,
right?) unless specified otherwise it should be archived"; you: "ive experienced it too where pointless tasks (a)
linger after their due date and also (b) that subtasks of exams/projects don't clear"; your answer: "Archive it, say
so", H232).

Once its due has passed, work Friday never plans after its due (an exam's prep, anything you marked Pointless after
its due: planner/build.expires) is dropped, as you would drop it, and the Inbox says so for two weeks: "Bring back"
opens it again as still worth doing (so it isn't archived again), "OK" lets the note go."""

import json
import sqlite3

from friday.api.commands import Changed, ItemRef
from friday.api.views import ArchivedOut
from friday.commands.registry import Ctx, command, run
from friday.core.db import rows
from friday.core.items import Item
from friday.core.rows import item_from_row
from friday.core.time import format_utc, parse_utc
from friday.planner.build import expires
from friday.planner.store import kv_get, kv_set, load_settings

ARCHIVED = "pointless_archived"  # kv: item id -> {"title", "why", "at"}
KEEP_DAYS = 14  # how long the Inbox says it


def archive_pointless(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> int:
    """Drops what's pointless and past its due; returns how many. Each dropped as you would (a timer on it stops, its
    project keeps what's left), by Friday, noted for the Inbox."""
    settings = load_settings(conn, user_id)
    now = format_utc(now_utc)
    found = [
        item_from_row(r)
        for r in rows(
            conn,
            "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND when_kind != 'fixed' "
            "AND due_utc IS NOT NULL AND due_utc <= ? ORDER BY due_utc, id",
            [user_id, now],
        )
    ]
    gone = [i for i in found if expires(i, settings)]
    noted = {k: v for k, v in (kv_get(conn, ARCHIVED, {}, user_id) or {}).items() if recent(v, now_utc)}
    for item in gone:
        run(conn, "drop", {"id": item.id}, now_utc=now_utc, actor="job", user_id=user_id, provisional=False)
        noted[str(item.id)] = {"title": item.title, "why": why(item), "at": now}
    if gone or noted != (kv_get(conn, ARCHIVED, {}, user_id) or {}):
        kv_set(conn, ARCHIVED, noted, user_id)
    return len(gone)


def recent(note: dict, now_utc: int) -> bool:
    return now_utc - parse_utc(note["at"]) < KEEP_DAYS * 1440


def why(item: Item) -> str:
    """Why it went, in a few words."""
    if item.preset == "Quiz prep":
        return "Its quiz is over"
    if item.preset == "Exam prep":
        return "Its exam is over"
    return "Its due passed, and it's pointless after"


def archived(conn: sqlite3.Connection, now_utc: int, user_id: int) -> list[ArchivedOut]:
    """The Inbox's notes, newest first."""
    noted = kv_get(conn, ARCHIVED, {}, user_id) or {}
    out = [
        ArchivedOut(id=int(k), title=v["title"], why=v["why"], at=v["at"])
        for k, v in noted.items()
        if recent(v, now_utc)
    ]
    return sorted(out, key=lambda a: (a.at, a.id), reverse=True)


def forget(ctx: Ctx, item_id: int) -> None:
    noted = dict(kv_get(ctx.conn, ARCHIVED, {}, ctx.user_id) or {})
    if noted.pop(str(item_id), None) is not None:
        ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": ARCHIVED}, {"value": json.dumps(noted)})


@command("archived_ok")
def archived_ok(ctx: Ctx, inp: ItemRef) -> Changed:
    """Let the Inbox's note about work archived at its due go; the work stays archived."""
    forget(ctx, inp.id)
    return Changed(message="OK")


@command("archived_restore", affects_plan=True)
def archived_restore(ctx: Ctx, inp: ItemRef) -> Changed:
    """Bring back work archived at its due: open again, and still worth doing after its due, so it isn't archived
    again; planned as late work."""
    from friday.commands.items import reopen  # noqa: PLC0415 (items imports the registry this module adds to)

    ctx.db.update("items", {"id": inp.id}, {"expires": 0, "updated_utc": ctx.now_text})
    reopen(ctx, inp)
    forget(ctx, inp.id)
    title = ctx.conn.execute("SELECT title FROM items WHERE id = ?", [inp.id]).fetchone()[0]
    return Changed(message=f"Brought back {title}, still worth doing")
