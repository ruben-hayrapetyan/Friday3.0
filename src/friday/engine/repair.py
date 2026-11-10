"""Deadline repair (DESIGN §11.6 step 2): the sampler on the deadlines stage alone, with walls as penalties.

It may pass through invalid states to get out of a late start; the best valid state it sees is kept only if it
is less late than the start.
"""

import numpy as np

from friday.engine.chain import run_chain
from friday.engine.compile import Compiled
from friday.engine.kernel import N_MOVES, init_state, move_cumulative, new_state

PENALTY = 1e9
DEADLINES_ONLY = np.array([1.0, 0.0, 0.0])
# The research ran repair with its calibration seeing no wellbeing or preference deltas, which leaves the median
# at 1 point-unit: T runs from 0.3 to 0.003, cold enough that lateness only falls once it is found.
T0, T1 = 0.3, 0.003
# Lateness first, but a meal not given up for nothing (C92): a skipped meal is ~1,000 wellbeing points, 0.1 here, far
# under any lateness yet above the cold end of the temperature, so work late after meals were placed is put right
# around them rather than over them.
MEALS_KEPT = np.array([1.0, 1e-4, 0.0])


def deadline_value(c: Compiled, owner: np.ndarray) -> int:
    st = new_state(c.m)
    init_state(c.m, st, owner)
    return int(st.stage_value[0])


def repair(
    c: Compiled,
    owner: np.ndarray,
    steps: int,
    seed: int,
    move_weights: dict[str, float],
    cancel: np.ndarray | None = None,
    weights: np.ndarray = DEADLINES_ONLY,
) -> np.ndarray:
    late = deadline_value(c, owner)
    if late == 0:
        return owner
    st = new_state(c.m)
    init_state(c.m, st, owner)
    best = owner.copy()
    best_info = np.full(3, np.inf)
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    work = (np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64))
    unprotected = np.zeros(c.m.I, dtype=bool)
    cancel = np.zeros(1, dtype=np.int64) if cancel is None else cancel
    run_chain(
        c.m,
        st,
        unprotected,
        weights,
        np.full(3, -1, dtype=np.int64),
        move_cumulative(move_weights),
        *work,
        steps,
        T0,
        T1,
        0,
        PENALTY,
        seed,
        best,
        stats,
        best_info,
        cancel,
    )
    if np.isfinite(best_info[0]) and deadline_value(c, best) < late:
        return best
    return owner
