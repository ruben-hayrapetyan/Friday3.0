"""Executor: exact feasibility by earliest-deadline-first (ENGINE_REFERENCE section 9).

Pure functions over free-time intervals and hard-deadline jobs; no solver. For one worker, splittable
jobs and release times, EDF minimises maximum lateness, so `l_max <= 0` is an exact feasibility test.
Daily caps, minimum chunks and dependencies are ignored here, so the test is slightly optimistic.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass

from .problem import Problem

Interval = tuple[int, int]


@dataclass(frozen=True)
class Job:
    key: str
    release: int
    due: int
    minutes: int
    importance: int = 3
    order: int = 0  # tie-break: lower first


@dataclass
class EdfResult:
    finish: dict[str, int]
    l_max: int  # largest finish - due, in minutes; <= 0 means every deadline can be met
    pieces: dict[str, list[Interval]]

    @property
    def feasible(self) -> bool:
        return self.l_max <= 0


def merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for lo, hi in sorted(i for i in intervals if i[1] > i[0]):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def subtract(free: list[Interval], busy: list[Interval]) -> list[Interval]:
    out = []
    busy = merge(busy)
    for lo, hi in merge(free):
        cur = lo
        for b0, b1 in busy:
            if b1 <= cur or b0 >= hi:
                continue
            if b0 > cur:
                out.append((cur, b0))
            cur = max(cur, b1)
        if cur < hi:
            out.append((cur, hi))
    return out


def edf(jobs: list[Job], free: list[Interval]) -> EdfResult:
    """Preemptive EDF over `free` time. Ties: higher importance, then lower `order`."""
    free = merge(free)
    remaining = {j.key: j.minutes for j in jobs}
    pending = sorted(jobs, key=lambda j: j.release)
    ready: list[tuple[int, int, int, str]] = []
    finish: dict[str, int] = {}
    pieces: dict[str, list[Interval]] = {j.key: [] for j in jobs}
    ri = 0
    for lo, hi in free:
        t = lo
        while t < hi:
            while ri < len(pending) and pending[ri].release <= t:
                j = pending[ri]
                heapq.heappush(ready, (j.due, -j.importance, j.order, j.key))
                ri += 1
            if not ready:
                if ri == len(pending) or pending[ri].release >= hi:
                    break
                t = pending[ri].release
                continue
            key = ready[0][3]
            next_release = pending[ri].release if ri < len(pending) else hi
            run = min(remaining[key], hi - t, next_release - t)
            pieces[key].append((t, t + run))
            remaining[key] -= run
            t += run
            if remaining[key] == 0:
                heapq.heappop(ready)
                finish[key] = t
    end_of_free = free[-1][1] if free else 0
    for j in jobs:
        if j.key not in finish:  # did not fit: strictly after both its due date and the last free minute
            finish[j.key] = max(end_of_free, j.due) + remaining[j.key]
    l_max = max((finish[j.key] - j.due for j in jobs), default=-1)
    return EdfResult(finish, l_max, pieces)


def latest_starts(jobs: list[Job], free: list[Interval]) -> dict[str, int]:
    """As-late-as-possible schedule by running EDF backwards; returns each job's latest start (minutes).

    In reversed time due dates act as release times and the job with the latest original release goes
    first. A job that cannot fit gets a start before the first free minute (negative slack).
    """
    free = merge(free)
    if not jobs:
        return {}
    horizon = free[-1][1] if free else 0
    big = max([horizon] + [j.due for j in jobs]) + 1
    rev_free = [(big - hi, big - lo) for lo, hi in reversed(free)]
    rev_jobs = [Job(j.key, big - j.due, big - j.release, j.minutes, j.importance, j.order) for j in jobs]
    res = edf(rev_jobs, rev_free)
    out = {}
    for j in jobs:
        pcs = res.pieces[j.key]
        if sum(b - a for a, b in pcs) < j.minutes:
            out[j.key] = min(j.release, free[0][0] if free else j.release) - 1
            continue
        out[j.key] = big - max(b for _, b in pcs)
    return out


def free_intervals(problem: Problem, until: int | None = None) -> list[Interval]:
    """Free time from now: minus blocking fixed items (buffers included), sleep cores, and locked pins."""
    g = problem.grid
    hi = g.horizon_end if until is None else min(until, g.horizon_end)
    busy: list[Interval] = [(f.blocked_lo, f.blocked_hi) for f in problem.fixed if f.blocks_time]
    busy += [n.core for n in problem.nights.values()]
    return subtract([(g.now, hi)], busy)


def jobs_from_problem(problem: Problem, exclude_locked: bool = False) -> list[Job]:
    g = problem.grid
    jobs = []
    for order, it in enumerate(problem.items.values()):
        if it.firmness != "hard" or it.due is None or it.amount != "fixed" or it.need <= 0:
            continue
        jobs.append(Job(it.key, g.now if it.release is None else max(g.now, it.release), it.due,
                        it.need * 15, it.importance, order))
    return jobs


def deadline_feasible(problem: Problem) -> EdfResult:
    jobs = jobs_from_problem(problem)
    if not jobs:
        return EdfResult({}, -1, {})
    free = free_intervals(problem, until=max(j.due for j in jobs))
    locked = [(int(g0), int(g1)) for it in problem.items.values() for s in it.locked
              for g0, g1 in [(problem.grid.start[s], problem.grid.end[s])]]
    # a locked slot of one job is that job's work, but treating all locks as busy is the conservative reading
    return edf(jobs, subtract(free, locked))
