"""Planner side of learning (DESIGN §21): which rules are learned, and versions of a coming day to compare.

A comparison shows two versions of one day. Versions are the current plan and samples drawn near it at a fixed
temperature (§11.13), so both are realistic. Each carries that day's per-rule totals (the features θ weighs) and,
for missing-rule detection, its hours inside each rule template.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from friday.core.time import format_local, to_local
from friday.engine.construct import prepare_start
from friday.engine.problem import NEVER_LEARNED
from friday.engine.sampler import sample
from friday.engine.scheduler import current_owner
from friday.learn.proposals import template_features
from friday.planner.assemble import PlannedBlock, planned_blocks, totals_by_day
from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.snapshot import Snapshot

# Stability is the planner's own concern, not a taste; travel time around events isn't weighed at all.
NOT_LEARNED = NEVER_LEARNED | {"minimize_changes", "travel"}
SAMPLE_STEPS = 20_000
SAMPLE_TEMPERATURE = 1.0  # × the median move: plans a user could plausibly prefer either way


def learnable(settings: dict[str, Any]) -> tuple[str, ...]:
    return tuple(r.name for r in settings["rules"] if r.type not in NOT_LEARNED)


@dataclass
class DayVersion:
    blocks: list[dict[str, Any]]  # that day's blocks: item_id, title, start, end (local)
    features: dict[str, float]  # per learnable rule, points on that day
    templates: dict[str, float]  # hours inside each rule template (learn/proposals.py)


def day_versions(snapshot: Snapshot, day: date, n: int = 6, seed: int = 0) -> list[DayVersion]:
    """The current plan's version of `day` and up to `n` sampled ones that differ from it."""
    problem = build_problem(build_input(snapshot))
    start = prepare_start(problem, current_owner(problem))
    owners = [start.owner] + [
        sample(
            start.c, start.owner, SAMPLE_TEMPERATURE, SAMPLE_STEPS, seed + k, snapshot.settings["engine"].move_weights
        )
        for k in range(n)
    ]
    rules = learnable(snapshot.settings)
    tz = snapshot.settings["time"].timezone
    titles = {item.id: item.title for item in snapshot.items}
    energy = {item.id: item.energy for item in snapshot.items}
    out, seen = [], set()
    for owner in owners:
        blocks, other = planned_blocks(problem, start.c.plan_from_owner(owner))
        on_day = [b for b in blocks if problem.grid.slots[problem.grid.slot_at(b.start_utc)].date == day]
        shape = tuple((b.item_id, b.start_utc, b.end_utc) for b in on_day)
        if shape in seen:
            continue
        seen.add(shape)
        totals = totals_by_day(problem, blocks, other).get(day.isoformat(), {})
        out.append(
            DayVersion(
                [view(b, titles, tz) for b in on_day],
                {r: totals.get(r, 0) / problem.scale for r in rules},
                template_features(
                    [(local(b.start_utc, tz), local(b.end_utc, tz), energy.get(b.item_id)) for b in on_day]
                ),
            )
        )
    return out


def local(minutes: int, tz: str) -> datetime:
    return to_local(minutes, tz).replace(tzinfo=None)


def view(block: PlannedBlock, titles: dict[int | None, str], tz: str) -> dict[str, Any]:
    return {
        "item_id": block.item_id,
        "title": titles.get(block.item_id, f"T{block.item_id}"),
        "start": format_local(to_local(block.start_utc, tz)),
        "end": format_local(to_local(block.end_utc, tz)),
    }
