"""Explanations and triage (DESIGN §16): why, why_not, changes, preview_weights, rule_totals, triage."""

import json
from typing import Any

from friday.api.commands import (
    BlockRef,
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
from friday.commands.progress import parse_block_key
from friday.commands.registry import Ctx, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.settings import validate_value
from friday.core.time import ampm, format_utc, parse_utc, to_local
from friday.engine.rules import RULE_TYPES, build_rules
from friday.planner.snapshot import take_snapshot
from friday.planner.spacing import Closer, closer_words
from friday.planner.store import current_plan, kv_get
from friday.planner.views import change_list, why_not_view
from friday.planner.views import preview_weights as run_preview
from friday.planner.views import triage as run_triage


def saved_report(ctx: Ctx) -> dict[str, Any]:
    saved = current_plan(ctx.conn, ctx.user_id)
    if saved is None:
        raise FieldError("plan", "there's no plan yet; run `replan`")
    return json.loads(saved["report"]) | {"plan_id": saved["id"]}


def find_block(ctx: Ctx, key: str) -> dict[str, Any]:
    item_id, start = parse_block_key(ctx, key)
    saved = current_plan(ctx.conn, ctx.user_id)
    found = one(
        ctx.conn,
        "SELECT * FROM blocks WHERE plan_id = ? AND item_id = ? AND start_utc = ?",
        [saved["id"] if saved else -1, item_id, format_utc(start)],
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
        due = f"Due {due_at:%a %-d %b} {ampm(due_at)}"
        parts.append(f"{due}; {room(slack)}" if slack is not None else due)
    start, end = block["start_utc"], block["end_utc"]
    pinned = one(
        ctx.conn, "SELECT kind FROM pins WHERE item_id = ? AND start_utc < ? AND end_utc > ?", [item.id, end, start]
    )
    if pinned:
        parts.append("You pinned it here")
    if spaced := report.get("spacing_closer", {}).get(str(item.id)):
        parts.append(closer_words(Closer(**spaced)))
    reasons = {r.name: r.reason or r.name for r in ctx.settings["rules"]}
    top = sorted(((name, cost) for name, cost in costs.items() if cost), key=lambda nc: -nc[1])[:2]
    parts += [f"costs {cost / 100:.1f} for {reasons.get(name, name).replace('_', ' ')}" for name, cost in top]
    shaped = shaping(ctx, parse_utc(start))
    if shaped:
        parts.append(shaped)
    day = start[:10]
    label = report.get("pace", {}).get(day)
    if label and label != ctx.settings["pace"].default:
        parts.append(f"{label} pace that day")
    return ". ".join(p[0].upper() + p[1:] for p in parts) + "." if parts else "Nothing in particular shaped it."


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
        kind = kinds.get(r["event_kind"] or "other", kinds["other"])
        after = r["buffer_after_min"] if r["buffer_after_min"] is not None else kind.after_min
        if parse_utc(r["end_utc"]) + after == start:
            return f"starts right after {r['title']}" + (f" + {after} min" if after else "")
    return None


@query("why_not")
def why_not(ctx: Ctx, inp: WhyNotInput) -> WhyNotOut:
    """What moving a block (to `start`, or to the cheapest valid place) would cost, or the wall in the way."""
    item_id, start = parse_block_key(ctx, inp.key)
    find_block(ctx, inp.key)
    target = parse_utc(ctx.utc(inp.start, "start")) if inp.start else None
    try:
        answer, tried = why_not_view(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), item_id, start, target)
    except ValueError as error:
        raise FieldError("start", str(error)) from error
    return WhyNotOut(
        key=inp.key,
        to_start=ctx.local(format_utc(tried)) if tried is not None else None,
        wall="; ".join(answer.walls) or None,
        difference=answer.delta,
        total=answer.total,
    )


def change_out(ctx: Ctx, report: dict[str, Any], before: dict[str, int] | None = None) -> ChangeOut:
    return change_list(report, before or {}, ctx.tz, lambda item_id: require_item(ctx, item_id).title)


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
    going = frozenset(kv_get(ctx.conn, "events_going", [], ctx.user_id))
    late, options = run_triage(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id), ratings, going)
    titles = {item_id: require_item(ctx, item_id).title for item_id in late}
    return TriageOut(
        late={titles[k]: v for k, v in late.items()},
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
