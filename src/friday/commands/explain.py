"""Explanations and triage (DESIGN §16): why, why_not, changes, preview_weights, rule_totals, triage, lighten."""

import json
from datetime import date
from typing import Any

from friday.api.commands import (
    BlockRef,
    LightenInput,
    LightenOption,
    LightenOut,
    PreviewWeightsInput,
    RuleTotalsInput,
    TriageOption,
    TriageOut,
    TriageStep,
    WhyNotInput,
    WhyNotOut,
    WhyOut,
)
from friday.api.types import ChangeOut, Empty
from friday.commands.fields import require_item
from friday.commands.horizon import saved_plan
from friday.commands.progress import parse_block_key
from friday.commands.registry import Ctx, query
from friday.commands.rules import readings, words
from friday.commands.timer import running
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.settings import validate_value
from friday.core.time import clock_time, format_utc, parse_utc, planning_date, to_local
from friday.engine.rules import RULE_TYPES, build_rules
from friday.planner.snapshot import gone_to_titles, take_snapshot
from friday.planner.spacing import Closer, closer_words
from friday.planner.store import current_plan, kv_get, load_item
from friday.planner.views import UnderWay, change_list, why_not_view
from friday.planner.views import lighten as run_lighten
from friday.planner.views import preview_weights as run_preview
from friday.planner.views import triage as run_triage


def saved_report(ctx: Ctx) -> dict[str, Any]:
    saved = current_plan(ctx.conn, ctx.user_id)
    if saved is None:
        raise FieldError("plan", "there's no plan yet; run `replan`")
    return json.loads(saved["report"]) | {"plan_id": saved["id"]}


def find_block(ctx: Ctx, key: str) -> dict[str, Any]:
    """The saved block a key names: the one starting there, or holding that time. The calendar cuts a block under way
    at now into what's gone and the rest (`plan`), and the rest's key is a time inside the saved block."""
    item_id, start = parse_block_key(ctx, key)
    saved = current_plan(ctx.conn, ctx.user_id)
    found = one(
        ctx.conn,
        "SELECT * FROM blocks WHERE plan_id = ? AND item_id = ? AND start_utc <= ? AND end_utc > ? "
        "ORDER BY start_utc DESC LIMIT 1",
        [saved["id"] if saved else -1, item_id, format_utc(start), format_utc(start)],
    )
    if found is None:
        raise FieldError("key", f"no block {key} in the current plan")
    return found


@query("why")
def why(ctx: Ctx, inp: BlockRef) -> WhyOut:
    """Why a block is where it is: its cost by rule and one plain sentence."""
    block = find_block(ctx, inp.key)
    costs = json.loads(block["cost"])
    return WhyOut(key=inp.key, sentence=sentence(ctx, block, costs), costs=costs, total=sum(costs.values()))


def sentence(ctx: Ctx, block: dict[str, Any], costs: dict[str, int]) -> str:
    """Deadline context, pins, the two largest costs by reason, then the first shaping constraint (§16)."""
    item = require_item(ctx, block["item_id"])
    report = saved_report(ctx)
    parts = []
    if item.due_utc:
        slack = report.get("slack_minutes", {}).get(str(item.id))
        due_at = to_local(parse_utc(item.due_utc), ctx.tz)
        due = f"Due {due_at:%a %-d %b} {clock_time(due_at)}"
        # late work says it's late, as the Plan page's note and the To-do tag do (23 Nov, the agreement check: its
        # block said "no room to spare: it has to happen as planned")
        late = report.get("late_hours", {}).get(str(item.id))
        if late:
            parts.append(f"{due}; the plan finishes it about {late_by(late)} after it's due")
        else:
            parts.append(f"{due}; {room(slack)}" if slack is not None else due)
    start, end = block["start_utc"], block["end_utc"]
    pinned = one(
        ctx.conn, "SELECT kind FROM pins WHERE item_id = ? AND start_utc < ? AND end_utc > ?", [item.id, end, start]
    )
    if pinned:
        parts.append("You pinned it here")
    if spaced := report.get("spacing_closer", {}).get(str(item.id)):
        parts.append(closer_words(Closer(**spaced)))
    # the Rules page's words for the built-in ones ("Wind down before bed", not "late night"; audit, 8 Nov)
    mine = readings(ctx)
    reasons = {r.name: words(r, mine) for r in ctx.settings["rules"]}
    top = sorted(((name, cost) for name, cost in costs.items() if cost), key=lambda nc: -nc[1])[:2]
    parts += [f"costs {cost / 100:.1f} for {reasons.get(name, name).replace('_', ' ')}" for name, cost in top]
    shaped = shaping(ctx, parse_utc(start))
    if shaped:
        parts.append(shaped)
    # the plan's paces are by planning day (audit, 12 Nov: the UTC date gave an evening block the next day's pace)
    day = planning_date(parse_utc(start), ctx.tz, ctx.day_start).isoformat()
    label = report.get("pace", {}).get(day)
    if label and label != ctx.settings["pace"].default:
        parts.append(f"{label} pace that day")
    return ". ".join(p[0].upper() + p[1:] for p in parts) + "." if parts else "Nothing in particular shaped it."


def late_by(hours: float) -> str:
    """How late, in the web's words (lateBy, web/src/lib/format.ts): whole days from a day, else to the quarter hour."""
    if hours >= 24:
        days = round(hours / 24)
        return f"{days} day{'' if days == 1 else 's'}"
    m = max(15, round(hours * 60 / 15) * 15)
    h, r = divmod(m, 60)
    return f"{h}h {r}m" if h and r else f"{h}h" if h else f"{r}m"


def room(slack_min: int) -> str:
    """Slack in words: how much later it could all start and still be on time."""
    if slack_min < 60:
        return "no room to spare: it has to happen as planned"
    if slack_min < 48 * 60:
        return f"it could all start {slack_min // 60} h later and still be on time"
    return f"it could all start {slack_min // 1440} days later and still be on time"


def shaping(ctx: Ctx, start: int) -> str | None:
    """A fixed item whose end (plus its buffer) is exactly where the block starts."""
    kinds = ctx.settings["event_kinds"]
    for r in rows(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND when_kind = 'fixed' AND end_utc <= ? AND end_utc >= ?",
        [ctx.user_id, format_utc(start), format_utc(start - 120)],
    ):
        if ctx.hidden.calendar(r["id"]):
            continue  # a hidden calendar's events aren't named (planner/hidden.py)
        kind = kinds.get(r["event_kind"] or "other", kinds["other"])
        after = r["buffer_after_min"] if r["buffer_after_min"] is not None else kind.after_min
        if parse_utc(r["end_utc"]) + after == start:
            return f"starts right after {r['title']}" + (f" + {after} min" if after else "")
    return None


@query("why_not")
def why_not(ctx: Ctx, inp: WhyNotInput) -> WhyNotOut:
    """What moving a block (to `start`, or to the cheapest valid place) would cost, or the wall in the way.

    A block under way is what's left of it ahead; with nothing left, while you time it or once its time has gone by,
    `note` says so and what to do."""
    item_id, start = parse_block_key(ctx, inp.key)
    block = find_block(ctx, inp.key)
    end = parse_utc(block["end_utc"])
    target = parse_utc(ctx.utc(inp.start, "start")) if inp.start else None
    nothing = WhyNotOut(key=inp.key, to_start=None, wall=None, difference={}, total=0)
    if end <= ctx.now_utc:
        return nothing.model_copy(update={"note": GONE_BY})
    if start < ctx.now_utc and running(ctx, item_id) is not None:
        return nothing.model_copy(update={"note": TIMING})
    try:
        answer, tried, until = why_not_view(
            take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), item_id, start, target, end
        )
    except UnderWay:
        return nothing.model_copy(update={"note": UNDER_WAY})
    except ValueError as error:
        raise FieldError("start", str(error)) from error
    walls = answer.walls
    if answer.window is not None:  # kept to its own time of day: that time, and what's around it there
        lo, hi = (clock_time(to_local(t, ctx.tz)) if t is not None else None for t in answer.window)
        title = require_item(ctx, item_id).title
        said = f"{title} goes between {lo} and {hi}" if lo else f"{title} goes by {hi}"
        walls = [said + (f", around {and_list(walls)}" if walls else "")]
    return WhyNotOut(
        key=inp.key,
        to_start=ctx.local(format_utc(tried)) if tried is not None else None,
        to_end=ctx.local(format_utc(until)) if until is not None else None,
        wall="; ".join(walls) or None,
        difference=answer.delta,
        total=answer.total,
    )


GONE_BY = "Its time has gone by, so there's nothing of it to move."
UNDER_WAY = "It's under way, so there's nothing of it left to move. Not doing it now? Drag it to a later time."
TIMING = "You're timing it now. Stop the timer, and what's left of it can go elsewhere."


def and_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def change_out(ctx: Ctx, report: dict[str, Any], before: dict[str, int] | None = None) -> ChangeOut:
    # An item the plan placed and you then took back (undo of its add) is gone from the database until the next
    # replan: said as such, not refused (12 Nov: "changes" failed with "That item isn't there any more").
    def title(item_id: int) -> str:
        found = load_item(ctx.conn, item_id, ctx.user_id)
        return found.title if found else "something since taken back"

    return change_list(report, before or {}, ctx.tz, title)


@query("changes")
def changes(ctx: Ctx, inp: Empty) -> ChangeOut:
    """What the latest plan changed, and which commands (and actors) led to it."""
    report = saved_report(ctx)
    previous = one(
        ctx.conn,
        "SELECT report FROM plans WHERE user_id = ? AND id < ? AND status = 'replaced' ORDER BY id DESC LIMIT 1",
        [ctx.user_id, report["plan_id"]],
    )
    before = json.loads(previous["report"]).get("rule_totals", {}) if previous else {}
    return change_out(ctx, report, before)


@query("preview_weights")
def preview_weights(ctx: Ctx, inp: PreviewWeightsInput) -> ChangeOut:
    """A warm run with changed weights, rules switched off or a whole rules list tried instead; saves nothing."""
    before = saved_report(ctx).get("rule_totals", {})
    instead = checked_rules(inp.rules) if inp.rules is not None else None
    preview = run_preview(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), inp.weights, inp.off, instead)
    return change_out(ctx, preview.report, before)


def checked_rules(raw: list[dict[str, Any]]) -> tuple:
    """A rules list validated as settings and built once, so a bad param is a field error, not a failed solve."""
    try:
        specs = validate_value("rules", raw)
        build_rules(r.model_dump(exclude={"enabled"}) for r in specs if r.type in RULE_TYPES)
    except ValueError as error:
        raise FieldError("rules", str(error)) from error
    return specs


@query("rule_totals")
def rule_totals(ctx: Ctx, inp: RuleTotalsInput) -> dict[str, int]:
    """Cost per rule in the current plan, or on one day."""
    report = saved_report(ctx)
    if inp.day is None:
        return report.get("rule_totals", {})
    return report.get("rule_totals_by_day", {}).get(inp.day, {})


def api_input(ctx: Ctx, values: dict[str, Any]) -> dict[str, Any]:
    """A step's input as the API takes it: `due_utc` minutes become a local `due`."""
    return {k.removesuffix("_utc"): ctx.local(format_utc(v)) if k.endswith("_utc") else v for k, v in values.items()}


@query("triage")
def triage(ctx: Ctx, inp: Empty) -> TriageOut:
    """Options when hard work is late or overflowing, each with the late hours it saves."""
    ratings = kv_get(ctx.conn, "event_ratings", {}, ctx.user_id)
    going = frozenset(gone_to_titles(ctx.conn, ctx.user_id))
    _, options = run_triage(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), ratings, going)
    # late now is the plan's, as the Plan page says it; each option is still tried on a quick copy (24 Nov, the
    # agreement check: Triage's own quick plan listed work late the plan didn't)
    _, report = saved_plan(ctx)
    late = {int(k): h for k, h in (report.get("late_hours") or {}).items()}
    todo = {
        r["id"]: r["title"]
        for r in rows(ctx.conn, "SELECT id, title FROM items WHERE user_id = ? AND status = 'todo'", [ctx.user_id])
    }
    return TriageOut(
        late={todo[k]: v for k, v in late.items() if k in todo},
        options=[
            TriageOption(
                action=o.action,
                steps=[TriageStep(command=c, input=api_input(ctx, i)) for c, i in o.steps],
                late_hours_saved=o.hours_saved,
                side_effects=o.side_effects,
                skip_title=o.skip_title,
            )
            for o in options
        ],
    )


@query("lighten")
def lighten(ctx: Ctx, inp: LightenInput) -> LightenOut:
    """Ways to plan less in a week (or a day) that holds more than your usual, each tried on a copy of your plan,
    none making anything late: flexible work there, started after it."""
    options = run_lighten(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), date.fromisoformat(inp.start), inp.days)
    return LightenOut(
        options=[
            LightenOption(
                action=o.action,
                steps=[TriageStep(command=c, input=api_input(ctx, i)) for c, i in o.steps],
                hours_moved=o.hours_moved,
                side_effects=o.side_effects,
            )
            for o in options
        ]
    )
