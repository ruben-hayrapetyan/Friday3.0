"""Other ways to plan the same work (personal's three options, COMBINED.md 25): asked for on demand beside m16's live
plan. Each way is described by how it differs from your plan, rule by rule; picking one makes it your plan (the next
replan starts afresh with its weights, for a week) and counts as a comparison your pick won, which is how Friday
learns what you like (DESIGN §21)."""

import json

from friday.api.commands import Changed, OneWayOut, OtherWay, OtherWayInput, OtherWayPickInput, OtherWaysOut
from friday.api.types import Empty
from friday.commands.fields import require_item
from friday.commands.queries import block_out
from friday.commands.registry import Ctx, command, query
from friday.core.time import format_utc, parse_utc
from friday.planner.assemble import AssembledPlan
from friday.planner.learning import learnable
from friday.planner.snapshot import take_snapshot
from friday.planner.store import current_plan, kv_get
from friday.planner.views import WAY_TRIES, signature
from friday.planner.views import other_way as find_way
from friday.planner.views import other_ways as find_ways

PICK_DAYS = 7
WAYS = 2  # ways shown


@query("other_ways")
def other_ways(ctx: Ctx, inp: Empty) -> OtherWaysOut:
    """Two other ways to plan what you have, each made afresh; nothing is saved."""
    current = current_totals(ctx)
    found = find_ways(take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id))
    return OtherWaysOut(current=current, ways=[way_out(ctx, current, w, seed, plan) for w, seed, plan in found])


@query("other_way")
def other_way(ctx: Ctx, inp: OtherWayInput) -> OneWayOut:
    """One other way to plan what you have, made afresh with seed `seed` (none when it came out as your plan); the
    app asks for them one at a time and keeps the first two unlike each other."""
    snapshot = take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id)
    weights, plan = find_way(snapshot, inp.seed)
    yours = signature(plan.blocks) == signature(snapshot.plan_blocks)
    way = None if yours else way_out(ctx, current_totals(ctx), weights, inp.seed, plan)
    return OneWayOut(way=way, tries=WAY_TRIES, wanted=WAYS)


def current_totals(ctx: Ctx) -> dict[str, int]:
    saved = current_plan(ctx.conn, ctx.user_id)
    return json.loads(saved["report"]).get("rule_totals", {}) if saved else {}


def way_out(ctx: Ctx, current: dict[str, int], weights: dict[str, float], seed: int, plan: AssembledPlan) -> OtherWay:
    totals = plan.report.get("rule_totals", {})
    late = plan.report.get("late_hours", {})
    return OtherWay(
        weights=weights,
        seed=seed,
        summary=difference(current, totals, learnable(ctx.settings)),
        blocks=[block_out(ctx, b.item_id, b.start_utc, b.end_utc) for b in plan.blocks],
        hours=round(sum(b.end_utc - b.start_utc for b in plan.blocks) / 60, 1),
        sessions=len(plan.blocks),
        late={require_item(ctx, int(k)).title: v for k, v in late.items()},
        rule_totals=totals,
        signature=signature(plan.blocks),
    )


# What a way gains or gives up by each rule (personal's PHRASES): costing less, then costing more.
PHRASES = {
    "late_night": ("less late-night work", "more late-night work"),
    "deep_run": ("shorter stretches of focus", "longer stretches of focus"),
    "weekday_evenings": ("freer weekday evenings", "busier weekday evenings"),
    "weekends": ("freer weekends", "busier weekends"),
    "daily_load": ("lighter days", "heavier days"),
    "even_load": ("work spread more evenly", "work bunched up"),
    "energy": ("more work in your best hours", "less work in your best hours"),
    "chunk_cost": ("fewer, longer sittings", "more, shorter sittings"),
    "buffer": ("more room between blocks", "less room between blocks"),
    "spread": ("spread-out work spread out more", "spread-out work bunched"),
    "cluster": ("clustered work on fewer days", "clustered work on more days"),
    "target_shortfall": ("more of your weekly targets", "less of your weekly targets"),
    "elastic_shortfall": ("routines nearer their ideal", "routines cut shorter"),
    "elastic_minimum": ("meals kept", "meals cut"),
    "open_value": ("more time for side projects", "less time for side projects"),
    "finish_early": ("work finished sooner before it's due", "work finished closer to its due"),
    "soft_late": ("soft deadlines kept better", "soft deadlines slipping"),
    "unscheduled": ("more undated work done", "less undated work done"),
    "minimize_changes": ("closer to the plan you have", "further from the plan you have"),
}


def difference(current: dict[str, int], other: dict[str, int], rules: tuple[str, ...]) -> str:
    """What a way gains and gives up against your plan: the two rules it changes most each way, in words."""
    changes = sorted(((other.get(r, 0) - current.get(r, 0), r) for r in rules if r in PHRASES), key=lambda c: c[0])
    gains = [PHRASES[r][0] for d, r in changes if d < 0][:2]
    costs = [PHRASES[r][1] for d, r in reversed(changes) if d > 0][:2]
    if not gains and not costs:
        return "Much the same, arranged differently"
    text = ", ".join(gains) if gains else "Arranged differently"
    text = text[0].upper() + text[1:]
    return f"{text}; but {' and '.join(costs)}" if costs else text


@command("other_way_pick", affects_plan=True)
def other_way_pick(ctx: Ctx, inp: OtherWayPickInput) -> Changed:
    """Make another way your plan, and learn from the pick."""
    until = format_utc(ctx.now_utc + PICK_DAYS * 1440)
    weights, seed = dict(inp.weights), inp.seed
    before = kv_get(ctx.conn, "other_way", None, ctx.user_id)
    if before and parse_utc(before["until"]) > ctx.now_utc:
        # The ways were made on top of the pick still in force, so this one is both: kept, it plans as shown.
        old = before["weights"]
        weights = {r: old.get(r, 1.0) * inp.weights.get(r, 1.0) for r in {*old, *inp.weights}}
        seed += before.get("seed", 0)
    ctx.db.upsert(
        "kv",
        {"user_id": ctx.user_id, "key": "other_way"},
        {"value": json.dumps({"weights": weights, "seed": seed, "until": until})},
    )
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "next_cold"}, {"value": json.dumps(True)})
    saved = current_plan(ctx.conn, ctx.user_id)
    current = json.loads(saved["report"]).get("rule_totals", {}) if saved else {}
    scale = ctx.settings["engine"].scale
    rules = learnable(ctx.settings)

    def features(totals: dict[str, int]) -> str:
        return json.dumps({"rules": {r: totals.get(r, 0) / scale for r in rules}})

    ctx.db.insert(
        "comparisons",
        {
            "asked_utc": ctx.now_text,
            "plan_a": "{}",
            "plan_b": "{}",
            "features_a": features(inp.rule_totals),
            "features_b": features(current),
            "answer": "a",
            "answered_utc": ctx.now_text,
            "source": "question",
            "dials": "{}",
        },
    )
    return Changed(message="That's your plan now")
