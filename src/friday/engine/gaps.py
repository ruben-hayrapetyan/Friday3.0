"""Empty time between two pieces of work closed (5 Nov: "why does it leave a gap between the second 17.3 and what came
before it"): a piece slides back to meet the work before it on the same day when that costs nothing more. Nothing
prices an empty quarter hour between two blocks, so the annealer had no reason to close one and left the reading
at 12:30am after a problem set ending at 12:15."""

import numpy as np

from friday.engine.compile import Compiled
from friday.engine.kernel import init_state, measure_cost, new_state, total_violations
from friday.engine.problem import EngineItem

STEADY = "minimize_changes"


def closed_gaps(c: Compiled, owner: np.ndarray, cancel: np.ndarray | None = None) -> np.ndarray:
    """Each piece with empty time before it and work before that, the same day, moved back to meet that work when no
    wall breaks and no stage costs more. Keeping the plan steady isn't counted: a gap the last plan had would stay
    for good, as closing it moves the block. A break you set between blocks is counted, so that room stays. Pinned,
    locked and timed time stays where it is, and so do meals and anything with travel around it."""
    items = list(c.problem.items.values())
    steady = steady_measures(c)
    best = unsteady_values(c, owner, steady)
    s = 0
    while s < c.m.S:
        if cancel is not None and cancel[0]:
            break
        i = int(owner[s])
        if i < 0:
            s += 1
            continue
        end = piece_end(owner, s)
        trial = slid_back(c, owner, items[i], i, s, end)
        if trial is not None:
            values = unsteady_values(c, trial, steady)
            if all(new <= old for new, old in zip(values, best, strict=True)):
                owner, best = trial, values
        s = end + 1  # past where it was: the time it left is the next piece's gap, so they close one after another
    return owner


def piece_end(owner: np.ndarray, s: int) -> int:
    """The last slot of the piece starting at `s`."""
    end = s
    while end + 1 < len(owner) and owner[end + 1] == owner[s]:
        end += 1
    return end


def slid_back(c: Compiled, owner: np.ndarray, item: EngineItem, i: int, start: int, end: int) -> np.ndarray | None:
    """The plan with the piece `start`…`end` moved back over the empty time before it, or None when there's none to
    close: no empty time, an event, the day's start or another day before it, or a piece that mustn't move."""
    grid, blocked = c.problem.grid, c.problem.blocked
    if item.meal_window is not None or item.travel_before or item.travel_after:
        return None
    if any(s in item.locked or s in item.preferred or s in item.held for s in range(start, end + 1)):
        return None
    first = start
    while first > 0 and owner[first - 1] < 0 and not blocked[first - 1] and grid.day[first - 1] == grid.day[start]:
        first -= 1
    if first == start or first == 0 or owner[first - 1] < 0 or grid.day[first - 1] != grid.day[start]:
        return None
    moved = range(first, first + end - start + 1)
    if not all(c.m.allowed[i, s] for s in moved):
        return None
    trial = owner.copy()
    trial[start : end + 1] = -1
    trial[list(moved)] = i
    return trial if no_walls_broken(c, trial) else None


def no_walls_broken(c: Compiled, owner: np.ndarray) -> bool:
    st = new_state(c.m)
    init_state(c.m, st, owner)
    return int(total_violations(c.m, st)) == 0


def steady_measures(c: Compiled) -> list[int]:
    """The measures of keeping the plan steady (`minimize_changes`, both halves)."""
    names = {r.name for r in c.problem.rules if r.type == STEADY}
    rules = {n for n, name in enumerate(c.rule_names) if name in names}
    return [m for m in range(c.m.M) if int(c.m.m_rule[m]) in rules]


def unsteady_values(c: Compiled, owner: np.ndarray, steady: list[int]) -> tuple[int, ...]:
    """The plan's stage values without what keeping it steady costs."""
    st = new_state(c.m)
    init_state(c.m, st, owner)
    values = [int(v) for v in st.stage_value]
    for m in steady:
        values[int(c.m.m_stage[m])] -= int(measure_cost(c.m, m, st.measure_value[m]))
    return tuple(values)
