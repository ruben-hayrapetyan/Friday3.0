"""The executor (DESIGN §14): exact deadline feasibility by earliest-deadline-first, slack, safe swaps and `now`.

Pure functions over free-time intervals and hard-deadline jobs; no solver. For one worker, splittable jobs and
release times, EDF minimizes the maximum lateness, so `l_max <= 0` is an exact feasibility test. Daily caps,
minimum chunks and dependencies are ignored here, so the test is slightly optimistic; the scheduler enforces them.
"""

import heapq
import math
from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np

from friday.core.time import UNIT_MIN, Grid
from friday.engine.compile import Compiled, compile_problem
from friday.engine.construct import construct
from friday.engine.explain import Block, blocks_of
from friday.engine.problem import EngineItem, Plan, Problem
from friday.engine.rules import price_row

Interval = tuple[int, int]
NEVER = math.inf


@dataclass(frozen=True)
class Job:
    key: str
    release: int
    due: int
    minutes: int
    importance: int = 3
    order: int = 0  # the last tie-break: lower first


@dataclass
class EdfResult:
    finish: dict[str, int]
    l_max: int  # the largest finish − due, in minutes; ≤ 0 means every deadline can be met
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
        if j.key not in finish:  # it didn't fit: it ends after both its due and the last free minute
            finish[j.key] = max(end_of_free, j.due) + remaining[j.key]
    l_max = max((finish[j.key] - j.due for j in jobs), default=-1)
    return EdfResult(finish, l_max, pieces)


def latest_starts(jobs: list[Job], free: list[Interval]) -> dict[str, int]:
    """Each job's latest start, from EDF run backwards (an as-late-as-possible schedule).

    In reversed time due dates act as releases, and the job with the latest original release goes first. A job
    that can't fit gets a start before its release, so its slack is negative.
    """
    free = merge(free)
    if not jobs:
        return {}
    big = max([free[-1][1] if free else 0] + [j.due for j in jobs]) + 1
    rev_free = [(big - hi, big - lo) for lo, hi in reversed(free)]
    rev_jobs = [Job(j.key, big - j.due, big - j.release, j.minutes, j.importance, j.order) for j in jobs]
    result = edf(rev_jobs, rev_free)
    out = {}
    for j in jobs:
        pieces = result.pieces[j.key]
        if sum(b - a for a, b in pieces) < j.minutes:
            out[j.key] = min(j.release, free[0][0] if free else j.release) - 1
        else:
            out[j.key] = big - max(b for _, b in pieces)
    return out


@dataclass(frozen=True)
class ExecutorInput:
    """What the executor needs besides the plan. `free` runs from now to the latest hard due."""

    now: int
    free: list[Interval]  # minus blocking fixed items with buffers, sleep cores and every locked pin
    jobs: list[Job]
    next_blocking: int | None = None  # the start of the next blocking fixed item or sleep core


@dataclass(frozen=True)
class Slack:
    latest_start: int
    minutes: int  # wall time from now to the latest start; negative when the deadlines can't all be met
    free_minutes: int  # free time from now to the latest start


def slack(inp: ExecutorInput) -> dict[str, Slack]:
    out = {}
    for key, start in latest_starts(inp.jobs, inp.free).items():
        free = sum(min(hi, start) - lo for lo, hi in inp.free if lo < start)
        out[key] = Slack(start, start - inp.now, free)
    return out


@dataclass(frozen=True)
class Swap:
    key: str
    minutes: int  # the run the safety check assumed
    price: int  # wellbeing and preferences price at the current slot
    next_start: float  # the item's next planned start, NEVER when it isn't planned
    slack_minutes: float  # NEVER for items without a hard deadline
    chunk_minutes: int  # the shortest run worth starting: the whole remainder for one-sitting items


def remaining_minutes(item: EngineItem, problem: Problem) -> int:
    if item.amount == "fixed":
        units = item.need
    elif item.amount == "elastic":
        units = item.ideal
    elif item.amount == "target":
        units = max(0, item.target - item.progress)
    else:
        today = problem.scales[0].open_value_slopes if problem.scales else 1.0
        units = item.daily_ceiling - item.progress_today if today > 0 else 0
    return units * UNIT_MIN


def is_candidate(item: EngineItem, problem: Problem, now: int, slot: int) -> bool:
    released = item.release_utc is None or item.release_utc <= now
    dependencies_done = all(dep.required == 0 for dep in item.depends_on)
    return released and dependencies_done and slot in item.allowed_set and remaining_minutes(item, problem) > 0


def price_now(problem: Problem, item: EngineItem, slot: int) -> int:
    rules = (r for r in problem.rules if r.has_price and r.stage != "deadlines" and r.applies(item))
    return int(sum(price_row(problem, rule, item)[slot] for rule in rules))


def is_safe(inp: ExecutorInput, key: str, run: int, before: EdfResult) -> bool:
    """Doing `key` for `run` minutes from now keeps every deadline that could be met."""
    taken = subtract(inp.free, [(inp.now, inp.now + run)])
    jobs = [replace(j, minutes=j.minutes - run) if j.key == key else j for j in inp.jobs]
    after = edf([j for j in jobs if j.minutes > 0], taken)
    return after.l_max <= max(0, before.l_max)


def safe_items(problem: Problem, plan: Plan, inp: ExecutorInput, run_limit: int) -> list[Swap]:
    """Every item that is safe to work on now for up to `run_limit` minutes, cheapest first (§14.4)."""
    slot = problem.grid.slot_at(max(inp.now, problem.grid.now))  # the grid starts at the next whole unit
    if slot < 0 or run_limit <= 0:
        return []
    before = edf(inp.jobs, inp.free)
    slacks = slack(inp)
    out = []
    for item in problem.items.values():
        if not is_candidate(item, problem, inp.now, slot):
            continue
        run = min(remaining_minutes(item, problem), run_limit)
        if not is_safe(inp, item.key, run, before):
            continue
        starts = [int(problem.grid.start[s]) for s in plan.get(item.key, ()) if problem.grid.end[s] > inp.now]
        item_slack = slacks[item.key].minutes if item.key in slacks else NEVER
        chunk = remaining_minutes(item, problem) if item.shape == "one_sitting" else item.min_chunk * UNIT_MIN
        out.append(Swap(item.key, run, price_now(problem, item, slot), min(starts, default=NEVER), item_slack, chunk))
    return sorted(out, key=lambda w: (w.price, w.next_start, w.slack_minutes, w.key))


@dataclass(frozen=True)
class Alert:
    key: str
    kind: Literal["soon", "start_now", "triage"]
    latest_start: int


@dataclass(frozen=True)
class NowSettings:
    swap_run_min: int = 30
    swap_count: int = 3
    soon_hours: float = 24
    notify_minutes: int = 120


@dataclass
class Now:
    current: str | None  # an item key, or None for free time
    current_source: Literal["timer", "block", "free"]
    next: Block | None
    swaps: list[Swap] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    fits: list[Swap] = field(default_factory=list)
    gap_minutes: int = 0  # free time until the next block or blocking fixed item


def now(problem: Problem, plan: Plan, inp: ExecutorInput, settings: NowSettings, timer_key: str | None = None) -> Now:
    """What's happening, what's next, what else is safe to do, and which deadlines need attention (§14.5)."""
    grid = problem.grid
    moment = max(inp.now, grid.now)  # the grid starts at the next whole unit
    blocks = sorted(blocks_of(plan), key=lambda b: b.slots[0])
    covering = next((b for b in blocks if grid.start[b.slots[0]] <= moment < grid.end[b.slots[-1]]), None)
    upcoming = next((b for b in blocks if grid.start[b.slots[0]] > moment), None)
    current = timer_key or (covering.key if covering else None)
    source: Literal["timer", "block", "free"] = "timer" if timer_key else "block" if covering else "free"
    until_blocking = (inp.next_blocking - inp.now) if inp.next_blocking is not None else 10**9
    run = min(settings.swap_run_min, until_blocking)
    swaps = [w for w in safe_items(problem, plan, inp, run) if w.key != current][: settings.swap_count]
    gap = min(until_blocking, int(grid.start[upcoming.slots[0]]) - inp.now if upcoming else 10**9)
    gap = gap if current is None and gap < 10**9 else 0
    fits = [w for w in safe_items(problem, plan, inp, gap) if w.chunk_minutes <= gap][: settings.swap_count]
    return Now(current, source, upcoming, swaps, alerts(inp, settings), fits, gap)


def alerts(inp: ExecutorInput, settings: NowSettings) -> list[Alert]:
    out = []
    for key, s in sorted(slack(inp).items(), key=lambda kv: (kv[1].minutes, kv[0])):
        if s.minutes < 0:
            out.append(Alert(key, "triage", s.latest_start))
        elif s.minutes < settings.notify_minutes:
            out.append(Alert(key, "start_now", s.latest_start))
        elif s.minutes < settings.soon_hours * 60:
            out.append(Alert(key, "soon", s.latest_start))
    return out


def provisional_plan(
    problem: Problem, previous: Plan, changed: set[str], left: dict[str, set[int]] | None = None
) -> dict[str, tuple[int, ...]]:
    """The plan shown until the scheduler answers (§14.6): the previous plan with pins applied, and what the changed
    and new items are missing placed in deadline order into the earliest free allowed slots. `left`: the slots a
    dragged block left, by item."""
    # Construction checks walls only, so the rules' measures (most of compile time) aren't needed.
    c = compile_problem(replace(problem, rules=[], price_cache={}))
    # Only what the command changed (new items are in `changed` too) is placed, and a changed item keeps its blocks
    # where still allowed: placing all unfinished work painted next week's homework into today on every command, and
    # a started task re-placed whole showed three times over the day (M16). The solve decides the rest.
    kept = {k: v for k, v in previous.items() if k in problem.items}
    # A block you dragged is where you put it, and gone from where it was (27 Oct: a preferred pin, what a drag makes,
    # wasn't applied, so the block showed back where it had been until the solve). Written last, so it wins its slots.
    gone = left or {}
    moved = {
        k: pinned_there(c, k, tuple(s for s in kept.get(k, ()) if s not in gone.get(k, set())))
        for k in sorted(changed)
        if k in problem.items and problem.items[k].preferred
    }
    kept = {k: v for k, v in kept.items() if k not in moved} | moved
    base = c.owner_from_plan(kept)
    held = construct(c, base, only=set())
    index = {k: i for i, k in enumerate(c.keys)}
    owner = construct(c, base, only=changed)
    # Work that an event you just added, or a block you just pinned, now covers steps aside to the nearest free time:
    # it sat under the event, drawn over it, until the solve (27 Oct), and placed in the earliest free time instead
    # it jumped days away and slid back when the solve landed.
    for k, slots in kept.items():
        gone = [s for s in slots if held[s] != index[k]]
        if gone and k not in changed:
            step_aside(c, owner, index[k], gone)
    return c.plan_from_owner(owner)


def step_aside(c: Compiled, owner: np.ndarray, i: int, near: list[int]) -> None:
    """What item `i` is missing, written into the free time it may use (by a hard due, too) nearest the slots it lost:
    the nearest free stretch that holds it all, and of a longer one the part nearest; pieces only when none does. A
    quick placement: chunk sizes and day limits are the solve's."""
    M, grid = c.m, c.problem.grid
    missing = int(M.need[i]) - int(M.units[: M.S][owner[: M.S] == i].sum())
    if missing <= 0:
        return
    center = float(np.mean(grid.start[near]))
    runs: list[list[int]] = []
    for s in range(M.S):
        if owner[s] != -1 or not M.on_time[i, s]:
            continue
        if runs and runs[-1][-1] == s - 1 and grid.contiguous(s - 1, s):
            runs[-1].append(s)
        else:
            runs.append([s])

    def gap(run: list[int]) -> float:
        return min(abs(float(grid.start[s]) - center) for s in run)

    while missing > 0 and runs:
        # The nearest stretch that holds all of it, else the nearest: a busy day broke it into quarter hours.
        run = min(runs, key=lambda r: (int(M.units[r].sum()) < missing, gap(r)))
        runs.remove(run)
        part = nearest_part(grid, run, missing, center)
        for s in part:
            owner[s] = i
        missing -= int(M.units[part].sum())


def nearest_part(grid: Grid, run: list[int], units: int, center: float) -> list[int]:
    """The stretch of `run` holding `units` whose middle is nearest `center`; all of it when it holds less."""
    best: tuple[float, list[int]] | None = None
    for a in range(len(run)):
        total = 0
        for b in range(a, len(run)):
            total += int(grid.units[run[b]])
            if total >= units:
                gap = abs((float(grid.start[run[a]]) + float(grid.end[run[b]])) / 2 - center)
                if best is None or gap < best[0]:
                    best = (gap, run[a : b + 1])
                break
    return best[1] if best else run


def pinned_there(c: Compiled, key: str, was: tuple[int, ...]) -> tuple[int, ...]:
    """An item's slots with its preferred pins applied: the pinned slots, and of its other planned stretches as many as
    still fit what it needs, the one most like the pin in length (the one dragged) let go first."""
    M = c.m
    i = c.keys.index(key)
    pinned = sorted(c.problem.items[key].preferred)
    room = max(int(M.need[i]), int(M.amount_cap[i]))
    have = sum(int(M.units[s]) for s in pinned)
    runs: list[list[int]] = []
    for s in (s for s in was if s not in c.problem.items[key].preferred):
        if runs and s == runs[-1][-1] + 1:
            runs[-1].append(s)
        else:
            runs.append([s])
    size = {id(r): sum(int(M.units[s]) for s in r) for r in runs}
    over = have + sum(size.values()) - room
    for run in sorted(runs, key=lambda r: (abs(size[id(r)] - have), r[0])):
        if over <= 0:
            break
        runs.remove(run)
        over -= size[id(run)]
    return tuple(sorted(pinned + [s for r in runs for s in r]))
