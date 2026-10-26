"""Replanning and its helpers (DESIGN §15.3): solve, check locks, save; `what_if`; provisional placement."""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace

import numpy as np

from friday.api.types import BlockOut
from friday.core.time import UNIT_MIN, format_local, format_utc, parse_utc, to_local
from friday.engine.construct import prepare_start
from friday.engine.evaluate import evaluate
from friday.engine.executor import provisional_plan
from friday.engine.repair import deadline_value, repair
from friday.engine.scheduler import deadline_fallback
from friday.planner.assemble import AssembledPlan, PlannedBlock, assemble, late_hours, planned_blocks
from friday.planner.build import BuildInput, build_problem, key_of, scheduler_config
from friday.planner.learning import learnable
from friday.planner.prepare import build_input
from friday.planner.snapshot import Snapshot, read_snapshot, take_snapshot
from friday.planner.solve import solve
from friday.planner.store import current_plan

MAX_PIN_CHECKS = 10


def replan(
    conn: sqlite3.Connection,
    now_utc: int,
    user_id: int = 1,
    warm: bool = True,
    reason: str = "replan",
    cancel: np.ndarray | None = None,
) -> int | None:
    """Solve the current state and save the plan; returns its id, or None when a newer plan is already saved."""
    snapshot = take_snapshot(conn, now_utc, user_id)
    assembled = plan_snapshot(snapshot, warm, cancel)
    return save_plan(conn, snapshot, assembled, reason)


def plan_snapshot(snapshot: Snapshot, warm: bool, cancel: np.ndarray | None = None) -> AssembledPlan:
    solved = solve(snapshot, warm, cancel)
    assembled = assemble(snapshot, solved)
    conflicts = lock_conflicts(snapshot, assembled)
    if conflicts:
        assembled.status = "waiting"
        assembled.report["conflicts"] = conflicts
    return assembled


def save_plan(conn: sqlite3.Connection, snapshot: Snapshot, plan: AssembledPlan, reason: str) -> int | None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        saved = current_plan(conn, snapshot.user_id)
        if saved is not None and saved["generation"] > plan.generation:
            conn.execute("ROLLBACK")
            return None
        if plan.status == "current":
            conn.execute(
                "UPDATE plans SET status = 'replaced' WHERE user_id = ? AND status IN ('current', 'waiting')",
                [snapshot.user_id],
            )
            if snapshot.next_stability is not None:
                conn.execute("DELETE FROM kv WHERE user_id = ? AND key = 'next_stability'", [snapshot.user_id])
            if snapshot.cold_once:
                conn.execute("DELETE FROM kv WHERE user_id = ? AND key = 'next_cold'", [snapshot.user_id])
        report = plan.report | {"settings_version": plan.settings_version}
        plan_id = int(
            conn.execute(
                "INSERT INTO plans (user_id, created_utc, generation, reason, status, stage_values, solve_seconds, "
                "report) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    snapshot.user_id,
                    format_utc(snapshot.now_utc),
                    plan.generation,
                    reason,
                    plan.status,
                    json.dumps(plan.stage_values),
                    plan.seconds,
                    json.dumps(report, default=str),
                ],
            ).lastrowid
            or 0
        )
        # A plan waiting on a lock carries them too: accepting it (`resolve`) mustn't lose what was planned earlier.
        past = past_blocks(conn, saved, snapshot.now_utc)
        conn.executemany(
            "INSERT INTO blocks (plan_id, user_id, item_id, start_utc, end_utc, cost, tentative) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    plan_id,
                    snapshot.user_id,
                    b.item_id,
                    format_utc(b.start_utc),
                    format_utc(b.end_utc),
                    json.dumps(b.cost),
                    int(b.tentative),
                )
                for b in joined(past, plan.blocks, snapshot)
            ],
        )
        if plan.status == "current" and saved is not None:
            record_drag(conn, snapshot, json.loads(saved["report"]), report)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    return plan_id


def record_drag(conn: sqlite3.Connection, snapshot: Snapshot, before: dict, after: dict) -> None:
    """A block you moved is a comparison your version won (DESIGN §21.1): the plan with your pin against the plan
    before it, by learnable rule. Not right after a pace or rule change: moves then reflect it, not your taste."""
    moved = any(c["command"] == "pin" and c["actor"] == "you" for c in snapshot.log_since_plan)
    if not moved or snapshot.next_stability is not None:
        return
    scale = snapshot.settings["engine"].scale
    rules = learnable(snapshot.settings)

    def features(report: dict) -> str:
        totals = report.get("rule_totals", {})
        return json.dumps({"rules": {r: totals.get(r, 0) / scale for r in rules}})

    conn.execute(
        "INSERT INTO comparisons (user_id, asked_utc, plan_a, plan_b, features_a, features_b, answer, answered_utc, "
        "source, dials) VALUES (?, ?, '{}', '{}', ?, ?, 'a', ?, 'drag', '{}')",
        [
            snapshot.user_id,
            format_utc(snapshot.now_utc),
            features(after),
            features(before),
            format_utc(snapshot.now_utc),
        ],
    )


def past_blocks(conn: sqlite3.Connection, saved: dict | None, now_utc: int) -> list[PlannedBlock]:
    """The previous plan's blocks from the last two days up to now, cut where the new plan begins (the next
    quarter hour). The review and the assumed-progress rule (§8) still need what was planned earlier."""
    if saved is None:
        return []
    cut = -(-now_utc // UNIT_MIN) * UNIT_MIN
    found = conn.execute(
        "SELECT * FROM blocks WHERE plan_id = ? AND start_utc < ? AND end_utc > ?",
        [saved["id"], format_utc(now_utc), format_utc(now_utc - 2 * 1440)],
    ).fetchall()
    return [
        PlannedBlock(
            r["item_id"],
            parse_utc(r["start_utc"]),
            min(parse_utc(r["end_utc"]), cut),
            json.loads(r["cost"]),
            bool(r["tentative"]),
        )
        for r in found
    ]


def joined(past: list[PlannedBlock], future: list[PlannedBlock], snapshot: Snapshot) -> list[PlannedBlock]:
    """A past block and the new plan's block of the same item that starts where it ends are one block, keyed by
    its first start, so a block carried across replans doesn't break into pieces. A timed past block stays apart:
    its session replaces it in the review, and the rest must still be reviewable (§8 rule 1)."""
    following = {(b.item_id, b.start_utc): b for b in future}
    out, used = [], set()
    for block in past:
        after = following.get((block.item_id, block.end_utc))
        if after is not None and after.tentative == block.tentative and not timed(snapshot, block):
            cost = {k: block.cost.get(k, 0) + after.cost.get(k, 0) for k in block.cost.keys() | after.cost.keys()}
            out.append(replace(block, end_utc=after.end_utc, cost=cost))
            used.add(id(after))
        else:
            out.append(block)
    return out + [b for b in future if id(b) not in used]


def timed(snapshot: Snapshot, block: PlannedBlock) -> bool:
    if snapshot.timer is not None and snapshot.timer[0] == block.item_id:
        return True
    return any(
        r["source"] == "timer"
        and r["start_utc"]
        and parse_utc(r["start_utc"]) < block.end_utc
        and parse_utc(r["end_utc"]) > block.start_utc
        for r in snapshot.progress.get(block.item_id, ())
    )


def quick_late(inp: BuildInput, with_fallback: bool) -> tuple[int, dict[int, float]]:
    """The deadlines value and late hours per hard item after construction, repair and (if asked and lateness is
    left) the fallback. Milliseconds without the fallback."""
    problem = build_problem(inp)
    start = prepare_start(problem)
    config = scheduler_config(inp.settings)
    owner = repair(start.c, start.owner, config.repair_steps, config.sampler.seed, config.sampler.move_weights)
    if with_fallback and deadline_value(start.c, owner) > 0:
        owner, _ = deadline_fallback(start.c, owner, config, np.zeros(1, dtype=np.int64), "what_if", warm=True)
    plan = start.c.plan_from_owner(owner)
    return deadline_value(start.c, owner), late_hours(problem, plan, evaluate(problem, plan).over_units)


def what_if(
    inp: BuildInput, change: Callable[[BuildInput], BuildInput], with_fallback: bool = False
) -> dict[int, float]:
    """Extra late hours per item if `change` were applied; writes nothing (§15.3)."""
    _, before = quick_late(inp, with_fallback)
    _, after = quick_late(change(inp), with_fallback)
    extra = {k: round(after.get(k, 0.0) - before.get(k, 0.0), 2) for k in set(before) | set(after)}
    return {k: v for k, v in extra.items() if v > 0}


def with_pins_preferred(pin_ids: set[int] | None) -> Callable[[BuildInput], BuildInput]:
    """A change turning these locked pins (every lock when None) into preferred ones."""

    def change(inp: BuildInput) -> BuildInput:
        pins = [
            replace(p, kind="preferred") if p.kind == "locked" and (pin_ids is None or p.created in pin_ids) else p
            for p in inp.pins
        ]
        return replace(inp, pins=pins)

    return change


def lock_conflicts(snapshot: Snapshot, plan: AssembledPlan) -> list[dict]:
    """Locked pins that make hard work late (§15.3 step 4). Only checked when something is late at all."""
    locked = [p for p in snapshot.pins if p.kind == "locked"]
    if not locked or plan.stage_values["deadlines"] == 0:
        return []
    inp = build_input(snapshot)
    points, hours = quick_late(inp, with_fallback=False)
    freed_points, _ = quick_late(with_pins_preferred(None)(inp), with_fallback=False)
    if points - freed_points <= snapshot.settings["planner"].lock_conflict_tolerance:
        return []
    titles = {i.id: i.title for i in snapshot.items}
    out = []
    for pin in locked[:MAX_PIN_CHECKS]:
        _, without = quick_late(with_pins_preferred({pin.id})(inp), with_fallback=False)
        saved = sum(hours.values()) - sum(without.values())
        if saved > 0:
            out.append(
                {
                    "pin_id": pin.id,
                    "item_id": pin.item_id,
                    "title": titles.get(pin.item_id, ""),
                    "start": format_utc(pin.start_utc),
                    "extra_late_hours": round(saved, 2),
                }
            )
    return out


def provisional(conn: sqlite3.Connection, now_utc: int, user_id: int, changed: set[int]) -> list[BlockOut] | None:
    """The executor's quick placement after a command, inside its transaction (§14.6); None until set up."""
    snapshot = read_snapshot(conn, now_utc, user_id)
    if snapshot.settings["time"].timezone is None or snapshot.settings["sleep"] is None:
        return None
    inp = build_input(snapshot)
    problem = build_problem(inp)
    grid = problem.grid
    previous: dict[str, list[int]] = {}
    for block in snapshot.plan_blocks:
        if key_of(block.item_id) in problem.items:
            previous.setdefault(key_of(block.item_id), []).extend(grid.slots_in(block.start_utc, block.end_utc))
    plan = provisional_plan(problem, {k: tuple(v) for k, v in previous.items()}, {key_of(i) for i in changed})
    blocks, _ = planned_blocks(problem, plan)
    titles = {i.id: i.title for i in snapshot.items}
    return [block_out(snapshot.settings, b, titles.get(b.item_id, "")) for b in blocks]


def block_out(settings: dict, block: PlannedBlock, title: str) -> BlockOut:
    tz = settings["time"].timezone
    start, end = format_local(to_local(block.start_utc, tz)), format_local(to_local(block.end_utc, tz))
    return BlockOut(
        key=f"T{block.item_id}@{start}",
        item_id=block.item_id,
        title=title,
        start=start,
        end=end,
        pinned=block.pinned,
        tentative=block.tentative,
        cost=block.cost,
    )  # type: ignore[arg-type]
