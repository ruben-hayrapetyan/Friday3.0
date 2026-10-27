"""What the inbox sets aside because you have it already (27 Oct: "please scan for duplicates before proposing things to
me. I have gotten many requests to add duplicates").

A suggestion to add something is the same as an item you have when their titles name the same thing
(`core.sameness`), they are both events or both tasks, and their dates agree: an event at the same time (within half an
hour), a task due within a day, or either without a date. Then it isn't asked: it's set aside ("superseded", with the
item), and the inbox lists what it set aside, each to add anyway. Your items count while open, and for 120 days after
you finished, deleted or skipped them: something done isn't proposed again.

The same numbered task with another date ("PS 9" due Friday, read again due Monday) is that task moved: still asked,
as a change to it (accepting moves it). Without a number ("Attendance", every week) another date is another one.

Suggestions waiting are checked again as things come in and as you accept: one you accepted makes the same thing from
another source a duplicate, and of two waiting suggestions of the same thing the later is set aside."""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from friday.core.db import rows
from friday.core.sameness import Reading, numbered, read_title, same_reading
from friday.core.time import format_utc, parse_local, parse_utc, to_utc
from friday.planner.store import kv_get

TASK_WINDOW_MIN = 24 * 60  # a task due within a day of yours is yours
EVENT_WINDOW_MIN = 30  # an event within half an hour of yours is yours
REMEMBERED_DAYS = 120  # what you finished or deleted is remembered this long


@dataclass(frozen=True)
class Same:
    item_id: int
    update: bool  # the same numbered task with another date: asked as moving it; else it's what you have
    title: str
    open: bool  # still to do (else done, deleted or skipped)


@dataclass(frozen=True)
class Candidate:
    id: int
    title: str
    event: bool
    at: int | None
    open: bool
    reading: Reading


def candidates(conn: sqlite3.Connection, settings: dict, user_id: int, now_utc: int) -> list[Candidate]:
    """Your items a suggestion may repeat: open ones, and those finished, deleted or skipped lately."""
    rules = settings["text"].rules()
    since = format_utc(now_utc - REMEMBERED_DAYS * 1440)
    found = rows(
        conn,
        "SELECT id, title, when_kind, status, due_utc, start_utc FROM items WHERE user_id = ? AND parent_id IS NULL "
        "AND (status = 'todo' OR updated_utc >= ?)",
        [user_id, since],
    )
    return [
        Candidate(
            r["id"],
            r["title"],
            r["when_kind"] == "fixed",
            parse_utc(at) if (at := r["start_utc"] if r["when_kind"] == "fixed" else r["due_utc"]) else None,
            r["status"] == "todo",
            read_title(r["title"], rules),
        )
        for r in found
    ]


def is_event(fields: dict[str, Any], settings: dict) -> bool:
    preset = settings["presets"].get(fields.get("preset"))
    return bool(fields.get("start")) or fields.get("when") == "fixed" or (preset is not None and preset.when == "fixed")


def moment(fields: dict[str, Any], event: bool, tz: str) -> int | None:
    when = fields.get("start") if event else fields.get("due")
    try:
        return to_utc(parse_local(str(when)), tz) if when else None
    except ValueError:
        return None


def duplicate_of(
    fields: dict[str, Any], settings: dict, found: list[Candidate], exclude: int | None = None
) -> Same | None:
    """The item a suggestion to add repeats, and whether it's that item moved; None when it's something new. An open
    item before one you finished, and what you have before a move."""
    title = fields.get("title")
    if not title:
        return None
    event = is_event(fields, settings)
    mine = read_title(str(title), settings["text"].rules())
    at = moment(fields, event, settings["time"].timezone)
    window = EVENT_WINDOW_MIN if event else TASK_WINDOW_MIN
    best: Same | None = None
    for c in found:
        if c.id == exclude or c.event != event or not same_reading(mine, c.reading):
            continue
        # Within the window, but a full day apart is the next day's (a routine's Lunch, every day at 2pm).
        if at is None or (c.at is not None and abs(c.at - at) <= window and abs(c.at - at) < 24 * 60):
            same = Same(c.id, False, c.title, c.open)
        elif c.at is None or (numbered(mine) and not event):
            same = Same(c.id, c.open, c.title, c.open)  # a date for it, or it moved: what you finished stays done
        else:
            continue  # the same name another time: another one
        rank = (same.open, not same.update)
        if best is None or rank > (best.open, not best.update):
            best = same
    return best


Write = Callable[[int, dict[str, Any]], None]


def set_aside_waiting(conn: sqlite3.Connection, settings: dict, user_id: int, now_utc: int, write: Write) -> int:
    """Check the suggestions waiting to add something again, as what you have changed: each that's now what you have
    is set aside, one that moves it says so, and of two waiting for the same thing the later goes. How many went."""
    kept = set(kv_get(conn, "not_duplicates", [], user_id) or [])
    found = candidates(conn, settings, user_id, now_utc)
    waiting = rows(
        conn,
        "SELECT id, input, duplicate_of FROM suggestions WHERE user_id = ? AND status = 'pending' AND command = 'add' "
        "AND (batch IS NULL OR batch NOT LIKE 'repeat:%') ORDER BY id",
        [user_id],
    )
    rules, tz = settings["text"].rules(), settings["time"].timezone
    twins = dict(kv_get(conn, "set_aside_twins", {}, user_id) or {})
    seen: list[tuple[int, Candidate]] = []
    gone = 0
    for s in waiting:
        if s["id"] in kept:
            continue
        fields = json.loads(s["input"] or "{}")
        same = duplicate_of(fields, settings, found)
        if same is not None and not same.update:
            write(s["id"], {"status": "superseded", "duplicate_of": same.item_id})
            gone += 1
            continue
        if same is not None and s["duplicate_of"] != same.item_id:
            write(s["id"], {"duplicate_of": same.item_id})
        if not fields.get("title"):
            continue
        event = is_event(fields, settings)
        mine = Candidate(s["id"], str(fields["title"]), event, moment(fields, event, tz), True,
                         read_title(str(fields["title"]), rules))  # fmt: skip
        earlier = duplicate_of(fields, settings, [c for _, c in seen])
        if earlier is not None and not earlier.update:
            write(s["id"], {"status": "superseded"})
            twins[str(s["id"])] = earlier.item_id  # a suggestion's id here: the one still waiting
            gone += 1
            continue
        seen.append((s["id"], mine))
    if twins != (kv_get(conn, "set_aside_twins", {}, user_id) or {}):
        conn.execute(
            "INSERT INTO kv (user_id, key, value) VALUES (?, 'set_aside_twins', ?) "
            "ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value",
            [user_id, json.dumps(twins)],
        )
    return gone
