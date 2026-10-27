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
from friday.engine.rules.prices import BeforeEvent, Skippable, titled
from friday.engine.scheduler import Schedule, SchedulerConfig, schedule
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
    given, corners = given_to_work(problem, result.plan)
    # Optional events the plan took only a corner of are kept first, when the work still fits on time and keeping them
    # costs no more elsewhere than skipping them would; then those given to work are given whole, and the nights
    # before them lifted, as before.
    for kept in [corners, {}] if corners else [{}]:
        if cancel is not None and cancel[0]:
            break
        starts = {start for found in kept.values() for start in found}
        freed = {name: found - kept.get(name, set()) for name, found in given.items()}
        again = second_pass(inp, allocation, result, config, cancel, overloaded, nights_lifted(problem, result, starts),
                            freed, kept)  # fmt: skip
        if again is None:
            break
        inp2, problem2, solved2 = again
        new, old = solved2.stage_values, result.stage_values
        # The stages count in order, as the planner counts them. Kept, the events' whole worth is what the first plan
        # left unpriced (it paid for a corner of each, and you'd have missed all of it): never lateness.
        allowed = kept_worth(problem, kept)
        stages = ("deadlines", "wellbeing", "preferences") if kept else ("deadlines", "wellbeing")
        better = [new[stage] for stage in stages] <= [old[stage] + allowed.get(stage, 0) for stage in stages]
        if better:
            return Solved(inp2, problem2, allocation, deadlines, overloaded, solved2)
    return Solved(inp, problem, allocation, deadlines, overloaded, result)


def kept_worth(problem: Problem, kept: dict[str, set[int]]) -> dict[str, float]:
    """By stage, what skipping the kept events whole would have cost, as their rules price them: what keeping them may
    cost elsewhere instead (a later evening, a pin moved), never lateness."""
    out: dict[str, float] = {}
    for rule in problem.rules:
        if not isinstance(rule, Skippable) or rule.name not in kept:
            continue
        hours = sum(
            (f.end_utc - f.start_utc) / 60 for f in titled(problem, rule.p.titles) if f.start_utc in kept[rule.name]
        )
        out[rule.stage] = out.get(rule.stage, 0) + rule.effective_weight * float(rule.p.price) * hours * problem.scale
    out.pop("deadlines", None)
    return out


def nights_lifted(problem: Problem, result: Schedule, kept: set[int]) -> dict[str, set[date]]:
    """Per night-before rule, the nights to free: before the optional events the plan gives to work (but not those
    kept), or, when work is late anyway, before every one of them."""
    lifted = not_gone_to(problem, result.plan, kept)
    if result.stage_values["deadlines"] > 0:  # late anyway: any of those nights may be what the work needs
        for name, days in optional_nights(problem).items():
            lifted.setdefault(name, set()).update(days)
    return lifted


def second_pass(
    inp: BuildInput,
    allocation: Allocation,
    result: Schedule,
    config: SchedulerConfig,
    cancel: np.ndarray | None,
    overloaded: bool,
    lifted: dict[str, set[date]],
    freed: dict[str, set[int]],
    kept: dict[str, set[int]],
) -> tuple[BuildInput, Problem, Schedule] | None:
    """The plan again from the first pass's, with those nights lifted, those events given to work whole and those
    kept from it; None when nothing changes."""
    if not (lifted or any(freed.values()) or kept):
        return None
    rules = with_kept(with_given(with_skip_days(inp.settings["rules"], lifted), freed), kept)
    inp2 = dataclasses.replace(inp, settings=inp.settings | {"rules": rules})
    problem2 = build_problem(inp2)
    apply_quotas(problem2.items.values(), allocation, problem2.grid.horizon_end, problem2.grid.units)
    for key, item in problem2.items.items():  # from this plan, not the last saved one
        item.current = frozenset(result.plan.get(key, ())) | item.preferred
    # From the first pass's plan, only those nights and events change: an anneal finds it; another deadline search
    # (seconds of CP-SAT on a big week) bought nothing the first hadn't.
    quick = dataclasses.replace(config, use_fallback=False)
    return inp2, problem2, schedule(problem2, quick, warm=True, cancel=cancel, overloaded=overloaded)


def worked(plan: Plan) -> set[int]:
    return {s for slots in plan.values() for s in slots}


def not_gone_to(problem: Problem, plan: Plan, kept: set[int] = frozenset()) -> dict[str, set[date]]:  # type: ignore[assignment]
    """Per night-before rule, the days of its optional events whose time the plan gives to work (not those `kept`)."""
    spec, used = problem.grid.spec, worked(plan)
    out: dict[str, set[date]] = {}
    for rule in problem.rules:
        if not isinstance(rule, BeforeEvent):
            continue
        for f in titled(problem, rule.p.titles):
            if f.skippable and f.start_utc not in kept and used & set(problem.grid.slots_in(f.start_utc, f.end_utc)):
                out.setdefault(rule.name, set()).add(planning_date(f.start_utc, spec.timezone, spec.day_start))
    return out


CORNER = 0.5  # work in less than this share of an optional event is a corner of it: worth keeping it if it can be


def given_to_work(problem: Problem, plan: Plan) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """Per optional-event rule, the starts of its events whose time the plan gives to work (skipped, so all of their
    time is work's in the second pass), and of those, the ones it takes only a corner of."""
    used, grid = worked(plan), problem.grid
    given: dict[str, set[int]] = {}
    corners: dict[str, set[int]] = {}
    for rule in problem.rules:
        if not isinstance(rule, Skippable):
            continue
        for f in titled(problem, rule.p.titles):
            if not f.skippable:
                continue
            taken = used & set(grid.slots_overlapping(f.blocked_lo, f.blocked_hi))
            if not taken:
                continue
            given.setdefault(rule.name, set()).add(f.start_utc)
            own = [s for s in grid.slots_overlapping(f.start_utc, f.end_utc)]
            if sum(int(grid.units[s]) for s in taken) < CORNER * sum(int(grid.units[s]) for s in own):
                corners.setdefault(rule.name, set()).add(f.start_utc)
    return given, corners


def with_kept(rules: tuple, kept: dict[str, set[int]]) -> tuple:
    return tuple(
        r.model_copy(update={"params": r.params | {"kept": sorted(kept[r.name])}}) if r.name in kept else r
        for r in rules
    )


def with_given(rules: tuple, given: dict[str, set[int]]) -> tuple:
    return tuple(
        r.model_copy(update={"params": r.params | {"given": sorted(given[r.name])}}) if r.name in given else r
        for r in rules
    )


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
