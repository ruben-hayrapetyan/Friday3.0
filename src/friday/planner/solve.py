"""One solve, from a snapshot to a plan (DESIGN §15.3 step 2). This is what the worker process runs.

Build, allocate and attach quotas, ask the executor whether the hard deadlines can all be met, then schedule. An
optional event with a night-before rule ("climbing club only if I'm ahead", "no work after 10pm the night before
climbing club") is one Friday decides to skip or go to: skipping frees both its time and the night before. The first
plan keeps every such night as if you're going; when it gives an event's time to work, or work is late anyway, those
nights are lifted and the plan made once more from it, kept when it's no later and no harder on you. Then each lifted
event whose time or night before the plan uses is one you skip (assemble says so); one it uses neither of, you go to,
and its night was kept after all. Lifting a night only when the event's own time was used had left the night ended
at 10pm before a club the plan already skipped.
"""

import dataclasses
from dataclasses import dataclass
from datetime import date

import numpy as np

from friday.core.time import planning_date
from friday.engine.allocator import Allocation, allocate, apply_quotas
from friday.engine.executor import ExecutorInput, edf
from friday.engine.problem import Plan, Problem
from friday.engine.rules.prices import BeforeEvent, titled
from friday.engine.scheduler import Schedule, schedule
from friday.planner.build import BuildInput, build_problem, scheduler_config
from friday.planner.inputs import allocator_input, executor_input
from friday.planner.prepare import build_input
from friday.planner.snapshot import Snapshot


@dataclass
class Solved:
    inp: BuildInput
    problem: Problem
    allocation: Allocation
    executor: ExecutorInput
    overloaded: bool
    result: Schedule


def prepared_problem(snapshot: Snapshot) -> tuple[BuildInput, Problem, Allocation]:
    inp = build_input(snapshot)
    problem = build_problem(inp)
    allocation = allocate(allocator_input(inp, problem))
    apply_quotas(problem.items.values(), allocation, problem.grid.horizon_end, problem.grid.units)
    return inp, problem, allocation


def solve(snapshot: Snapshot, warm: bool, cancel: np.ndarray | None = None, threads: int | None = None) -> Solved:
    inp, problem, allocation = prepared_problem(snapshot)
    deadlines = executor_input(inp, problem)
    overloaded = not edf(deadlines.jobs, deadlines.free).feasible
    config = scheduler_config(snapshot.settings, threads)
    warm = warm and bool(snapshot.plan_blocks) and not snapshot.cold_once
    # A way you picked (`cold_once`) is a plan made afresh on purpose: the one you had doesn't stand against it.
    result = schedule(problem, config, warm=warm, cancel=cancel, overloaded=overloaded, keep=not snapshot.cold_once)
    lifted = not_gone_to(problem, result.plan)
    if result.stage_values["deadlines"] > 0:  # late anyway: any of those nights may be what the work needs
        for name, days in optional_nights(problem).items():
            lifted.setdefault(name, set()).update(days)
    if lifted and not (cancel is not None and cancel[0]):
        inp2 = dataclasses.replace(
            inp, settings=inp.settings | {"rules": with_skip_days(inp.settings["rules"], lifted)}
        )
        problem2 = build_problem(inp2)
        apply_quotas(problem2.items.values(), allocation, problem2.grid.horizon_end, problem2.grid.units)
        for key, item in problem2.items.items():  # from this plan, not the last saved one
            item.current = frozenset(result.plan.get(key, ())) | item.preferred
        # From the first pass's plan, only those nights change: an anneal finds it; another deadline search (seconds
        # of CP-SAT on a big week) bought nothing the first hadn't.
        quick = dataclasses.replace(config, use_fallback=False)
        again = schedule(problem2, quick, warm=True, cancel=cancel, overloaded=overloaded)
        better = [again.stage_values[s] for s in ("deadlines", "wellbeing")]
        if better <= [result.stage_values[s] for s in ("deadlines", "wellbeing")]:
            return Solved(inp2, problem2, allocation, deadlines, overloaded, again)
    return Solved(inp, problem, allocation, deadlines, overloaded, result)


def worked(plan: Plan) -> set[int]:
    return {s for slots in plan.values() for s in slots}


def not_gone_to(problem: Problem, plan: Plan) -> dict[str, set[date]]:
    """Per night-before rule, the days of its optional events whose time the plan gives to work."""
    spec, used = problem.grid.spec, worked(plan)
    out: dict[str, set[date]] = {}
    for rule in problem.rules:
        if not isinstance(rule, BeforeEvent):
            continue
        for f in titled(problem, rule.p.titles):
            if f.skippable and used & set(problem.grid.slots_in(f.start_utc, f.end_utc)):
                out.setdefault(rule.name, set()).add(planning_date(f.start_utc, spec.timezone, spec.day_start))
    return out


def with_skip_days(rules: tuple, lifted: dict[str, set[date]]) -> tuple:
    return tuple(
        r.model_copy(update={"params": r.params | {"skip_days": sorted(d.isoformat() for d in lifted[r.name])}})
        if r.name in lifted
        else r
        for r in rules
    )


def optional_nights(problem: Problem) -> dict[str, set[date]]:
    """Per night-before rule, the days of its optional events in the plan's range: each one Friday may skip."""
    spec = problem.grid.spec
    out: dict[str, set[date]] = {}
    for rule in problem.rules:
        if isinstance(rule, BeforeEvent):
            for f in titled(problem, rule.p.titles):
                if f.skippable:
                    out.setdefault(rule.name, set()).add(planning_date(f.start_utc, spec.timezone, spec.day_start))
    return out
