"""One solve, from a snapshot to a plan (DESIGN §15.3 step 2). This is what the worker process runs.

Build, allocate and attach quotas, ask the executor whether the hard deadlines can all be met, then schedule.
"""

from dataclasses import dataclass

import numpy as np

from friday.engine.allocator import Allocation, allocate, apply_quotas
from friday.engine.executor import ExecutorInput, edf
from friday.engine.problem import Problem
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
    result = schedule(problem, config, warm=warm and bool(snapshot.plan_blocks), cancel=cancel, overloaded=overloaded)
    return Solved(inp, problem, allocation, deadlines, overloaded, result)
