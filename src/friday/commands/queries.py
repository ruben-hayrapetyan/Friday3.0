"""Queries (DESIGN §9.3): now, fits, plan, items, item, parse, review, paces, status, settings, log_list, stats."""

import json
import os
from datetime import timedelta
from typing import Any

from friday.api.commands import (
    EventsInput,
    FitsInput,
    ItemRef,
    ItemsInput,
    LogListInput,
    ParseInput,
    RangeInput,
)
from friday.api.types import BlockOut, Empty, ItemOut
from friday.api.views import (
    Alert,
    ItemDetail,
    LateItem,
    LogEntry,
    NowOut,
    PacesOut,
    ParseOutput,
    PlanOut,
    StatsOut,
    StatusOut,
    Swap,
)
from friday.commands.decisions import decisions
from friday.commands.fields import item_out, require_item, waiting_on
from friday.commands.registry import Ctx, query
from friday.commands.timer import all_running, elapsed_seconds, running
from friday.commands.timer import timer_out as timing
from friday.core.db import one, rows
from friday.core.guess import course_of, guess_preset
from friday.core.pace import dials_on, pace_label
from friday.core.presets import in_use
from friday.core.quickadd import parse
from friday.core.rows import item_from_row
from friday.core.settings import to_json
from friday.core.textnorm import identity_text, norm
from friday.core.time import UNIT_MIN, format_utc, local_midnight, parse_utc, to_local, to_utc
from friday.engine import executor
from friday.engine.explain import Block
from friday.engine.rules.prices import has_words
from friday.planner.assemble import PlannedBlock
from friday.planner.build import id_of, key_of
from friday.planner.progress import minutes_by_item, remaining_minutes
from friday.planner.service import ahead
from friday.planner.snapshot import pace_periods, take_snapshot
from friday.planner.store import area_names, current_plan, generation, kv_get, settings_version
from friday.planner.timed import OWN, background_ids, sittings_between, timed_over
from friday.planner.views import Current, fits_view, now_view


def block_out(
    ctx: Ctx, item_id: int, start: int, end: int, cost: dict | None = None, running: bool = False, **extra: Any
) -> BlockOut:
    """`running`: the calendar's block of a task that runs by itself is its whole length, its quarter hour with you
    first; everywhere else (the Now bar, what's next) it's the quarter hour."""
    begins = ctx.local(format_utc(start)) or ""
    item = require_item(ctx, item_id)
    if running and item.background and item.duration_units:
        end = max(end, start + item.duration_units * UNIT_MIN)
        extra["background"] = True
    return BlockOut(
        key=f"T{item_id}@{begins}",
        item_id=item_id,
        title=item.title,
        area=area_names(ctx.conn, ctx.user_id).get(item.area_id) if item.area_id else None,
        preset=item.preset,
        estimated=item.estimate_detail is not None,
        start=begins,
        end=ctx.local(format_utc(end)) or "",
        cost=cost or {},
        **extra,
    )


def engine_block(ctx: Ctx, state: Current, block: Block | None) -> BlockOut | None:
    if block is None:
        return None
    grid = state.problem.grid
    return block_out(ctx, id_of(block.key), int(grid.start[block.slots[0]]), int(grid.end[block.slots[-1]]))


def swap_out(ctx: Ctx, swap: executor.Swap) -> Swap:
    item_id = id_of(swap.key)
    slack = None if swap.slack_minutes == executor.NEVER else round(swap.slack_minutes / 60, 1)
    return Swap(
        item_id=item_id,
        title=require_item(ctx, item_id).title,
        minutes=swap.minutes,
        price=swap.price,
        slack_hours=slack,
    )


@query("now")
def now(ctx: Ctx, inp: Empty) -> NowOut:
    """What's on now, what's next, what else is safe to do, and deadlines needing attention."""
    snapshot = take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id)
    state, shown = now_view(snapshot)
    timer = running(ctx)
    # Real times, not the grid's: the grid starts at the next quarter hour, so a block begun at 08:00 "started" at
    # 08:15 and nothing was on at 08:03 (M16).
    planned = [b for b in snapshot.plan_blocks if key_of(b.item_id) in state.problem.items and b.end_utc > ctx.now_utc]
    covering = next((b for b in planned if b.start_utc <= ctx.now_utc), None)
    events = fixed_events(ctx)
    happening = next((e for e in events if parse_utc(e["start_utc"]) <= ctx.now_utc), None)
    current = None
    if timer is not None:
        current = timed_now(ctx, timer, planned, events)
    elif covering is not None:
        current = block_out(ctx, covering.item_id, covering.start_utc, covering.end_utc)
    elif happening is not None:
        current = event_out(ctx, happening)
    after = parse_utc(ctx.utc(current.end)) if current else ctx.now_utc
    block = min((b for b in planned if b.start_utc >= after), key=lambda b: b.start_utc, default=None)
    event = next((e for e in events if parse_utc(e["start_utc"]) >= after), None)
    coming = None  # the next thing, work or class: "free until 15:45" had walked past a 13:25 discussion
    if block is not None and (event is None or block.start_utc < parse_utc(event["start_utc"])):
        coming = (block.start_utc, block_out(ctx, block.item_id, block.start_utc, block.end_utc))
    elif event is not None:
        coming = (parse_utc(event["start_utc"]), event_out(ctx, event))
    gap = coming[0] - ctx.now_utc if current is None and coming else 0
    fits = executor.safe_items(state.problem, state.plan, state.executor, gap) if gap else []
    count = ctx.settings["executor"].swap_count
    alerts = [
        Alert(
            item_id=id_of(a.key),
            title=require_item(ctx, id_of(a.key)).title,
            kind=a.kind,
            latest_start=ctx.local(format_utc(a.latest_start)) or "",
        )
        for a in shown.alerts
    ]
    return NowOut(
        current=current,
        current_source="timer" if timer else "block" if covering else "event" if happening else "free",
        timer_minutes=elapsed_seconds(ctx, timer) // 60 if timer else 0,
        next=coming[1] if coming else None,
        swaps=[swap_out(ctx, w) for w in shown.swaps],
        alerts=alerts,
        # How long each would take of the gap (what's left of it, or the gap), not the gap itself on every one.
        fits=[
            swap_out(ctx, w).model_copy(update={"minutes": min(gap, state.problem.items[w.key].need * 15)})
            for w in fits
            if w.chunk_minutes <= gap
        ][:count],
        gap_minutes=gap,
    )


def fixed_events(ctx: Ctx) -> list[dict[str, Any]]:
    """Today's classes and events still to end, that take your time."""
    return rows(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status = 'todo' AND blocks_time = 1 "
        "AND end_utc > ? AND start_utc < ? ORDER BY start_utc",
        [ctx.user_id, format_utc(ctx.now_utc), format_utc(ctx.now_utc + 1440)],
    )


def event_out(ctx: Ctx, event: dict[str, Any]) -> BlockOut:
    out = block_out(ctx, event["id"], parse_utc(event["start_utc"]), parse_utc(event["end_utc"]))
    return out.model_copy(update={"key": out.key.replace("T", "F", 1), "fixed": True})


def timed_now(ctx: Ctx, timer: dict[str, Any], planned: list[Any], events: list[dict[str, Any]]) -> BlockOut:
    """The timed item from the timer's start: until its own block ends when it has one now (or starting within the
    quarter hour the plan rounds to), else until what's left of it runs out, stopped by the next class."""
    started = parse_utc(timer["start_utc"])
    mine = next((b for b in planned if b.item_id == timer["item_id"] and b.start_utc <= ctx.now_utc + 15), None)
    if mine is not None:
        end = mine.end_utc
    else:
        item = require_item(ctx, timer["item_id"])
        done = minutes_by_item(ctx.conn, ctx.user_id).get(item.id, 0)
        end = ctx.now_utc + max(15, (item.duration_units or 4) * 15 - done)
        end = min([end, *(parse_utc(e["start_utc"]) for e in events if parse_utc(e["start_utc"]) > ctx.now_utc)])
    return block_out(ctx, timer["item_id"], started, max(end, ctx.now_utc + 1))


@query("fits")
def fits(ctx: Ctx, inp: FitsInput) -> list[Swap]:
    """Items that fit a gap (until the next block when no length is given), safe, best first."""
    _, found = fits_view(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), inp.minutes)
    return [swap_out(ctx, w) for w in found]


@query("plan")
def plan(ctx: Ctx, inp: RangeInput) -> PlanOut:
    """Blocks and fixed items in a range, with hours per day."""
    lo = parse_utc(ctx.utc(inp.start, "start")) if inp.start else ctx.now_utc
    hi = parse_utc(ctx.utc(inp.end, "end")) if inp.end else lo + ctx.settings["time"].horizon_days * 1440
    saved = current_plan(ctx.conn, ctx.user_id)
    coming = ahead(ctx.conn, ctx.user_id, saved)
    pins = rows(ctx.conn, "SELECT * FROM pins WHERE user_id = ? ORDER BY created_utc DESC", [ctx.user_id])
    blocks = []
    going: list[tuple[int, int, int]] = []  # the saved plan's blocks under way now: item, start, end
    if saved is not None:
        for r in rows(
            ctx.conn,
            # What you deleted, skipped or finished leaves at once, not when the replan lands; past blocks stay.
            "SELECT b.* FROM blocks b JOIN items i ON i.id = b.item_id WHERE b.plan_id = ? AND b.end_utc > ? "
            "AND b.start_utc < ? AND (i.status = 'todo' OR b.end_utc <= ?) ORDER BY b.start_utc",
            [saved["id"], format_utc(lo), format_utc(hi), format_utc(ctx.now_utc)],
        ):
            start, end = parse_utc(r["start_utc"]), parse_utc(r["end_utc"])
            if coming is not None and start >= ctx.now_utc:
                continue  # what's ahead is the quick placement's until the replan lands
            if start < ctx.now_utc < end:
                going.append((r["item_id"], start, end))
            blocks.append(
                block_out(
                    ctx,
                    r["item_id"],
                    start,
                    end,
                    json.loads(r["cost"]),
                    # a start of something that runs by itself that went by unstarted is that quarter hour, missed,
                    # not its whole run (1 Nov: each missed Laundry start drew two hours, cut in two at now)
                    running=end > ctx.now_utc,
                    tentative=bool(r["tentative"]),
                    pinned=pin_kind(pins, r),
                )
            )
    if coming is not None:
        blocks = sorted(blocks + placed_ahead(ctx, coming, max(lo, ctx.now_utc), hi, going), key=lambda b: b.start)
    blocks = coalesced(past_states(ctx, blocks))  # pieces join only with pieces that went the same way
    blocks = later_start_only(ctx, blocks)
    fixed = [
        item_out(ctx, item_from_row(r))
        for r in rows(
            ctx.conn,
            "SELECT * FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status = 'todo' "
            "AND end_utc > ? AND start_utc < ? ORDER BY start_utc",
            [ctx.user_id, format_utc(lo), format_utc(hi)],
        )
    ]
    fixed = optional_marked(ctx, fixed, blocks)
    hours: dict[str, float] = {}
    for b in blocks:
        day = b.start[:10]
        # A task that runs by itself asks only its first quarter hour of you.
        minutes = UNIT_MIN if b.background else parse_utc(ctx.utc(b.end)) - parse_utc(ctx.utc(b.start))
        hours[day] = hours.get(day, 0) + minutes / 60
    plan_id = saved["id"] if saved else None
    return PlanOut(
        plan_id=plan_id,
        blocks=blocks,
        fixed=fixed,
        day_hours=hours,
        provisional=coming is not None,
        generation=generation(ctx.conn, ctx.user_id) if coming is not None else saved["generation"] if saved else 0,
        sessions=sittings(ctx, lo, hi),
    )


def optional_marked(ctx: Ctx, fixed: list[ItemOut], blocks: list[BlockOut]) -> list[ItemOut]:
    """Optional events (a `skippable` rule's) marked: one you said you'd go to, and one whose time the plan gives to
    work, with that work, so the calendar draws it as skipped rather than the work over it as if you were going."""
    text = ctx.settings["text"].rules()
    optional = [
        identity_text(norm(t, text))
        for r in ctx.settings["rules"]
        if r.type == "skippable" and r.enabled
        for t in r.params.get("titles", [])
        if t.strip()
    ]
    if not optional:
        return fixed
    going = set(kv_get(ctx.conn, "events_kept", [], ctx.user_id))
    work = [b for b in blocks if b.state is None and not b.background]
    out = []
    for f in fixed:
        title = identity_text(norm(f.title, text))
        if not f.start or not f.end or not any(has_words(title, o) for o in optional):
            out.append(f)
            continue
        if f.id in going:
            out.append(f.model_copy(update={"optional": True, "going": True}))
            continue
        takes = [b.title for b in work if b.start < f.end and b.end > f.start]
        out.append(f.model_copy(update={"optional": True, "gives_way_to": ", ".join(dict.fromkeys(takes)) or None}))
    return out


def placed_ahead(
    ctx: Ctx, coming: list[PlannedBlock], lo: int, hi: int, going: list[tuple[int, int, int]]
) -> list[BlockOut]:
    """The quick placement's blocks in [lo, hi) of what's still to do, as the plan view shows them while the replan
    is coming; a block under way stays as the saved plan has it."""
    todo = {
        r["id"] for r in rows(ctx.conn, "SELECT id FROM items WHERE user_id = ? AND status = 'todo'", [ctx.user_id])
    }
    out = []
    for b in coming:
        if b.end_utc <= lo or b.start_utc >= hi or b.item_id not in todo:
            continue
        if any(i == b.item_id and s < b.end_utc and b.start_utc < e for i, s, e in going):
            continue
        out.append(
            block_out(ctx, b.item_id, b.start_utc, b.end_utc, running=True, tentative=b.tentative, pinned=b.pinned)
        )
    return out


def sittings(ctx: Ctx, lo: int, hi: int) -> list[BlockOut]:
    """What you timed between `lo` and `hi`, when you did it: the timer's records, one item's touching ones as one
    (a replan cuts a running timer's record in two). The running timer isn't one yet: the grid draws it live."""
    spans: list[list[int]] = []  # item id, start, end
    for r in rows(
        ctx.conn,
        "SELECT item_id, start_utc, end_utc FROM progress WHERE user_id = ? AND source = 'timer' AND start_utc "
        "IS NOT NULL AND end_utc IS NOT NULL AND end_utc > ? AND start_utc < ? ORDER BY item_id, start_utc",
        [ctx.user_id, format_utc(lo), format_utc(hi)],
    ):
        start, end = parse_utc(r["start_utc"]), parse_utc(r["end_utc"])
        if spans and spans[-1][0] == r["item_id"] and start <= spans[-1][2]:
            spans[-1][2] = max(spans[-1][2], end)
        elif end > start:
            spans.append([r["item_id"], start, end])
    out = [block_out(ctx, item_id, start, end) for item_id, start, end in sorted(spans, key=lambda s: s[1])]
    return [b.model_copy(update={"key": "S" + b.key[1:]}) for b in out]


def past_states(ctx: Ctx, blocks: list[BlockOut]) -> list[BlockOut]:
    """What became of each block that has ended: the item finished, or this block marked done (or, while unmarked
    blocks count as done, left unmarked) is done; a timer sitting of the item over it, timed; marked not done, or
    left unmarked while unmarked blocks are planned again, or mostly under other things you timed, missed; the item
    deleted or skipped, gone."""
    blocks = split_at_now(ctx, blocks)
    past = [b for b in blocks if b.end <= (ctx.local(ctx.now_text) or "")]
    if not past:
        return blocks
    ids = sorted({b.item_id for b in past})
    marks = ",".join("?" * len(ids))
    status = {r["id"]: r["status"] for r in rows(ctx.conn, f"SELECT id, status FROM items WHERE id IN ({marks})", ids)}
    lo = min(parse_utc(ctx.utc(b.start)) for b in past)
    recorded = rows(
        ctx.conn,
        f"SELECT item_id, source, minutes, start_utc, end_utc FROM progress WHERE item_id IN ({marks}) "
        "AND source IN ('timer', 'review') AND start_utc IS NOT NULL AND end_utc > ?",
        [*ids, format_utc(lo)],
    )
    counts = ctx.settings["planner"].assume_unreviewed == "done"
    sittings = sittings_between(ctx.conn, ctx.user_id, lo, ctx.now_utc, ctx.now_utc)
    background = background_ids(ctx.conn, ctx.user_id)
    states = {}
    for b in past:
        start, end = parse_utc(ctx.utc(b.start)), parse_utc(ctx.utc(b.end))
        over = [
            r
            for r in recorded
            if r["item_id"] == b.item_id and parse_utc(r["start_utc"]) < end and parse_utc(r["end_utc"]) > start
        ]
        timed = timed_over(b.item_id, start, end, sittings, background)
        if status.get(b.item_id) in ("dropped", "skipped"):
            states[b.key] = "gone"
        elif timed == OWN:
            states[b.key] = "timed"  # finished or not, the sitting is what happened there
        elif status.get(b.item_id) == "done":
            states[b.key] = "done"
        elif reviewed := [r for r in over if r["source"] == "review"]:
            states[b.key] = "done" if reviewed[-1]["minutes"] > 0 else "missed"
        else:  # mostly under other things you timed, it didn't happen
            states[b.key] = "done" if counts and timed is None else "missed"
    return [b.model_copy(update={"state": states[b.key]}) if b.key in states else b for b in blocks]


def later_start_only(ctx: Ctx, blocks: list[BlockOut]) -> list[BlockOut]:
    """Missed starts of something that runs by itself left out while a later start is planned: one Laundry on the
    calendar, not one for every quarter hour it could have been put on (1 Nov: "why are there three events named
    laundry"). With none planned, the missed one stays, to say so and to be marked done if you did start it."""
    ahead = {b.item_id for b in blocks if b.state is None}
    if not ahead:
        return blocks
    marks = ",".join("?" * len(ahead))
    runs = {
        r["id"] for r in rows(ctx.conn, f"SELECT id FROM items WHERE background = 1 AND id IN ({marks})", sorted(ahead))
    }
    return [b for b in blocks if not (b.state == "missed" and b.item_id in runs)]


def split_at_now(ctx: Ctx, blocks: list[BlockOut]) -> list[BlockOut]:
    """A block running across now, apart at the last quarter hour: what's gone of it is past (and says what became
    of it), the rest is still the plan. A replan keeps the two in one record, so 10–10:30 missed and 10:30–12:30
    planned read as one block from 10. Not the block you're timing: the timer shows that one."""
    timed = {r["item_id"] for r in rows(ctx.conn, "SELECT item_id FROM timer WHERE user_id = ?", [ctx.user_id])}
    cut = ctx.local(format_utc(ctx.now_utc // UNIT_MIN * UNIT_MIN)) or ""
    out = []
    for b in blocks:
        if b.start < cut < b.end and b.item_id not in timed:
            share = (parse_utc(ctx.utc(cut)) - parse_utc(ctx.utc(b.start))) / max(1, minutes_of_block(ctx, b))
            gone = {k: round(v * share) for k, v in b.cost.items()}
            out.append(b.model_copy(update={"end": cut, "cost": gone}))
            ahead = {k: v - gone[k] for k, v in b.cost.items()}
            out.append(b.model_copy(update={"key": f"T{b.item_id}@{cut}", "start": cut, "cost": ahead}))
        else:
            out.append(b)
    return out


def minutes_of_block(ctx: Ctx, b: BlockOut) -> int:
    return parse_utc(ctx.utc(b.end)) - parse_utc(ctx.utc(b.start))


PIN_STRENGTH = {None: 0, "preferred": 1, "locked": 2}


def coalesced(blocks: list[BlockOut]) -> list[BlockOut]:
    """Touching blocks of one item as one block. Every replan cuts the plan at that moment and the pieces stay in
    the record, so a sitting showed as 12:00–13:00, 13:00–13:15 and 13:15–14:00 side by side (M16). A pinned piece
    and an unpinned one of the same sitting are one block too, pinned as the stronger (27 Oct: a block you dragged
    next to the rest of its sitting showed as two)."""
    out: list[BlockOut] = []
    for b in blocks:
        last = out[-1] if out else None
        joins = last is not None and (last.item_id, last.end, last.tentative, last.state) == (
            b.item_id,
            b.start,
            b.tentative,
            b.state,
        )
        if last is not None and joins:
            cost = {k: last.cost.get(k, 0) + b.cost.get(k, 0) for k in last.cost.keys() | b.cost.keys()}
            pinned = max(last.pinned, b.pinned, key=lambda p: PIN_STRENGTH.get(p, 0))
            out[-1] = last.model_copy(update={"end": b.end, "cost": cost, "pinned": pinned})
        else:
            out.append(b)
    return out


def pin_kind(pins: list[dict[str, Any]], block: dict[str, Any]) -> str | None:
    """The kind of the newest pin under a block; a block elsewhere isn't pinned, though its item may be."""
    return next(
        (
            p["kind"]
            for p in pins
            if p["item_id"] == block["item_id"]
            and p["start_utc"] < block["end_utc"]
            and block["start_utc"] < p["end_utc"]
        ),
        None,
    )


@query("items")
def items(ctx: Ctx, inp: ItemsInput) -> list[ItemOut]:
    """Items, filtered, with progress and what's left."""
    sql = "SELECT * FROM items WHERE user_id = ? AND when_kind != 'fixed'"
    params: list[Any] = [ctx.user_id]
    if inp.status != "all":
        sql, params = sql + " AND status = ?", [*params, inp.status]
    done = minutes_by_item(ctx.conn, ctx.user_id)
    found = [item_from_row(r) for r in rows(ctx.conn, sql + " ORDER BY coalesce(due_utc, '9999'), id", params)]
    areas = area_names(ctx.conn, ctx.user_id)
    if inp.area:
        found = [i for i in found if i.area_id and areas.get(i.area_id, "").lower() == inp.area.lower()]
    if inp.text:
        found = [i for i in found if inp.text.lower() in i.title.lower()]
    waiting = waiting_on(ctx)
    out = [item_out(ctx, i, done.get(i.id or 0, 0)) for i in found]
    return [o.model_copy(update={"waiting_on": waiting.get(o.id, [])}) for o in out]


@query("events")
def events(ctx: Ctx, inp: EventsInput) -> list[ItemOut]:
    """Calendar events whose title has the text, one per series (its next time, else its last), soonest first."""
    text = inp.text.strip().lower()
    if not text:
        return []
    now = format_utc(ctx.now_utc)
    best: dict[str, Any] = {}
    for r in rows(
        ctx.conn, "SELECT * FROM items WHERE user_id = ? AND when_kind = 'fixed' AND status != 'dropped'", [ctx.user_id]
    ):
        if text not in r["title"].lower() or r["start_utc"] is None:
            continue
        series = f"s{r['series_id']}" if r["series_id"] is not None else f"i{r['id']}"
        was = best.get(series)
        if was is None or _closer(r["start_utc"], was["start_utc"], now):
            best[series] = r
    found = sorted(best.values(), key=lambda r: (r["start_utc"] < now, r["start_utc"] if r["start_utc"] >= now else ""))
    return [item_out(ctx, item_from_row(r)) for r in found[: max(1, inp.limit)]]


def _closer(start: str, other: str, now: str) -> bool:
    """Whether `start` is a better occurrence to show than `other`: the next one to come, else the latest gone."""
    if (start >= now) != (other >= now):
        return start >= now
    return start < other if start >= now else start > other


@query("item")
def item(ctx: Ctx, inp: ItemRef) -> ItemDetail:
    """One item with its blocks, progress and dependencies."""
    found = require_item(ctx, inp.id)
    saved = current_plan(ctx.conn, ctx.user_id)
    pins = rows(ctx.conn, "SELECT * FROM pins WHERE item_id = ? ORDER BY created_utc DESC", [inp.id])
    blocks = [
        block_out(
            ctx,
            r["item_id"],
            parse_utc(r["start_utc"]),
            parse_utc(r["end_utc"]),
            json.loads(r["cost"]),
            pinned=pin_kind(pins, r),
        )
        for r in rows(
            ctx.conn,
            "SELECT * FROM blocks WHERE plan_id = ? AND item_id = ? ORDER BY start_utc",
            [saved["id"] if saved else -1, inp.id],
        )
    ]
    progress = [
        {"source": r["source"], "minutes": r["minutes"], "start": ctx.local(r["start_utc"])}
        for r in rows(ctx.conn, "SELECT * FROM progress WHERE item_id = ? ORDER BY id", [inp.id])
    ]
    deps = [
        {"depends_on_id": r["depends_on_id"], "fraction": r["fraction"], "lag_min": r["lag_min"]}
        for r in rows(ctx.conn, "SELECT * FROM dependencies WHERE item_id = ?", [inp.id])
    ]
    done = minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)
    return ItemDetail(item=item_out(ctx, found, done), blocks=blocks, progress=progress, depends_on=deps)


@query("parse")
def parse_line(ctx: Ctx, inp: ParseInput) -> ParseOutput:
    """How a quick-add line reads, with a span per recognized token."""
    result = parse(
        inp.text,
        to_local(ctx.now_utc, ctx.tz),
        ctx.day_start,
        area_names(ctx.conn, ctx.user_id).values(),
        in_use(ctx.settings["presets"], ctx.settings["school"]),
    )
    spans = [{"start": s.start, "end": s.end, "kind": s.kind, "value": s.value} for s in result.spans]
    fields = dict(result.fields)
    title = fields.get("title") or ""
    if title and "start_local" not in fields:
        # What add will guess from the title, so the add box shows it as a chip you can change (COMBINED.md 55).
        if not fields.get("preset") and (
            preset := guess_preset(title, in_use(ctx.settings["presets"], ctx.settings["school"]))
        ):
            fields["preset"] = preset
        if not fields.get("area") and (course := course_of(title)):
            fields["area"] = course
    return ParseOutput(fields=fields, spans=spans, warnings=result.warnings)


@query("paces")
def paces(ctx: Ctx, inp: Empty) -> PacesOut:
    """Saved paces, the default, the dials in effect now, and when the current period ends."""
    periods = list(pace_periods(ctx.conn, ctx.user_id))
    saved = ctx.settings["paces"]
    dials = dials_on(ctx.today, periods, saved, ctx.settings["pace"].default, ctx.settings["pace"].weekly)
    period = next(
        (p for p in periods if p.start_date <= ctx.today and (p.end_date is None or ctx.today <= p.end_date)), None
    )
    return PacesOut(
        default=ctx.settings["pace"].default,
        paces={k: v.model_dump() for k, v in saved.items()},
        now_label=pace_label(dials, saved),
        now_dials=dials.model_dump(),
        period_end=period.end_date.isoformat() if period and period.end_date else None,
    )


NOT_SLIPPING = ("Routine", "Habit")  # a meal or a habit missed is missed, not late


def slipping(ctx: Ctx, saved: dict | None, late: set[int]) -> list[LateItem]:
    """Work with a due the plan finishes after it, or doesn't plan at all though it's due in the plan's range: soft
    deadlines (readings) and anything hard the report doesn't already call late. Soonest due first."""
    if saved is None:
        return []
    horizon_end = ctx.now_utc + ctx.settings["time"].horizon_days * 1440
    done = minutes_by_item(ctx.conn, ctx.user_id)
    out = []
    for r in rows(
        ctx.conn,
        "SELECT i.id, i.title, i.due_utc, i.preset, MAX(b.end_utc) AS last FROM items i "
        "LEFT JOIN blocks b ON b.item_id = i.id AND b.plan_id = ? "
        "WHERE i.user_id = ? AND i.status = 'todo' AND i.when_kind != 'fixed' AND i.due_utc IS NOT NULL "
        "AND i.amount != 'open' AND COALESCE(i.duration_units, 1) > 0 GROUP BY i.id",
        [saved["id"], ctx.user_id],
    ):
        if r["id"] in late or r["preset"] in NOT_SLIPPING:
            continue
        due = parse_utc(r["due_utc"])
        if r["last"] is not None and parse_utc(r["last"]) > due:
            hours = round((parse_utc(r["last"]) - due) / 60, 1)
            out.append(LateItem(item_id=r["id"], title=r["title"], due=ctx.local(r["due_utc"]), hours=hours))
        elif (
            r["last"] is None
            and due <= horizon_end
            and (remaining_minutes(require_item(ctx, r["id"]), done.get(r["id"], 0)) or 0) > 0
        ):
            out.append(LateItem(item_id=r["id"], title=r["title"], due=ctx.local(r["due_utc"]), hours=0, planned=False))
    return sorted(out, key=lambda i: i.due or "9999")


@query("status")
def status(ctx: Ctx, inp: Empty) -> StatusOut:
    """The plan generation, the current plan, the timer and whether Friday is set up."""
    saved = current_plan(ctx.conn, ctx.user_id)
    timer = running(ctx)
    timer_out = timing(ctx, timer) if timer is not None else None
    ready = ctx.settings["time"].timezone is not None and ctx.settings["sleep"] is not None
    report = json.loads(saved["report"]) if saved else {}
    notices = report.get("notices", [])
    found = {
        r["id"]: r for r in rows(ctx.conn, "SELECT id, title, due_utc FROM items WHERE user_id = ?", [ctx.user_id])
    }
    late_hours = {int(k): hours for k, hours in report.get("late_hours", {}).items() if int(k) in found}
    late = {found[k]["title"]: hours for k, hours in late_hours.items()}
    late_items = sorted(
        (
            LateItem(item_id=k, title=found[k]["title"], due=ctx.local(found[k]["due_utc"]), hours=hours)
            for k, hours in late_hours.items()
        ),
        key=lambda i: i.due or "9999",
    )
    return StatusOut(
        generation=generation(ctx.conn, ctx.user_id),
        plan_id=saved["id"] if saved else None,
        plan_generation=saved["generation"] if saved else None,
        timer=timer_out,
        alongside=[timing(ctx, t) for t in all_running(ctx) if timer is None or t["item_id"] != timer["item_id"]],
        settings_version=settings_version(ctx.conn, ctx.user_id),
        ready=ready,
        notices=notices,
        late=late,
        late_items=late_items,
        slipping=slipping(ctx, saved, set(late_hours)),
        problems=list(kv_get(ctx.conn, "server_problems", {}, ctx.user_id).values()),
        decisions=decisions(ctx, report, late_items),
        config_keys=kv_get(ctx.conn, "config_keys", [], ctx.user_id),
        demo=bool(kv_get(ctx.conn, "demo", False, ctx.user_id)),
        server_pid=os.getpid(),
        server_build=os.environ.get("FRIDAY_APP_BUILD") or None,
        server_orphan=os.getppid() == 1,  # the app that started it quit without stopping it
        suggestions=(
            one(
                ctx.conn,
                # repeating calendar events wait in Settings → Repeating, not the inbox
                "SELECT count(*) AS n FROM suggestions WHERE user_id = ? AND status = 'pending' "
                "AND (batch IS NULL OR batch NOT LIKE 'repeat:%')",
                [ctx.user_id],
            )
            or {"n": 0}
        )["n"],
    )


@query("settings")
def settings(ctx: Ctx, inp: Empty) -> dict[str, Any]:
    """Every settings key with its value."""
    return {key: to_json(key, value) for key, value in ctx.settings.items()}


@query("log_list")
def log_list(ctx: Ctx, inp: LogListInput) -> list[LogEntry]:
    """The latest commands, newest first."""
    sql, params = "SELECT * FROM command_log WHERE user_id = ?", [ctx.user_id]
    if inp.item_id is not None:
        # Commands name an item in their input, except `add`, whose result holds the new item.
        paths = ("input, '$.id'", "input, '$.item_id'", "input, '$.depends_on_id'", "result, '$.item.id'")
        named = " OR ".join(f"json_extract({path}) = ?" for path in paths)
        sql, params = f"{sql} AND ({named})", [*params, *[inp.item_id] * len(paths)]
    found = rows(ctx.conn, sql + " ORDER BY id DESC LIMIT ?", [*params, inp.limit])
    return [
        LogEntry(
            id=r["id"],
            at=ctx.local(r["at_utc"]) or "",
            actor=r["actor"],
            command=r["command"],
            input=json.loads(r["input"]),
            undone_by=r["undone_by"],
        )
        for r in found
    ]


@query("stats")
def stats(ctx: Ctx, inp: Empty) -> StatsOut:
    """This week's completions and hours, late items, and how actual times compare with estimates."""
    # From the start of this planning week (Settings' week start, at the day start), not a day before it.
    first = ctx.today - timedelta(days=(ctx.today.weekday() - ctx.settings["time"].grid_spec().week_start) % 7)
    since = format_utc(to_utc(local_midnight(first) + timedelta(minutes=ctx.day_start), ctx.tz))
    done = rows(ctx.conn, "SELECT * FROM completions WHERE user_id = ? AND completed_utc >= ?", [ctx.user_id, since])
    saved = current_plan(ctx.conn, ctx.user_id)
    late = len(json.loads(saved["report"]).get("late_hours", {})) if saved else 0
    estimated = [r for r in done if r["friday_estimate_units"]]
    ratio = (
        sum(r["actual_minutes"] for r in estimated) / sum(r["friday_estimate_units"] * 15 for r in estimated)
        if estimated
        else None
    )
    return StatsOut(
        done_this_week=len(done),
        hours_this_week=round(sum(r["actual_minutes"] for r in done) / 60, 1),
        late_items=late,
        estimate_ratio=round(ratio, 2) if ratio else None,
    )
