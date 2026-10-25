"""Every wall violation of a plan (DESIGN §11.4). A plan with any violation is invalid, whatever it costs."""

from collections.abc import Iterable
from dataclasses import dataclass

from friday.engine.problem import EngineItem, Plan, Problem, Solution

WALL_OF = {
    "unknown_item": "W1",
    "duplicate_slot": "W1",
    "bad_slot": "W1",
    "double_booked": "W1",
    "pruned_slot": "W2",
    "lock_dropped": "W3",
    "over_placed": "W4",
    "over_max": "W4",
    "over_cap": "W4",
    "over_ceiling": "W4",
    "day_cap": "W5",
    "not_one_sitting": "W6",
    "partial_one_sitting": "W6",
    "short_chunk": "W7",
    "long_chunk": "W7",
    "dependency": "W8",
    "protected_late": "W9",
}


@dataclass(frozen=True)
class Violation:
    code: str
    key: str
    detail: str = ""

    @property
    def wall(self) -> str:
        return WALL_OF[self.code]

    def __str__(self) -> str:
        return f"{self.wall} {self.code}[{self.key}] {self.detail}"


def runs(slots: tuple[int, ...]) -> list[tuple[int, int]]:
    """Maximal runs of consecutive slot indices as (first, last)."""
    out: list[tuple[int, int]] = []
    for s in slots:
        if out and out[-1][1] == s - 1:
            out[-1] = (out[-1][0], s)
        else:
            out.append((s, s))
    return out


def lag_slot(problem: Problem, s: int, lag_min: int) -> int:
    """The slot t such that a dependency is read before t: the slot holding start(s) − lag; ≤ 0 is nothing."""
    grid = problem.grid
    if lag_min == 0:
        return s
    t = int(grid.start[s]) - lag_min
    if t < grid.slots[0].start_utc:
        return 0
    return grid.slot_at(t)


def check(problem: Problem, plan: Plan, protected: Iterable[str] = ()) -> list[Violation]:
    """`protected` names the items W9 keeps complete and on time (those on time in the start plan)."""
    solution = Solution(problem, plan)
    out = [Violation("unknown_item", k) for k in plan if k not in problem.items]
    out += slot_violations(problem, solution)
    for item in problem.items.values():
        out += amount_violations(problem, solution, item)
        out += chunk_violations(problem, solution, item)
        out += dependency_violations(problem, solution, item)
    out += day_cap_violations(problem, solution)
    for key in protected:
        out += protected_violations(problem, solution, problem.items[key])
    return out


def slot_violations(problem: Problem, solution: Solution) -> list[Violation]:
    out = []
    owner: dict[int, str] = {}
    for key, slots in solution.slots.items():
        item = problem.items[key]
        if len(set(slots)) != len(slots):
            out.append(Violation("duplicate_slot", key))
        for s in slots:
            if not 0 <= s < problem.grid.S:
                out.append(Violation("bad_slot", key, str(s)))
                continue
            if s in owner and owner[s] != key:
                out.append(Violation("double_booked", key, f"slot {s} also {owner[s]}"))
            owner[s] = key
            if s not in item.allowed_set:
                out.append(Violation("pruned_slot", key, f"slot {s}"))
        missing = item.locked - solution.sets[key]
        if missing:
            out.append(Violation("lock_dropped", key, f"{sorted(missing)}"))
    return out


def amount_violations(problem: Problem, solution: Solution, item: EngineItem) -> list[Violation]:
    grid, key = problem.grid, item.key
    slots, placed = solution.slots[key], solution.placed(key)
    out = []
    # One extra unit is allowed only when it fills a 30-minute slot holding a 15-minute remainder.
    fills_coarse_slot = placed == item.need + 1 and any(grid.units[s] > 1 for s in slots)
    if item.amount == "fixed" and placed > item.need and not fills_coarse_slot:
        out.append(Violation("over_placed", key, f"{placed} > {item.need}"))
    fills_coarse_max = placed == item.max + 1 and any(grid.units[s] > 1 for s in slots)
    if item.amount == "elastic" and placed > item.max and not fills_coarse_max:
        out.append(Violation("over_max", key, f"{placed} > {item.max}"))
    if item.amount == "target" and placed > item.cap:
        out.append(Violation("over_cap", key, f"{placed} > {item.cap}"))
    if item.amount == "open":
        for d in range(grid.n_days):
            ceiling = item.daily_ceiling - (item.progress_today if d == 0 else 0)
            got = sum(int(grid.units[s]) for s in slots if grid.slots[s].day == d)
            if got > ceiling:
                out.append(Violation("over_ceiling", key, f"day {d}: {got} > {ceiling}"))
    return out


def chunk_violations(problem: Problem, solution: Solution, item: EngineItem) -> list[Violation]:
    units, key = problem.grid.units, item.key
    chunks, placed = runs(solution.slots[key]), solution.placed(key)
    out = []
    if item.shape == "one_sitting":
        if len(chunks) > 1:
            out.append(Violation("not_one_sitting", key, f"{len(chunks)} chunks"))
        if item.amount == "fixed" and 0 < placed < item.need:
            out.append(Violation("partial_one_sitting", key, f"{placed} of {item.need}"))
    for a, b in chunks:
        chunk_units = int(units[a : b + 1].sum())
        if chunk_units < item.min_chunk:
            out.append(Violation("short_chunk", key, f"slots {a}-{b}: {chunk_units} < {item.min_chunk}"))
        if item.max_chunk is not None and chunk_units > item.max_chunk:
            out.append(Violation("long_chunk", key, f"slots {a}-{b}: {chunk_units} > {item.max_chunk}"))
    return out


def dependency_violations(problem: Problem, solution: Solution, item: EngineItem) -> list[Violation]:
    """At most one violation per dependency: its first slot that starts too early."""
    out = []
    for dep in item.depends_on:
        required = dep.required
        if required == 0 or dep.key not in problem.items:
            continue
        before = solution.prefix(dep.key)
        for s in solution.slots[item.key]:
            if s in item.locked:
                continue
            t = lag_slot(problem, s, dep.lag_min)
            if (0 if t <= 0 else int(before[t])) < required:
                out.append(Violation("dependency", item.key, f"slot {s} before {dep.key} reached {required} units"))
                break
    return out


def day_cap_violations(problem: Problem, solution: Solution) -> list[Violation]:
    grid = problem.grid
    per_day = [0] * grid.n_days
    occupied = {s for slots in solution.slots.values() for s in slots if 0 <= s < grid.S}
    for s in occupied:
        per_day[grid.slots[s].day] += int(grid.units[s])
    return [
        Violation("day_cap", f"d{d}", f"{used} > {problem.day_caps[d]}")
        for d, used in enumerate(per_day)
        if used > problem.day_caps[d]
    ]


def protected_violations(problem: Problem, solution: Solution, item: EngineItem) -> list[Violation]:
    grid, key = problem.grid, item.key
    late = [s for s in solution.slots[key] if item.due_utc is not None and int(grid.end[s]) > item.due_utc]
    late = [s for s in late if s not in item.locked]  # a lock is never moved, even past the due
    if late or solution.placed(key) < item.need:
        return [Violation("protected_late", key, f"{solution.placed(key)} of {item.need} units, {len(late)} late")]
    return []
