"""Progress (DESIGN §8): progress, start, stop, log, review_submit, close_day."""

import json
import re
from datetime import date, timedelta
from typing import Any

from friday.api.commands import (
    Changed,
    DateInput,
    DoneInput,
    ItemResult,
    LogInput,
    ProgressInput,
    ReviewSubmitInput,
    ReviewTaskInput,
    SettleInput,
    StartInput,
    StopInput,
    StuckInput,
    TimerOut,
)
from friday.api.views import ReviewGap
from friday.commands.fields import insert_item, item_out, new_item, require_item
from friday.commands.items import done
from friday.commands.refit import refit
from friday.commands.registry import Ctx, command
from friday.commands.timer import running, started_text, stop_timer, timer_out, write_progress
from friday.core.db import one, rows
from friday.core.items import FieldError, Item
from friday.core.time import UNIT_MIN, format_utc, local_midnight, parse_local, parse_utc, planning_date, to_utc
from friday.learn.order import KEPT
from friday.planner.prepare import block_key
from friday.planner.progress import minutes_by_item
from friday.planner.store import current_plan, kv_get

SHORT_START = re.compile(r"^([A-Za-z]{3})(\d{1,2}:\d{2})$")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def amount_minutes(item: Item) -> int:
    units = {"fixed": item.duration_units, "elastic": item.ideal_units, "target": item.target_units}.get(item.amount)
    if units is None:
        raise FieldError("id", f"T{item.id} has no amount to take a share of")
    return units * UNIT_MIN


@command("progress", affects_plan=True)
def progress(ctx: Ctx, inp: ProgressInput) -> ItemResult:
    """Set progress as a share of the amount ("about half done")."""
    if not 0 <= inp.share <= 1:
        raise FieldError("share", "must be between 0 and 1")
    item = require_item(ctx, inp.id)
    write_progress(ctx, inp.id, round(inp.share * amount_minutes(item)), "slider")
    return ItemResult(item=item_out(ctx, item, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)))


@command("start")  # no replan: the timer is an overlay on the plan, and a replan on every Start split it into pieces
def start(ctx: Ctx, inp: StartInput) -> TimerOut:
    """Start the timer on an item. The plan is left as it is; the session is recorded when you stop (§8 rule 2)."""
    item = require_item(ctx, inp.id)
    if item.status != "todo" or item.when == "fixed":
        raise FieldError("id", f"T{inp.id} isn't something to work on now")
    if running(ctx) is not None:
        stop_timer(ctx)
    if item.certainty == "tentative":
        ctx.db.update("items", {"id": inp.id}, {"certainty": "planned", "updated_utc": ctx.now_text})
    ctx.db.insert("timer", {"item_id": inp.id, "start_utc": started_text(ctx)})
    chose_over(ctx, item)
    return timer_out(ctx, running(ctx) or {}, f"Timing {item.title}")


def chose_over(ctx: Ctx, item: Item) -> None:
    """Starting something other than what's planned right now is a choice Friday learns from (26 Oct): which kind
    you chose over which (`learn/order.py`), and, like a block you dragged, your plan winning over its own."""
    planned = one(
        ctx.conn,
        "SELECT b.item_id, i.preset FROM blocks b JOIN plans p ON p.id = b.plan_id JOIN items i ON i.id = b.item_id "
        "WHERE p.user_id = ? AND p.status = 'current' AND b.start_utc <= ? AND b.end_utc > ? AND i.status = 'todo' "
        "AND i.when_kind != 'fixed' ORDER BY b.start_utc LIMIT 1",
        [ctx.user_id, ctx.now_text, ctx.now_text],
    )
    if planned is None or planned["item_id"] == item.id:
        return
    kept = kv_get(ctx.conn, "order_choices", [], ctx.user_id) or []
    chose = {"at": ctx.now_text, "command_id": ctx.command_id, "chose": item.id, "chose_kind": item.preset,
             "over": planned["item_id"], "over_kind": planned["preset"]}  # fmt: skip
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "order_choices"}, {"value": json.dumps([*kept, chose][-KEPT:])})


FRICTION_KEPT = 200


@command("stuck")  # no replan: the plan stands; the friction is kept, and shows in the item's history (DESIGN §18)
def stuck(ctx: Ctx, inp: StuckInput) -> Changed:
    """Say you're stuck on an item: it goes in its history, and the app offers what else fits now."""
    item = require_item(ctx, inp.id)
    if item.when == "fixed":
        raise FieldError("id", f"T{inp.id} is an event, not something you work on")
    kept = kv_get(ctx.conn, "friction", [], ctx.user_id)
    kept = [*kept, {"item_id": inp.id, "at": ctx.now_text, "note": inp.note}][-FRICTION_KEPT:]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "friction"}, {"value": json.dumps(kept)})
    return Changed(message=f"Noted that you're stuck on {item.title}")


@command("stop", affects_plan=True)
def stop(ctx: Ctx, inp: StopInput) -> TimerOut:
    """Stop the timer; with `done`, also complete the item."""
    timer = running(ctx)
    out = stop_timer(ctx)
    if inp.done and timer is not None:
        done(ctx, DoneInput(id=timer["item_id"]))
        out.message += " and marked it done"
    return out


@command("log", affects_plan=True)
def log(ctx: Ctx, inp: LogInput) -> ItemResult:
    """Record past work on an item, or something that happened (made a fixed item)."""
    start, end = parse_utc(ctx.utc(inp.start, "start")), parse_utc(ctx.utc(inp.end, "end"))
    if end <= start:
        raise FieldError("end", "must be after the start")
    if inp.id is not None:
        item = require_item(ctx, inp.id)
        write_progress(ctx, inp.id, end - start, "retro", start, end)
        return ItemResult(item=item_out(ctx, item, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)))
    if not inp.title:
        raise FieldError("title", "give an item id, or a title for something that happened")
    event = new_item(
        ctx,
        {
            "title": inp.title,
            "preset": "Event",
            "when": "fixed",
            "start_utc": format_utc(start),
            "end_utc": format_utc(end),
        },
    )
    item_id = insert_item(ctx, event)
    return ItemResult(item=item_out(ctx, require_item(ctx, item_id)))


def parse_block_key(ctx: Ctx, key: str) -> tuple[int, int]:
    """`T42@2026-10-20T14:00` or the CLI's `T42@Tue14:00` (local) → item id and start in UTC minutes."""
    item_part, _, start = key.partition("@")
    try:
        return int(item_part.lstrip("Tt")), to_utc(parse_local(start), ctx.tz)
    except ValueError:
        pass
    short = SHORT_START.match(start)
    if not item_part.lstrip("Tt").isdigit() or short is None or short[1].lower() not in WEEKDAYS:
        raise FieldError("block_key", f"{key!r} isn't a block like T42@2026-10-20T14:00 or T42@Tue14:00")
    # The nearest such weekday: the review looks back a few days, the plan ahead.
    weekday = WEEKDAYS.index(short[1].lower())
    day = next(d for d in (ctx.today + timedelta(days=n) for n in range(-3, 4)) if d.weekday() == weekday)
    hour, minute = map(int, short[2].split(":"))
    return int(item_part.lstrip("Tt")), to_utc(local_midnight(day) + timedelta(hours=hour, minutes=minute), ctx.tz)


def day_bounds(ctx: Ctx, day: date) -> tuple[int, int]:
    begins = local_midnight(day) + timedelta(minutes=ctx.day_start)
    return to_utc(begins, ctx.tz), to_utc(begins + timedelta(days=1), ctx.tz)


def day_blocks(ctx: Ctx, day: date) -> list[dict[str, Any]]:
    """The current plan's blocks of that planning day that have started, except those a timer session of the same
    item overlaps: the session replaces the block (§8 rule 1), so the review shows it as recorded instead."""
    plan = current_plan(ctx.conn, ctx.user_id)
    if plan is None:
        return []
    lo, hi = day_bounds(ctx, day)
    found = rows(
        ctx.conn,
        "SELECT * FROM blocks WHERE plan_id = ? AND start_utc >= ? AND start_utc < ? "
        "AND start_utc < ? ORDER BY start_utc",
        [plan["id"], format_utc(lo), format_utc(hi), ctx.now_text],
    )
    sessions = [
        (r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]))
        for r in rows(
            ctx.conn,
            "SELECT * FROM progress WHERE user_id = ? AND source = 'timer' AND start_utc < ? AND end_utc > ?",
            [ctx.user_id, format_utc(hi), format_utc(lo)],
        )
    ]
    blocks = [r | {"start": parse_utc(r["start_utc"]), "end": min(parse_utc(r["end_utc"]), ctx.now_utc)} for r in found]
    return [b for b in blocks if not any(i == b["item_id"] and s < b["end"] and e > b["start"] for i, s, e in sessions)]


@command("review_submit", affects_plan=True)
def review_submit(ctx: Ctx, inp: ReviewSubmitInput) -> Changed:
    """Settle a day: each block done, partial or not done, plus anything that happened (§8 rule 4)."""
    day = date.fromisoformat(inp.date) if inp.date else ctx.today
    lo, hi = day_bounds(ctx, day)
    for row in rows(
        ctx.conn,
        "SELECT id FROM progress WHERE user_id = ? AND source = 'assumed' AND start_utc >= ? AND start_utc < ?",
        [ctx.user_id, format_utc(lo), format_utc(hi)],
    ):
        ctx.db.delete("progress", {"id": row["id"]})
    settled = {(b["item_id"], b["start"]) for b in day_blocks(ctx, day) if reviewed_minutes(ctx, b) is not None}
    for entry in inp.entries:
        if entry.block_key is not None:
            block = find_day_block(ctx, day, entry.block_key)
            write_review(ctx, block, entry.status, entry.share)
            settled.add((block["item_id"], block["start"]))
        elif entry.item_id is not None and entry.start and entry.end:
            s, e = parse_utc(ctx.utc(entry.start, "start")), parse_utc(ctx.utc(entry.end, "end"))
            write_progress(ctx, entry.item_id, e - s, "review", s, e)
    if ctx.settings["planner"].assume_unreviewed == "done":
        for block in day_blocks(ctx, day):
            if (block["item_id"], block["start"]) not in settled:
                write_review(ctx, block, "done", 1.0)
    ctx.db.upsert("reviews", {"user_id": ctx.user_id, "date": day.isoformat()}, {"submitted_utc": ctx.now_text})
    refit(ctx)  # the review is where comparisons are answered (§21.2)
    return Changed(message=f"Reviewed {day:%a %b} {day.day}")


def ended_blocks(ctx: Ctx, day: date, item_id: int | None = None) -> list[dict[str, Any]]:
    """`day_blocks` that are over (one under way isn't asked about yet), of one item when given."""
    return [
        b
        for b in day_blocks(ctx, day)
        if parse_utc(b["end_utc"]) <= ctx.now_utc and (item_id is None or b["item_id"] == item_id)
    ]


def day_gaps(ctx: Ctx, day: date) -> list[ReviewGap]:
    """The day's time Friday can't account for, by task, in the order it was planned (27 Oct: "only the gaps, by
    task"): ended blocks with no timer, no answer and the task still open, and what you said of those answered.
    Routines (lunch, dinner) are the meal taps' to record, not the Review's."""
    found = ended_blocks(ctx, day)
    if not found:
        return []
    ids = sorted({b["item_id"] for b in found})
    items = {r["id"]: r for r in rows(ctx.conn, f"SELECT * FROM items WHERE id IN ({', '.join('?' * len(ids))})", ids)}
    plan = current_plan(ctx.conn, ctx.user_id)
    ahead = (
        {
            r["item_id"]
            for r in rows(
                ctx.conn,
                "SELECT DISTINCT item_id FROM blocks WHERE plan_id = ? AND start_utc >= ?",
                [plan["id"], ctx.now_text],
            )
        }
        if plan
        else set()
    )
    by_item: dict[int, list[dict[str, Any]]] = {}
    for b in found:
        by_item.setdefault(b["item_id"], []).append(b)
    out = []
    for item_id, blocks in by_item.items():
        item = items.get(item_id)
        if item is None or item["preset"] == "Routine":
            continue
        said = [reviewed_minutes(ctx, b) for b in blocks]
        open_ = [b for b, m in zip(blocks, said, strict=True) if m is None]
        if open_ and item["status"] != "todo":
            continue  # checked off: done is what happened
        shown = open_ or blocks
        planned = sum(b["end"] - b["start"] for b in shown)
        answer = None
        if not open_:
            told = sum(m or 0 for m in said)
            answer = "not_done" if told == 0 else "done" if told >= planned else "partial"
        out.append(
            ReviewGap(
                item_id=item_id,
                title=item["title"],
                planned_min=planned,
                spans=[[ctx.local(format_utc(b["start"])) or "", ctx.local(format_utc(b["end"])) or ""] for b in shown],
                blocks=[block_key(item_id, b["start"]) for b in shown],
                due=ctx.local(item["due_utc"]),
                last=item_id not in ahead,
                answer=answer,
                done_min=None if answer is None else sum(m or 0 for m in said),
                finished=item["status"] == "done",
            )
        )
    return out


@command("review_task", affects_plan=True)
def review_task(ctx: Ctx, inp: ReviewTaskInput) -> Changed:
    """Answer the Review for one task's time that day: all done, some (`minutes`), none, or the whole task finished."""
    day = date.fromisoformat(inp.date) if inp.date else ctx.today
    blocks = ended_blocks(ctx, day, inp.item_id)
    if not blocks:
        raise FieldError("item_id", f"T{inp.item_id} has no time on {day} to answer for")
    planned = sum(b["end"] - b["start"] for b in blocks)
    status, share = ("done" if inp.status == "finished" else inp.status), 1.0
    if inp.status == "partial":
        if inp.minutes is None:
            raise FieldError("minutes", "say how much you did")
        share = min(1.0, max(0.0, inp.minutes / planned))
    for block in blocks:
        write_review(ctx, block, status, share)
    item = require_item(ctx, inp.item_id)
    if inp.status == "finished" and item.status != "done":
        done(ctx, DoneInput(id=inp.item_id))
    if all(g.answer is not None for g in day_gaps(ctx, day)):
        ctx.db.upsert("reviews", {"user_id": ctx.user_id, "date": day.isoformat()}, {"submitted_utc": ctx.now_text})
        refit(ctx)  # the review is where comparisons are answered (§21.2)
    said = {
        "done": "all done",
        "partial": f"{round(share * planned)} min done",
        "not_done": "Friday plans it again",
        "finished": "finished",
    }[inp.status]
    return Changed(message=f"{item.title}: {said}")


def find_day_block(ctx: Ctx, day: date, key: str) -> dict[str, Any]:
    item_id, start = parse_block_key(ctx, key)
    block = next((b for b in day_blocks(ctx, day) if b["item_id"] == item_id and b["start"] == start), None)
    if block is None:
        raise FieldError("block_key", f"no block {key} on {day}")
    return block


def reviewed_minutes(ctx: Ctx, block: dict[str, Any]) -> int | None:
    """What a review (or `settle`) recorded for this block, or None when it isn't settled yet."""
    found = rows(
        ctx.conn,
        "SELECT minutes FROM progress WHERE user_id = ? AND source = 'review' AND block_key = ?",
        [ctx.user_id, block_key(block["item_id"], block["start"])],
    )
    return found[-1]["minutes"] if found else None


def write_review(ctx: Ctx, block: dict[str, Any], status: str, share: float) -> None:
    """Settle one block: its share of the block's minutes, replacing what an earlier answer recorded for it."""
    if not 0 <= share <= 1:
        raise FieldError("share", "must be between 0 and 1")
    key = block_key(block["item_id"], block["start"])
    for row in rows(ctx.conn, "SELECT id FROM progress WHERE source = 'review' AND block_key = ?", [key]):
        ctx.db.delete("progress", {"id": row["id"]})
    minutes = round({"done": 1.0, "partial": share, "not_done": 0.0}[status] * (block["end"] - block["start"]))
    write_progress(ctx, block["item_id"], minutes, "review", block["start"], block["end"], key)


@command("settle", affects_plan=True)
def settle(ctx: Ctx, inp: SettleInput) -> Changed:
    """Settle one of the past blocks the plan still holds (today's, or a missed one from the day before) before the
    review ("did you finish it?"); the review keeps the answer."""
    item_id, start = parse_block_key(ctx, inp.block_key)
    day = planning_date(start, ctx.tz, ctx.day_start)
    if day > ctx.today:
        raise FieldError("block_key", "that block hasn't happened yet")
    block = find_day_block(ctx, day, inp.block_key)
    write_review(ctx, block, inp.status, inp.share)
    if inp.until:  # the calendar joins a block's pieces (each replan cuts one): the rest of the span goes with it
        until = parse_utc(ctx.utc(inp.until, "until"))
        for piece in day_blocks(ctx, day):
            if piece["item_id"] == item_id and start < piece["start"] < until:
                write_review(ctx, piece, inp.status, inp.share)
    return Changed(
        message={"done": "Marked done", "partial": "Marked partly done", "not_done": "Marked not done"}[inp.status]
    )


def skip_missed_routines(ctx: Ctx, before: int) -> None:
    """A lunch whose window has passed is skipped, not owed: it stayed in To-do for weeks, "not planned"."""
    for r in rows(
        ctx.conn,
        "SELECT id FROM items WHERE user_id = ? AND status = 'todo' AND preset = 'Routine' AND series_id IS NOT NULL "
        "AND due_utc <= ?",
        [ctx.user_id, format_utc(before)],
    ):
        ctx.db.update("items", {"id": r["id"]}, {"status": "skipped", "updated_utc": ctx.now_text})


@command("close_day", affects_plan=True)
def close_day(ctx: Ctx, inp: DateInput) -> Changed:
    """Write `assumed` progress for a past day's unreviewed blocks (§8; the nightly job runs this for yesterday)."""
    day = date.fromisoformat(inp.date) if inp.date else ctx.today - timedelta(days=1)
    if day >= ctx.today:
        raise FieldError("date", "only a day that has ended can be closed")
    skip_missed_routines(ctx, day_bounds(ctx, ctx.today)[0])
    reviewed = rows(ctx.conn, "SELECT 1 FROM reviews WHERE user_id = ? AND date = ?", [ctx.user_id, day.isoformat()])
    if reviewed or ctx.settings["planner"].assume_unreviewed != "done":
        return Changed(message=f"Nothing to assume for {day}")
    lo, hi = day_bounds(ctx, day)
    recorded = rows(
        ctx.conn,
        "SELECT * FROM progress WHERE user_id = ? AND start_utc < ? AND end_utc > ?",
        [ctx.user_id, format_utc(hi), format_utc(lo)],
    )
    written = 0
    for block in day_blocks(ctx, day):
        key = block_key(block["item_id"], block["start"])
        settled = any(r["block_key"] == key for r in recorded)
        if not settled and not block["tentative"]:
            write_progress(
                ctx, block["item_id"], block["end"] - block["start"], "assumed", block["start"], block["end"], key
            )
            written += 1
    return Changed(message=f"Assumed {written} blocks done on {day}")
