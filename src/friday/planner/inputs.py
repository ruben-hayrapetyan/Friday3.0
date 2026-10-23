"""The allocator's and executor's inputs, built from the same items and settings as the scheduler's Problem.

Both look past the scheduler's horizon: the allocator over `allocator_weeks`, the executor until the latest hard
due. So fixed items and nights are gathered over that span here rather than read from the Problem.
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from friday.core.pace import DayScales
from friday.core.time import UNIT_MIN, planning_day_start_utc, week_of
from friday.engine.allocator import AllocatorInput, AllocDay
from friday.engine.executor import ExecutorInput, Interval, Job, NowSettings, merge, subtract
from friday.engine.problem import Problem
from friday.planner.build import BuildInput, cap_hours_on, fixed_occurrences, nights


def busy_until(inp: BuildInput, problem: Problem, end: int) -> list[Interval]:
    """Blocking fixed items with their buffers, and sleep cores, from now until `end`."""
    grid = problem.grid
    days = (end - grid.now) // 1440 + 2
    fixed, _ = fixed_occurrences(inp, grid.now, end)
    cores = [night.core for night in nights(inp, grid.spec, grid.slots[0].date, days).values()]
    return merge([(f.blocked_lo, f.blocked_hi) for f in fixed if f.blocks_time] + cores)


def overlap(free: list[Interval], lo: int, hi: int) -> int:
    return sum(max(0, min(b, hi) - max(a, lo)) for a, b in free)


def allocator_input(inp: BuildInput, problem: Problem) -> AllocatorInput:
    settings, grid = inp.settings, problem.grid
    spec, first = grid.spec, grid.slots[0].date
    n_days = settings["time"].allocator_weeks * 7
    bounds = [
        planning_day_start_utc(first + timedelta(days=d), spec.timezone, spec.day_start) for d in range(n_days + 1)
    ]
    free = subtract([(grid.now, bounds[-1])], busy_until(inp, problem, bounds[-1]))
    scales = list(inp.day_scales or [])
    days = []
    for d in range(n_days):
        day = first + timedelta(days=d)
        lo, hi = max(grid.now, bounds[d]), bounds[d + 1]
        days.append(
            AllocDay(
                date=day,
                start_utc=lo,
                end_utc=hi,
                free_units=overlap(free, lo, hi) // UNIT_MIN,
                cap_units=round(cap_hours_on(inp.settings, inp.day_overrides, day) * 60 / UNIT_MIN),
                week=week_of(day, spec.week_start),
                scales=scales[d] if d < len(scales) else DayScales(),
            )
        )
    planner = settings["planner"]
    return AllocatorInput(
        days,
        list(problem.items.values()),
        problem.rules,
        grid.now,
        grid.n_days,
        grid.horizon_end,
        planner.utilization,
        planner.pacing_weight,
    )


def executor_input(inp: BuildInput, problem: Problem) -> ExecutorInput:
    """Free time and hard-deadline jobs from now until the latest hard due (DESIGN §14.1).

    Locked pins are fixed in time, so every one leaves free time, and a job's own locked minutes before its due
    count as work already placed: its EDF minutes are what's left after them.
    """
    grid, now = problem.grid, inp.now_utc
    jobs = []
    for order, item in enumerate(problem.items.values()):
        if item.amount != "fixed" or item.firmness != "hard" or item.due_utc is None or item.need <= 0:
            continue
        locked_before_due = sum(int(grid.units[s]) for s in item.locked if grid.end[s] <= item.due_utc)
        minutes = max(0, item.need - locked_before_due) * UNIT_MIN
        if minutes > 0:
            jobs.append(Job(item.key, max(now, item.release_utc or now), item.due_utc, minutes, item.importance, order))
    end = max([j.due for j in jobs] + [grid.horizon_end])
    busy = busy_until(inp, problem, end)
    locked = [(int(grid.start[s]), int(grid.end[s])) for item in problem.items.values() for s in item.locked]
    next_blocking = min((lo for lo, _ in busy if lo > now), default=None)
    return ExecutorInput(now, subtract([(now, end)], busy + locked), jobs, next_blocking)


def now_settings(settings: Mapping[str, Any]) -> NowSettings:
    executor = settings["executor"]
    return NowSettings(executor.swap_run_min, executor.swap_count, executor.soon_hours, executor.notify_minutes)
