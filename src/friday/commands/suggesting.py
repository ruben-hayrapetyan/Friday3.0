"""Suggestions from what sources bring in (DESIGN §22.1): an input is stored once and suggested again only when it
changes; a change to what an earlier one made is an edit, one that vanished a drop; a likely duplicate is marked;
a trusted source's fixed events, and a repeat you imported, go in without asking."""

import contextlib
import json
import sqlite3
from collections.abc import Callable
from typing import Any

from friday.commands.inbox import record_spend, spend
from friday.commands.registry import run
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.settings import minutes_of
from friday.core.textnorm import identity_text, norm
from friday.core.time import format_utc, parse_local, parse_utc, planning_date, to_utc
from friday.ingest import llm, sort
from friday.ingest.ics import Found, Proposed

DUPLICATE_WINDOW_MIN = 24 * 60


def take(
    conn: sqlite3.Connection,
    source: dict,
    read: Callable[[], list[Found]],
    settings: dict,
    now_utc: int,
    user_id: int,
    until: int | None,
    client: Any | None = None,
) -> int:
    """Read a source and suggest from what is new or changed (calendar events sorted by the small model when it
    can), and from what is gone (§22.1)."""
    try:
        found = read()
    except Exception as error:  # a bad feed mustn't stop the others; it shows in Settings and, repeated, a banner
        conn.execute(
            "UPDATE sources SET last_error = ?, failures = failures + 1, last_sync_utc = ? WHERE id = ?",
            [f"{type(error).__name__}: {error}"[:300], format_utc(now_utc), source["id"]],
        )
        return 0
    conn.execute(
        "UPDATE sources SET last_error = NULL, failures = 0, last_sync_utc = ? WHERE id = ?",
        [format_utc(now_utc), source["id"]],
    )
    made = 0
    fresh = [(raw_id, f) for f in found if (raw_id := store(conn, source["id"], f, now_utc, user_id)) is not None]
    sorted_by = sort_fresh(conn, source, [f for _, f in fresh], settings, now_utc, user_id, client)
    for raw_id, f in fresh:
        picked = sorted_by.get(sort_key(f))
        proposals = sized(f.as_kind(picked.kind, picked.title), picked.minutes) if picked else f.proposals
        if picked and picked.skip:
            proposals = []  # your notes say it needs nothing from you
        made += suggest(conn, settings, now_utc, user_id, raw_id, proposals, bool(source["trusted"]), source["name"])
        conn.execute("UPDATE raw_inputs SET status = 'extracted' WHERE id = ?", [raw_id])
    return made + gone(conn, source, {f.external_id for f in found}, settings, now_utc, user_id, until)


def sized(proposals: list[Proposed], minutes: int | None) -> list[Proposed]:
    """Work due by a time gets the length your notes give; exam prep and events keep theirs."""
    for p in proposals:
        if minutes and not p.fixed and p.input.get("preset") != "Exam prep":
            p.input["duration_min"] = minutes
    return proposals


SORT_BATCH = 50  # events per call: well within the small model's reply


def sort_key(f: Found) -> str:
    """A repeating event is sorted once, for all its instances."""
    return (f.event.series if f.event and f.event.series else None) or f.external_id


def sort_fresh(
    conn: sqlite3.Connection,
    source: dict,
    fresh: list[Found],
    settings: dict,
    now_utc: int,
    user_id: int,
    client: Any | None,
) -> dict[str, sort.Sorted]:
    """New events' kinds and titles from the small model, by `sort_key`; empty (so the rules stand) when the
    calendar names its own kind, there is no key, today's budget is spent, or the call fails (said on the source)."""
    events = {sort_key(f): f.event for f in fresh if f.event is not None}
    if not events or json.loads(source["config"] or "{}").get("kind"):
        return {}
    client = client or llm.client()
    budget, today = (
        settings["llm"],
        planning_date(now_utc, settings["time"].timezone, minutes_of(settings["time"].day_start)),
    )
    kinds = {name: p.when == "fixed" for name, p in settings["presets"].items()}
    out: dict[str, sort.Sorted] = {}
    items = list(events.items())
    for at in range(0, len(items), SORT_BATCH):
        used = spend(conn, user_id, today.isoformat())
        if client is None or used["calls"] >= budget.daily_calls or used["tokens"] >= budget.daily_tokens:
            break
        try:
            found, tokens = sort.sort_events(
                client, budget.small_model, items[at : at + SORT_BATCH], source["name"], kinds, today, settings["notes"]
            )
        except Exception as error:  # the rules stand; the source says why
            why = f"Sorting with {budget.small_model} failed, so the fixed rules sorted these: {error}"[:300]
            conn.execute("UPDATE sources SET last_error = ? WHERE id = ?", [why, source["id"]])
            break
        record_spend(conn, user_id, today.isoformat(), tokens)
        out |= found
    return out


def gone(
    conn: sqlite3.Connection,
    source: dict,
    seen: set[str],
    settings: dict,
    now_utc: int,
    user_id: int,
    until: int | None,
) -> int:
    """Inputs the source no longer has (cancelled, declined, deleted): their pending suggestions are withdrawn, and
    an item they made that is still ahead (before `until`, for a calendar read in a window) is suggested dropped."""
    made = 0
    for r in rows(
        conn, "SELECT id, external_id FROM raw_inputs WHERE source_id = ? AND status != 'ignored'", [source["id"]]
    ):
        if r["external_id"] in seen:
            continue
        conn.execute(
            "UPDATE suggestions SET status = 'superseded' WHERE raw_input_id = ? AND status = 'pending'", [r["id"]]
        )
        conn.execute("UPDATE raw_inputs SET status = 'ignored' WHERE id = ?", [r["id"]])
        item = made_item(conn, r["id"])
        when = item and (item["start_utc"] or item["due_utc"])
        if item and when and now_utc <= parse_utc(when) and (until is None or parse_utc(when) < until):
            drop = Proposed("drop", {"id": item["id"], "title": item["title"]}, fixed=True)
            made += suggest(conn, settings, now_utc, user_id, r["id"], [drop], bool(source["trusted"]), source["name"])
    return made


def made_item(conn: sqlite3.Connection, raw_id: int) -> dict[str, Any] | None:
    """The open item an accepted suggestion from this input made or changed."""
    found = made_items(conn, raw_id)
    return found[0] if found else None


def made_items(conn: sqlite3.Connection, raw_id: int) -> list[dict[str, Any]]:
    return rows(
        conn,
        "SELECT i.id, i.title, i.preset, i.start_utc, i.due_utc FROM suggestions s JOIN items i ON i.id = s.item_id "
        "WHERE s.raw_input_id = ? AND s.status = 'accepted' AND i.status = 'todo' ORDER BY s.id DESC",
        [raw_id],
    )


def same_kind(made: list[dict[str, Any]], fields: dict[str, Any]) -> dict[str, Any] | None:
    """What an earlier read of the input made that this proposal changes: an exam's prep never edits the exam."""
    prep = fields.get("preset") == "Exam prep"
    return next((m for m in made if (m["preset"] == "Exam prep") == prep), None)


def store(conn: sqlite3.Connection, source_id: int, f: Found, now_utc: int, user_id: int) -> int | None:
    """Keep a raw input; returns its id when it is new or changed, None when it was seen as it is."""
    seen = one(
        conn,
        "SELECT id, content_hash, status FROM raw_inputs WHERE source_id = ? AND external_id = ?",
        [source_id, f.external_id],
    )
    if seen and seen["content_hash"] == f.content_hash and seen["status"] != "ignored":
        return None
    if seen:
        conn.execute(
            "UPDATE raw_inputs SET content = ?, content_hash = ?, title = ?, received_utc = ?, status = 'new' "
            "WHERE id = ?",
            [f.text, f.content_hash, f.title, format_utc(now_utc), seen["id"]],
        )
        return int(seen["id"])
    cursor = conn.execute(
        "INSERT INTO raw_inputs (user_id, source_id, external_id, received_utc, content_hash, title, content) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [user_id, source_id, f.external_id, format_utc(now_utc), f.content_hash, f.title, f.text],
    )
    return int(cursor.lastrowid or 0)


def suggest(
    conn: sqlite3.Connection,
    settings: dict,
    now_utc: int,
    user_id: int,
    raw_id: int,
    proposals: list[Proposed],
    trusted: bool,
    source: str,
    batch: str | None = None,
) -> int:
    """Suggestions from one input: a change to what an earlier one made is an edit; a likely duplicate is marked;
    a trusted source's fixed events are accepted at once."""
    made_before = made_items(conn, raw_id)
    conn.execute("UPDATE suggestions SET status = 'superseded' WHERE raw_input_id = ? AND status = 'pending'", [raw_id])
    made = 0
    for p in proposals:
        command, fields = p.command, dict(p.input)
        earlier = same_kind(made_before, fields)
        if command == "add" and not earlier and over(fields, settings["time"].timezone, now_utc):
            continue  # an assignment due last week, read today, is nothing to do now
        if command == "add" and not earlier and not p.fixed and twin_suggested(conn, raw_id):
            continue  # the same event on another of your calendars already made this task
        if command == "add":
            fields = addable(fields, settings["presets"])
        if earlier and command == "add":
            command, fields = "edit", {"id": earlier["id"]} | fields
        group = batch or (f"repeat:{p.series}" if p.series and command == "add" else None)
        said = said_of_series(conn, group) if group and p.series else None
        # an instance of a repeating event isn't a duplicate of its neighbours, a day apart
        duplicate = duplicate_of(conn, settings, user_id, fields) if command == "add" and not p.series else None
        cursor = conn.execute(
            "INSERT INTO suggestions (user_id, raw_input_id, batch, command, input, quotes, confidence, duplicate_of, "
            "created_utc, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                user_id,
                raw_id,
                group,
                command,
                json.dumps(fields),
                json.dumps(p.quotes),
                p.confidence,
                duplicate,
                format_utc(now_utc),
                "rejected" if said == "rejected" else "pending",  # kept, so switching the repeat on finds it
            ],
        )
        made += said != "rejected"
        imported = earlier is not None and command != "add" and follows_calendar(conn, earlier["id"])
        if (trusted and p.fixed) or said == "accepted" or imported:
            accept_trusted(conn, now_utc, user_id, int(cursor.lastrowid or 0), source)
    return made


def twin_suggested(conn: sqlite3.Connection, raw_id: int) -> bool:
    """The same calendar event, read from another of your calendars (the Mac's copy of a Google one), already
    suggested this task."""
    mine = one(conn, "SELECT source_id, external_id FROM raw_inputs WHERE id = ?", [raw_id])
    if not mine or not mine["external_id"]:
        return False
    key = mine["external_id"].split(":")[-1]  # the event and its occurrence, without the calendar
    return (
        one(
            conn,
            "SELECT 1 AS yes FROM raw_inputs r JOIN suggestions s ON s.raw_input_id = r.id "
            "WHERE r.source_id != ? AND (r.external_id = ? OR r.external_id LIKE ?) AND s.command = 'add' "
            "AND s.status IN ('pending', 'accepted')",
            [mine["source_id"], key, f"%:{key}"],
        )
        is not None
    )


def addable(fields: dict[str, Any], presets: dict) -> dict[str, Any]:
    """Fields Friday can add as they are: a set-time kind without a time (a meeting still to arrange) is a to-do,
    and deadline work without a due date is soft, rather than a suggestion that fails when you accept it."""
    preset = presets.get(fields.get("preset"))
    if preset is None:
        return fields
    if preset.when == "fixed" and not fields.get("start"):
        rest = {k: v for k, v in fields.items() if k not in ("preset", "end", "blocks_time")}
        return rest | ({"preset": "Errand"} if "Errand" in presets else {})
    if preset.firmness == "hard" and not fields.get("due") and not fields.get("firmness"):
        return fields | {"firmness": "none"}
    return fields


def over(fields: dict[str, Any], tz: str, now_utc: int) -> bool:
    """Already due, or already ended."""
    last = fields.get("due") or fields.get("end") or fields.get("start")
    try:
        return bool(last) and to_utc(parse_local(last), tz) <= now_utc
    except ValueError:  # a time the AI wrote oddly; accepting it says what is wrong
        return False


def said_of_series(conn: sqlite3.Connection, group: str | None) -> str | None:
    """What you said to a repeating event: imported in Repeating (its series on: "accepted"; switched off:
    "rejected"), or turned down; it holds for the event's later instances."""
    mirror = one(
        conn, "SELECT active FROM series WHERE external_id = ?", ["gcal:" + (group or "").removeprefix("repeat:")]
    )
    if mirror:
        return "accepted" if mirror["active"] else "rejected"
    found = one(
        conn,
        "SELECT status FROM suggestions WHERE batch = ? AND status IN ('accepted', 'rejected') "
        "ORDER BY decided_utc DESC, id DESC LIMIT 1",
        [group],
    )
    return found["status"] if found else None


def follows_calendar(conn: sqlite3.Connection, item_id: int) -> bool:
    """An occurrence of a repeat you imported: the calendar keeps its times, so a move or cancellation applies."""
    return (
        one(
            conn,
            "SELECT 1 AS yes FROM items i JOIN series s ON s.id = i.series_id "
            "WHERE i.id = ? AND s.external_id IS NOT NULL",
            [item_id],
        )
        is not None
    )


def accept_trusted(conn: sqlite3.Connection, now_utc: int, user_id: int, suggestion_id: int, source: str) -> None:
    # If it can't go in (say, a clash with validation), it stays in the inbox for you to look at.
    with contextlib.suppress(FieldError):
        run(
            conn,
            "suggestion_accept",
            {"id": suggestion_id},
            now_utc=now_utc,
            actor=f"sync:{source}",
            user_id=user_id,
            provisional=False,
        )


def words_within(a: str, b: str) -> bool:
    shorter, longer = sorted((set(a.split()), set(b.split())), key=len)
    return bool(shorter) and shorter <= longer


def duplicate_of(conn: sqlite3.Connection, settings: dict, user_id: int, fields: dict) -> int | None:
    """An open item with the same identity text whose due or start is within a day of this one's (§22.1)."""
    title = fields.get("title")
    if not title:
        return None
    rules, tz = settings["text"].rules(), settings["time"].timezone
    wanted = identity_text(norm(title, rules))
    when = fields.get("due") or fields.get("start")
    moment = to_utc(parse_local(when), tz) if when else None
    for r in rows(
        conn, "SELECT id, title, due_utc, start_utc FROM items WHERE user_id = ? AND status = 'todo'", [user_id]
    ):
        theirs = r["due_utc"] or r["start_utc"]
        mine = identity_text(norm(r["title"], rules))
        # "MATH Prelim 2" at the very minute you have "Prelim 2" is that prelim
        if (
            fields.get("start")
            and r["start_utc"]
            and parse_utc(r["start_utc"]) == moment
            and words_within(mine, wanted)
        ):
            return int(r["id"])
        if mine != wanted:
            continue
        if moment is None or theirs is None or abs(parse_utc(theirs) - moment) <= DUPLICATE_WINDOW_MIN:
            return int(r["id"])
    return None
