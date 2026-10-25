"""Looking at a day or a week (DESIGN §8, §18.9, §20.4): review, brief, week_review."""

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from friday.api.commands import Changed, DateInput, RangeInput, WeekNoteInput
from friday.api.types import Empty
from friday.api.views import AreaWeek, BriefOut, DeadlineWeek, ReviewOut, Rock, WeekItem, WeekOut
from friday.commands.fields import item_out
from friday.commands.progress import day_blocks, day_bounds, reviewed_minutes
from friday.commands.queries import block_out, now, paces, plan
from friday.commands.registry import Ctx, command, query
from friday.commands.sleeping import missing, planned_min, recorded
from friday.core.db import one, rows
from friday.core.rows import item_from_row
from friday.core.time import format_utc, parse_utc
from friday.planner.progress import minutes_by_item, remaining_minutes
from friday.planner.snapshot import day_overrides, pace_periods
from friday.planner.store import area_names, current_plan, kv_get


@query("review")
def review(ctx: Ctx, inp: DateInput) -> ReviewOut:
    """A day's review sheet: its blocks, timer sessions and logged work, and items that look finished."""
    day = date.fromisoformat(inp.date) if inp.date else ctx.today
    lo, hi = day_bounds(ctx, day)
    found = day_blocks(ctx, day)
    blocks = [block_out(ctx, b["item_id"], b["start"], b["end"]) for b in found]
    answered = {out.key: reviewed_minutes(ctx, b) for out, b in zip(blocks, found, strict=True)}
    sessions = [
        {
            "item_id": r["item_id"],
            "source": r["source"],
            "start": ctx.local(r["start_utc"]),
            "end": ctx.local(r["end_utc"]),
            "minutes": r["minutes"],
            "block_key": r["block_key"],
        }
        for r in rows(
            ctx.conn,
            "SELECT * FROM progress WHERE user_id = ? AND start_utc >= ? AND start_utc < ?",
            [ctx.user_id, format_utc(lo), format_utc(hi)],
        )
    ]
    done = minutes_by_item(ctx.conn, ctx.user_id)
    finished = []
    for r in rows(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND when_kind != 'fixed' AND amount != 'open'",
        [ctx.user_id],
    ):
        it = item_from_row(r)
        if done.get(it.id or 0) and remaining_minutes(it, done[it.id or 0]) == 0:
            finished.append(item_out(ctx, it, done[it.id or 0]))
    reviewed = bool(
        rows(ctx.conn, "SELECT 1 FROM reviews WHERE user_id = ? AND date = ?", [ctx.user_id, day.isoformat()])
    )
    settled = {k: v for k, v in answered.items() if v is not None}
    return ReviewOut(
        date=day.isoformat(),
        reviewed=reviewed,
        blocks=blocks,
        sessions=sessions,
        finished=finished,
        settled=settled,
        sleep=missing(ctx, day),
    )


@query("brief")
def brief(ctx: Ctx, inp: Empty) -> BriefOut:
    """Today's big rocks, fixed items, alerts and pace, with a one-line summary, as data and plain text."""
    lo, hi = day_bounds(ctx, ctx.today)
    today = plan(ctx, RangeInput(start=ctx.local(format_utc(lo)), end=ctx.local(format_utc(hi))))
    planned: dict[int, int] = defaultdict(int)
    for b in today.blocks:
        planned[b.item_id] += int(parse_utc_local(ctx, b.end) - parse_utc_local(ctx, b.start))
    saved = current_plan(ctx.conn, ctx.user_id)
    slack = json.loads(saved["report"]).get("slack_minutes", {}) if saved else {}
    soon = format_utc(ctx.now_utc + 48 * 60)
    candidates = rows(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND when_kind != 'fixed' "
        "AND (firmness = 'hard' AND due_utc <= ?)",
        [ctx.user_id, soon],
    )
    routines = {
        r["id"] for r in rows(ctx.conn, "SELECT id FROM items WHERE user_id = ? AND preset = 'Routine'", [ctx.user_id])
    }
    ids = (set(planned) | {r["id"] for r in candidates}) - routines  # lunch isn't what matters most today
    rocks = [rock(ctx, item_id, planned.get(item_id, 0), soon) for item_id in ids]
    rocks = sorted(
        (r for r in rocks if r is not None),
        key=lambda r: (
            not (r.hard and (r.due or "") <= ctx.local(soon)),
            slack.get(str(r.item_id), 10**6),
            -r.planned_min,
        ),
    )[:5]
    alerts = now(ctx, Empty()).alerts
    pace = pace_line(ctx)
    hours = sum(planned.values()) / 60
    summary = " · ".join(
        [f"{round(hours, 1):g} h planned", f"{len(today.fixed)} fixed"]
        + ([pace] if pace else [])
        + [f"{len(alerts)} alerts"] * bool(alerts)
    )
    lines = [summary] + [
        f"• {r.title} ({spoken(r.planned_min)} today{', due ' + r.due[5:16].replace('T', ' ') if r.due else ''})"
        for r in rocks
    ]
    slept = short_night(ctx)
    return BriefOut(
        rocks=rocks, fixed=today.fixed, alerts=alerts, pace=pace, sleep=slept, summary=summary, text="\n".join(lines)
    )


def short_night(ctx: Ctx) -> str | None:
    """Last night, when you tracked it and it fell an hour or more short of the sleep you plan for."""
    if not ctx.settings["sleep_tracking"].on or ctx.settings["sleep"] is None:
        return None
    evening = ctx.today - timedelta(days=1)
    night = recorded(ctx, 2).get(evening)
    if night is None or night.slept_min is None:
        return None
    short = planned_min(ctx, day_overrides(ctx.conn, ctx.user_id), evening) - night.slept_min
    if short < 60:
        return None
    return f"You slept {spoken(night.slept_min)} last night, {spoken(short)} less than you plan for. An Easy day?"


def spoken(minutes: int) -> str:
    """7h45, 2h, 30m."""
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}" if hours and rest else f"{hours}h" if hours else f"{rest}m"


def parse_utc_local(ctx: Ctx, local: str) -> int:
    return parse_utc(ctx.utc(local))


def rock(ctx: Ctx, item_id: int, planned_min: int, soon: str) -> Rock | None:
    found = one(ctx.conn, "SELECT * FROM items WHERE id = ?", [item_id])
    if found is None or found["when_kind"] == "fixed":
        return None
    hard = found["firmness"] == "hard" and found["due_utc"] is not None and found["due_utc"] <= soon
    if not planned_min and not hard:
        return None
    return Rock(
        item_id=item_id, title=found["title"], planned_min=planned_min, due=ctx.local(found["due_utc"]), hard=hard
    )


def pace_line(ctx: Ctx) -> str | None:
    """The pace when it isn't the default, or that a period ended yesterday."""
    now_pace = paces(ctx, Empty())
    if now_pace.now_label != now_pace.default:
        return f"{now_pace.now_label} pace" + (f" until {now_pace.period_end}" if now_pace.period_end else "")
    yesterday = ctx.today - timedelta(days=1)
    if any(p.end_date == yesterday for p in pace_periods(ctx.conn, ctx.user_id)):
        return f"Back to {now_pace.default} today"
    return None


@query("week_review")
def week_review(ctx: Ctx, inp: DateInput) -> WeekOut:
    """The week holding a date (this week when left out): planned against actual by area, deadlines hit, moves made
    and notifications acted on."""
    day = date.fromisoformat(inp.date) if inp.date else ctx.today
    first = day - timedelta(days=(day.weekday() - ctx.settings["time"].grid_spec().week_start) % 7)
    days = [first + timedelta(days=n) for n in range(7)]
    lo, hi = day_bounds(ctx, first)[0], day_bounds(ctx, days[-1])[1]
    areas = area_names(ctx.conn, ctx.user_id)
    area_of = {
        r["id"]: areas.get(r["area_id"], "No area")
        for r in rows(ctx.conn, "SELECT id, area_id FROM items WHERE user_id = ?", [ctx.user_id])
    }
    planned: dict[str, float] = defaultdict(float)
    intended: set[int] = set()
    for d in days:
        if d > ctx.today:
            break
        for b in morning_blocks(ctx, d):
            planned[area_of.get(b["item_id"], "No area")] += (parse_utc(b["end_utc"]) - parse_utc(b["start_utc"])) / 60
            intended.add(b["item_id"])
    actual: dict[str, float] = defaultdict(float)
    for r in rows(
        ctx.conn,
        "SELECT item_id, minutes FROM progress WHERE user_id = ? AND start_utc >= ? AND start_utc < ?",
        [ctx.user_id, format_utc(lo), format_utc(hi)],
    ):
        actual[area_of.get(r["item_id"], "No area")] += r["minutes"] / 60
    fixed: dict[str, float] = defaultdict(float)
    for r in rows(
        ctx.conn,
        "SELECT event_kind, start_utc, end_utc FROM items WHERE user_id = ? AND when_kind = 'fixed' "
        "AND status != 'dropped' AND start_utc >= ? AND start_utc < ?",
        [ctx.user_id, format_utc(lo), format_utc(hi)],
    ):
        fixed[r["event_kind"] or "other"] += (parse_utc(r["end_utc"]) - parse_utc(r["start_utc"])) / 60
    return WeekOut(
        start=first.isoformat(),
        end=days[-1].isoformat(),
        areas=[
            AreaWeek(area=a, planned_h=round(planned[a], 1), actual_h=round(actual[a], 1))
            for a in sorted(set(planned) | set(actual))
        ],
        fixed_h={k: round(v, 1) for k, v in fixed.items()},
        deadlines=deadlines(ctx, lo, hi),
        moves=count(ctx, "command_log", "actor = 'you' AND command IN ('pin', 'unpin', 'shove')", "at_utc", lo, hi),
        notifications={
            "sent": count(ctx, "notifications", "kind != 'test'", "sent_utc", lo, hi),
            "acted": count(ctx, "notifications", "acted = 1", "sent_utc", lo, hi),
            "dismissed": count(ctx, "notifications", "acted = 0", "sent_utc", lo, hi),
        },
        finished=week_items(
            ctx, "status = 'done' AND completed_utc >= ? AND completed_utc < ?", [lo, hi], "completed_utc"
        ),
        carried=carried(ctx, intended),
        coming=week_items(
            ctx,
            "status = 'todo' AND ((due_utc >= ? AND due_utc < ?) "
            "OR (when_kind = 'fixed' AND start_utc >= ? AND start_utc < ?))",
            [hi, hi + 7 * 1440, hi, hi + 7 * 1440],
            "COALESCE(due_utc, start_utc)",
        ),
        note=(kv_get(ctx.conn, "week_notes", {}, ctx.user_id) or {}).get(first.isoformat(), {}),
    )


def week_items(ctx: Ctx, condition: str, bounds: list[int], at: str) -> list[WeekItem]:
    areas = area_names(ctx.conn, ctx.user_id)
    found = rows(
        ctx.conn,
        f"SELECT *, {at} AS at FROM items WHERE user_id = ? AND {condition} ORDER BY at",
        [ctx.user_id, *(format_utc(b) for b in bounds)],
    )
    return [
        WeekItem(
            item_id=r["id"],
            title=r["title"],
            area=areas.get(r["area_id"]),
            when=ctx.local(r["at"]) or "",
            note="fixed" if r["when_kind"] == "fixed" else ("due" if r["due_utc"] else ""),
        )
        for r in found
    ]


def carried(ctx: Ctx, intended: set[int]) -> list[WeekItem]:
    """Items this week's plans held that are still open, with what's left."""
    areas = area_names(ctx.conn, ctx.user_id)
    done = minutes_by_item(ctx.conn, ctx.user_id)
    out = []
    for item_id in sorted(intended):
        found = one(
            ctx.conn, "SELECT * FROM items WHERE user_id = ? AND id = ? AND status = 'todo'", [ctx.user_id, item_id]
        )
        if found is None or found["when_kind"] == "fixed":
            continue
        item = item_from_row(found)
        left = remaining_minutes(item, done.get(item_id, 0))
        due = ctx.local(found["due_utc"])
        note = f"{round((left or 0) / 60, 1)} h left"
        out.append(
            WeekItem(item_id=item_id, title=found["title"], area=areas.get(found["area_id"]), when=due or "", note=note)
        )
    return out


@command("week_note")
def week_note(ctx: Ctx, inp: WeekNoteInput) -> Changed:
    """How the week felt and anything to remember, kept with the week."""
    notes = kv_get(ctx.conn, "week_notes", {}, ctx.user_id) or {}
    entry = notes.get(inp.week, {})
    for key, value in (("feel", inp.feel), ("notes", inp.notes)):
        if value is not None:
            entry[key] = value
    notes[inp.week] = entry
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "week_notes"}, {"value": json.dumps(notes)})
    return Changed(message="Saved")


def count(ctx: Ctx, table: str, condition: str, at: str, lo: int, hi: int) -> int:
    """Rows of `table` meeting `condition` with `at` in [lo, hi)."""
    sql = f"SELECT count(*) AS n FROM {table} WHERE user_id = ? AND {condition} AND {at} >= ? AND {at} < ?"
    found = one(ctx.conn, sql, [ctx.user_id, format_utc(lo), format_utc(hi)])
    return found["n"] if found else 0


def morning_blocks(ctx: Ctx, day: date) -> list[dict[str, Any]]:
    """That day's blocks in the plan in effect when the day began: what the morning intended."""
    lo, hi = day_bounds(ctx, day)
    found = one(
        ctx.conn,
        "SELECT id FROM plans WHERE user_id = ? AND created_utc <= ? ORDER BY id DESC LIMIT 1",
        [ctx.user_id, format_utc(lo)],
    )
    found = found or one(
        ctx.conn,
        "SELECT id FROM plans WHERE user_id = ? AND created_utc >= ? ORDER BY id LIMIT 1",
        [ctx.user_id, format_utc(lo)],
    )
    if found is None:
        return []
    return rows(
        ctx.conn,
        "SELECT * FROM blocks WHERE plan_id = ? AND start_utc >= ? AND start_utc < ?",
        [found["id"], format_utc(lo), format_utc(hi)],
    )


def deadlines(ctx: Ctx, lo: int, hi: int) -> list[DeadlineWeek]:
    out = []
    for r in rows(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND firmness = 'hard' AND when_kind != 'fixed' "
        "AND status IN ('todo', 'done') AND due_utc >= ? AND due_utc < ? ORDER BY due_utc",
        [ctx.user_id, format_utc(lo), format_utc(hi)],
    ):
        if r["status"] == "done":
            outcome = "on_time" if r["completed_utc"] <= r["due_utc"] else "late"
        else:
            outcome = "late" if parse_utc(r["due_utc"]) < ctx.now_utc else "open"
        out.append(DeadlineWeek(item_id=r["id"], title=r["title"], due=ctx.local(r["due_utc"]) or "", outcome=outcome))
    return out
