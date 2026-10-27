"""A solved plan → blocks, costs, the change list and the report (DESIGN §15.3 step 3). Pure data out, so the
worker can hand it back across processes and the API process only has to save it."""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from friday.core.pace import DayScales, dials_on, pace_label
from friday.core.textnorm import course_tag
from friday.core.time import (
    UNIT_MIN,
    ampm,
    format_utc,
    local_midnight,
    planning_date,
    planning_day_start_utc,
    to_local,
    to_utc,
)
from friday.engine.executor import slack
from friday.engine.explain import block_costs, blocks_of
from friday.engine.problem import FixedOcc, Plan, Problem
from friday.engine.rules import RULE_TYPES
from friday.engine.rules.prices import BeforeEvent, Skippable, titled
from friday.planner.build import PLANNER_RULES, id_of, key_of
from friday.planner.snapshot import BlockRow, Snapshot
from friday.planner.solve import Solved


@dataclass(frozen=True)
class PlannedBlock:
    item_id: int
    start_utc: int
    end_utc: int
    cost: dict[str, int]
    tentative: bool = False
    pinned: str | None = None  # preferred | locked


@dataclass
class AssembledPlan:
    generation: int
    settings_version: int
    blocks: list[PlannedBlock]
    stage_values: dict[str, int]
    report: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    status: str = "current"  # plans from before 27 Oct may be "waiting" (on a lock); none waits now


def pin_edges(problem: Problem) -> dict[str, set[int]]:
    """Slots where a block must start so pinned blocks stay whole."""
    edges: dict[str, set[int]] = {}
    for item in problem.items.values():
        for pinned in (item.locked, item.preferred):
            for s in pinned:
                if s - 1 not in pinned:
                    edges.setdefault(item.key, set()).add(s)
                if s + 1 not in pinned:
                    edges.setdefault(item.key, set()).add(s + 1)
    return edges


def planned_blocks(problem: Problem, plan: Plan, priced: bool = True) -> tuple[list[PlannedBlock], dict[str, int]]:
    """The plan's blocks; `priced`, with each block's cost by rule (half of a quick placement's time went on pricing
    blocks nobody reads, 27 Oct)."""
    blocks = blocks_of(plan, pin_edges(problem))
    costs, other = block_costs(problem, plan, blocks) if priced else ([{} for _ in blocks], {})
    grid = problem.grid
    out = []
    for block, cost in zip(blocks, costs, strict=True):
        item = problem.items[block.key]
        slots = set(block.slots)
        pinned = "locked" if slots <= item.locked else "preferred" if slots <= item.preferred else None
        out.append(
            PlannedBlock(
                id_of(block.key),
                int(grid.start[block.slots[0]]),
                int(grid.end[block.slots[-1]]),
                cost,
                item.tentative,
                pinned,
            )
        )
    return out, other


def late_hours(problem: Problem, plan: Plan, over_units: dict[str, int]) -> dict[int, float]:
    """Hours each hard item finishes after its due, overflow counted as late."""
    grid, out = problem.grid, {}
    for item in problem.items.values():
        if item.firmness != "hard" or item.due_utc is None or item.amount != "fixed":
            continue
        slots = plan.get(item.key, ())
        hours = max(0.0, (int(grid.end[slots[-1]]) - item.due_utc) / 60) if slots else 0.0
        if item.due_utc <= grid.horizon_end:  # work on a later due waits for its weeks; it isn't late
            hours += over_units.get(item.key, 0) * UNIT_MIN / 60
        if hours > 0:
            out[id_of(item.key)] = round(hours, 2)
    return out


def assemble(snapshot: Snapshot, solved: Solved) -> AssembledPlan:
    problem, result = solved.problem, solved.result
    blocks, other = planned_blocks(problem, result.plan)
    evaluation = result.evaluation
    report = {
        "stage_values": evaluation.stage_values,
        "rule_totals": evaluation.rule_totals,
        "rule_totals_by_day": totals_by_day(problem, blocks, other),
        "overflow_hours": {id_of(k): v * UNIT_MIN / 60 for k, v in evaluation.over_units.items() if v},
        "late_hours": late_hours(problem, result.plan, evaluation.over_units),
        "notices": notices(problem, result.demoted_locks)
        + clashes(problem, snapshot.settings["time"].timezone)
        + given_way(problem, blocks, snapshot.settings["time"].timezone, snapshot.now_utc)
        + missing_rule_types(snapshot),
        "changes": changes(snapshot, problem, blocks),
        "solve": {
            "fallback": result.fallback,
            "seconds": result.seconds,
            "steps": result.steps_per_chain,
            "chains": result.chains,
            "cancelled": result.cancelled,
        },
        "quotas": {id_of(k): v for k, v in solved.allocation.quotas.items()},
        "allocation_hours": [round(units * UNIT_MIN / 60, 2) for units in solved.allocation.day_totals()],
        "allocation_capacity_hours": [round(units * UNIT_MIN / 60, 2) for units in solved.allocation.capacity],
        "allocation_start": problem.grid.slots[0].date.isoformat(),
        "allocation_finish": allocation_finish(solved),
        "slack_minutes": {id_of(k): s.minutes for k, s in slack(solved.executor).items()},
        "pace": pace_days(snapshot, problem),
        "pace_notices": pace_notices(snapshot, problem, blocks),
        "last_command_id": snapshot.last_command_id,
        "profile_version": snapshot.profile_version,
    }
    return AssembledPlan(
        snapshot.generation,
        snapshot.settings_version,
        blocks,
        evaluation.stage_values,
        report,
        result.seconds.get("total", 0.0),
    )


def allocation_finish(solved: Solved) -> dict[int, int]:
    """The last day (from the allocation's first) each item has work on, for "planned finish" past the horizon."""
    out = {}
    for key, units in solved.allocation.units.items():
        days = [d for d, u in enumerate(units) if u > 0.01]
        if days:
            out[id_of(key)] = days[-1]
    return out


def totals_by_day(problem: Problem, blocks: list[PlannedBlock], other: dict[str, int]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for block in blocks:
        s = problem.grid.slot_at(block.start_utc)
        day = problem.grid.slots[s].date.isoformat()
        for rule, cost in block.cost.items():
            out.setdefault(day, {})[rule] = out.get(day, {}).get(rule, 0) + cost
    if other:
        out["other"] = dict(other)
    return out


def notices(problem: Problem, demoted: list[str]) -> list[str]:
    """What the plan couldn't do as asked. Late work has its own line in the app (`status.late`), from late_hours."""
    tz = problem.grid.spec.timezone
    over = [
        f"Your lock on {problem.items[k].title} ({to_local(at, tz):%a} {ampm(to_local(at, tz))}) is during {event}, "
        f"so Friday planned it elsewhere: move the lock, or make {event} optional"
        for k, event, at in problem.locks_over_events
        if k in problem.items
    ]
    return over + [f"A lock on {problem.items[k].title} couldn't be kept and became a preferred pin" for k in demoted]


def clashes(problem: Problem, tz: str) -> list[str]:
    """Events at the same time, like a prelim during a lab: one has to give, and only you can say which."""
    events = sorted((f for f in problem.fixed if f.blocks_time and f.kind != "shove"), key=lambda f: f.start_utc)
    out = []
    for n, a in enumerate(events):
        for b in events[n + 1 :]:
            if b.start_utc >= a.end_utc:
                break
            if b.title != a.title and not in_class_exam(a, b):
                when = to_local(max(a.start_utc, b.start_utc), tz)
                out.append(f"{a.title} and {b.title} overlap on {when:%a %b} {when.day} at {ampm(when)}")
    return out


GO_DAYS = 7  # "go" is said for the coming week's events: further out, the plan will still change


def given_way(problem: Problem, blocks: list[PlannedBlock], tz: str, now: int) -> list[str]:
    """Optional events the plan uses the time of (`skippable`), or the night before of (a night-before rule's night
    the plan lifted: planner/solve.py), because the work wouldn't fit otherwise: skip; and the coming week's events you
    go to only when you're ahead (`ahead`) whose time and night the plan leaves free: go."""
    ahead = {
        (f.title, f.start_utc)
        for r in problem.rules
        if isinstance(r, Skippable) and r.p.ahead
        for f in titled(problem, r.p.titles)
    }
    nights = lifted_nights(problem)
    out = []
    for event in sorted((f for f in problem.fixed if f.skippable), key=lambda f: f.start_utc):
        over = [b for b in blocks if b.start_utc < event.end_utc and b.end_utc > event.start_utc]
        night = nights.get((event.title, event.start_utc))
        late = [b for b in blocks if night and b.start_utc < night[1] and b.end_utc > night[0]]
        when = to_local(event.start_utc, tz)
        if over or late:
            work = problem.items.get(key_of((over or late)[0].item_id))
            needs = work.title if work else "work"
            eve = to_local(night[0], tz) if night else when
            said = "the time" if over else f"{eve:%A} night"
            out.append(f"Skip {event.title} on {when:%a} at {ampm(when)}: {needs} needs {said}")
        elif (event.title, event.start_utc) in ahead and now <= event.start_utc < now + GO_DAYS * 1440:
            out.append(f"Go to {event.title} on {when:%a} at {ampm(when)}: you’re ahead")
    return out


def lifted_nights(problem: Problem) -> dict[tuple[str, int], tuple[int, int]]:
    """The optional events whose night before the plan was free to use (a night-before rule's `skip_days`), and that
    night: from the rule's hour until the event's day starts, in UTC minutes."""
    spec = problem.grid.spec
    out = {}
    for rule in problem.rules:
        if not isinstance(rule, BeforeEvent) or not rule.p.skip_days:
            continue
        days = {date.fromisoformat(d) for d in rule.p.skip_days}
        for f in titled(problem, rule.p.titles):
            day = planning_date(f.start_utc, spec.timezone, spec.day_start)
            if day in days:
                eve = day - timedelta(days=1)
                after = rule.p.after + (1440 if rule.p.after < spec.day_start else 0)
                start = to_utc(local_midnight(eve) + timedelta(minutes=after), spec.timezone)
                out[(f.title, f.start_utc)] = (start, planning_day_start_utc(day, spec.timezone, spec.day_start))
    return out


def in_class_exam(a: FixedOcc, b: FixedOcc) -> bool:
    """A midterm in its own lecture's time replaces the lecture; that isn't a clash to point out."""
    course = course_tag(a.title, [])
    return "exam" in (a.kind, b.kind) and course is not None and course == course_tag(b.title, [])


def missing_rule_types(snapshot: Snapshot) -> list[str]:
    return [
        f"Rule {r.name} is off: no rule type {r.type!r} is loaded"
        for r in snapshot.settings["rules"]
        if r.type not in RULE_TYPES and r.type not in PLANNER_RULES
    ]


def changes(snapshot: Snapshot, problem: Problem, blocks: list[PlannedBlock]) -> dict[str, Any]:
    """Added, moved and removed work against the previous plan's future blocks. Open items fill whatever is left,
    so their moves aren't news and aren't listed."""
    is_open = {id_of(k) for k, item in problem.items.items() if item.amount == "open"}
    before = per_item(b for b in snapshot.plan_blocks if b.end_utc > snapshot.now_utc and b.item_id not in is_open)
    after = per_item(BlockRow(b.item_id, b.start_utc, b.end_utc) for b in blocks if b.item_id not in is_open)
    out: dict[str, Any] = {"added": [], "moved": [], "removed": []}
    for item_id in sorted(set(before) | set(after)):
        old, new = before.get(item_id, []), after.get(item_id, [])
        if old == new:
            continue
        kind = "added" if not old else "removed" if not new else "moved"
        out[kind].append({"item_id": item_id, "before": spans(old), "after": spans(new)})
    out["inputs"] = [
        {"command_id": r["id"], "actor": r["actor"], "command": r["command"], "input": r["input"]}
        for r in snapshot.log_since_plan
    ]
    return out


def per_item(blocks: Any) -> dict[int, list[tuple[int, int]]]:
    out: dict[int, list[tuple[int, int]]] = {}
    for b in blocks:
        out.setdefault(b.item_id, []).append((b.start_utc, b.end_utc))
    return {k: sorted(v) for k, v in out.items()}


def spans(found: list[tuple[int, int]]) -> list[list[str]]:
    return [[format_utc(a), format_utc(b)] for a, b in found]


def pace_days(snapshot: Snapshot, problem: Problem) -> dict[str, str]:
    settings = snapshot.settings
    out = {}
    for day in problem.grid.day_date:
        dials = dials_on(
            day, list(snapshot.pace_periods), settings["paces"], settings["pace"].default, settings["pace"].weekly
        )
        out[day.isoformat()] = pace_label(dials, settings["paces"])
    return out


def pace_notices(snapshot: Snapshot, problem: Problem, blocks: list[PlannedBlock]) -> list[str]:
    """Days off the default pace where hard deadlines force more work than the day's dialled-down load limit."""
    threshold = next((r.p.threshold for r in problem.rules if r.type == "daily_load"), None)
    default = snapshot.settings["pace"].default
    labels = pace_days(snapshot, problem)
    out = []
    for d, day in enumerate(problem.grid.day_date):
        if threshold is None or labels[day.isoformat()] == default:
            continue
        scales: DayScales = problem.scales[d]
        limit = threshold * scales.daily_load_threshold * UNIT_MIN / 60
        hard = [b for b in blocks if day_index(problem, b) == d and item_of(problem, b).firmness == "hard"]
        hours = sum(b.end_utc - b.start_utc for b in hard) / 60
        if hours > limit:
            due = sorted({item_of(problem, b).title for b in hard})
            out.append(
                f"{labels[day.isoformat()]} pace can't keep {day:%a} under {limit:.1f} h: "
                f"{' and '.join(due)} {'is' if len(due) == 1 else 'are'} due"
            )
    return out


def item_of(problem: Problem, block: PlannedBlock) -> Any:
    return problem.items[key_of(block.item_id)]


def day_index(problem: Problem, block: PlannedBlock) -> int:
    return problem.grid.slots[problem.grid.slot_at(block.start_utc)].day
