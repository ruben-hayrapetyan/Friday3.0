"""One solve, from a snapshot to a plan (DESIGN §15.3 step 2). This is what the worker process runs.

Build, allocate and attach quotas, ask the executor whether the hard deadlines can all be met, then schedule. When
the plan gives an optional event's time to work, and a night-before rule ended the night before it early ("no work
after 10pm the night before climbing club"), you aren't going, so that night is lifted and the plan made once more
from this one; kept only if it never keeps an event it worked late before, and is no later.
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
    result = schedule(problem, config, warm=warm, cancel=cancel, overloaded=overloaded)
    lifted = not_gone_to(problem, result.plan)
    if lifted and not (cancel is not None and cancel[0]):
        inp2 = dataclasses.replace(
            inp, settings=inp.settings | {"rules": with_skip_days(inp.settings["rules"], lifted)}
        )
        problem2 = build_problem(inp2)
        apply_quotas(problem2.items.values(), allocation, problem2.grid.horizon_end, problem2.grid.units)
        for key, item in problem2.items.items():  # from this plan, not the last saved one
            item.current = frozenset(result.plan.get(key, ())) | item.preferred
        quick = dataclasses.replace(config, fallback_overload_warm_s=config.fallback_warm_s)
        again = schedule(problem2, quick, warm=True, cancel=cancel, overloaded=overloaded)
        no_later = again.stage_values["deadlines"] <= result.stage_values["deadlines"]
        if no_later and kept_nights_free(problem, again.plan, lifted):
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


def kept_nights_free(problem: Problem, plan: Plan, lifted: dict[str, set[date]]) -> bool:
    """No lifted night worked late before an event the new plan keeps after all (one you'd go to tired)."""
    spec, used, grid = problem.grid.spec, worked(plan), problem.grid
    for rule in problem.rules:
        if not isinstance(rule, BeforeEvent) or rule.name not in lifted:
            continue
        for f in titled(problem, rule.p.titles):
            day = planning_date(f.start_utc, spec.timezone, spec.day_start)
            if day not in lifted[rule.name] or used & set(grid.slots_in(f.start_utc, f.end_utc)):
                continue  # not lifted, or still not gone to
            if any(rule.matches(s) for s in used if grid.slots[s].date == day.fromordinal(day.toordinal() - 1)):
                return False
    return True
