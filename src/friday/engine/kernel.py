"""The numba kernel: plan state, exact incremental energy and wall checks (DESIGN §11.3–11.5).

The 11 moves live in `moves.py` and the chain that proposes and accepts them in `chain.py`.

State, all arrays mutated in place:
  owner[s]              item index or −1 (W1 holds by construction)
  placed[i]             units placed
  measure_value[m]      value of measure m's linear expression
  group_count[g]        occupied members of any-of group g
  stage_value[k]        exact integer stage values: deadlines, wellbeing, preferences
  day_units[d]          units placed on planning day d
  item_violations[i]    cached wall-violation count of item i, the same count `check()` gives
  log_slot, log_owner   every owner change of the current move, so it can be undone
  counters              [0] log length, [1] sum of item_violations

This is flat array code for speed: the one place functions run long. Every move is built from `set_owner`
calls, which keep all totals exact, and a move that breaks a wall is undone by the chain.
"""

from typing import NamedTuple

import numpy as np
from numba import njit

from friday.engine.compile import Model

# Without numba's reference-counting runtime, helper calls are 10–15× cheaper (research report §5).
kernel = njit(cache=True, nogil=True, _nrt=False)

SHIFT, SWAP, GROW, SHRINK, TRANSFER, SPLIT, MERGE, FAR_SHIFT, INSERT, DROP, EJECT = range(11)
MOVE_NAMES = (
    "shift",
    "swap",
    "grow",
    "shrink",
    "transfer",
    "split",
    "merge",
    "far_shift",
    "insert",
    "drop",
    "eject",
)
N_MOVES = len(MOVE_NAMES)
LOG_SIZE = 4096
CANCEL_EVERY = 50_000


class State(NamedTuple):
    owner: np.ndarray
    placed: np.ndarray
    measure_value: np.ndarray
    group_count: np.ndarray
    stage_value: np.ndarray
    day_units: np.ndarray
    item_violations: np.ndarray
    log_slot: np.ndarray
    log_owner: np.ndarray
    counters: np.ndarray


def new_state(M: Model) -> State:
    return State(
        np.full(M.S, -1, dtype=np.int16),
        np.zeros(M.I, dtype=np.int64),
        np.zeros(M.M, dtype=np.int64),
        np.zeros(M.G, dtype=np.int64),
        np.zeros(3, dtype=np.int64),
        np.zeros(M.D, dtype=np.int64),
        np.zeros(M.I, dtype=np.int64),
        np.zeros(LOG_SIZE, dtype=np.int64),
        np.zeros(LOG_SIZE, dtype=np.int64),
        np.zeros(4, dtype=np.int64),
    )


def move_cumulative(weights: dict[str, float]) -> np.ndarray:
    """Cumulative move weights in kernel order, for picking a move."""
    return np.cumsum(np.array([weights[name] for name in MOVE_NAMES], dtype=np.float64))


@kernel
def copy_into(dst, src):
    for q in range(dst.shape[0]):
        dst[q] = src[q]


@kernel
def seed_rng(seed):
    np.random.seed(seed)


@kernel
def measure_cost(M, m, value):
    cost = 0
    for h in range(M.h_ptr[m], M.h_ptr[m + 1]):
        excess = value - M.h_theta[h] if M.h_dir[h] == 0 else M.h_theta[h] - value
        if excess > 0:
            cost += M.h_coef[h] * excess
    return cost


@kernel
def bump(M, st, m, change):
    if change == 0:
        return
    old = st.measure_value[m]
    new = old + change
    st.measure_value[m] = new
    st.stage_value[M.m_stage[m]] += measure_cost(M, m, new) - measure_cost(M, m, old)


@kernel
def starts_chunk(M, owner, i, t):
    """1 when slot t begins a chunk of item i."""
    if i < 0 or t < 0 or t >= M.S:
        return 0
    if owner[t] != i:
        return 0
    if t > 0 and owner[t - 1] == i:
        return 0
    return 1


@kernel
def overflow(M, i, placed):
    if M.amount_kind[i] != 0:
        return 0
    return max(0, M.need[i] - placed)


@kernel
def placed_changed(M, st, i, old_placed, new_placed):
    change = overflow(M, i, new_placed) - overflow(M, i, old_placed)
    if change == 0:
        return
    for k in range(3):
        st.stage_value[k] += M.over_cost[k, i] * change
    for e in range(M.ov_ptr[i], M.ov_ptr[i + 1]):
        bump(M, st, M.ov_m[e], M.ov_c[e] * change)


@kernel
def leave_slot(M, st, i, s):
    """Item i leaves slot s; the caller updates owner[s]."""
    idx = i * (M.S + 1) + s
    u = M.units[s]
    for k in range(3):
        st.stage_value[k] -= M.price[k, i, s]
    for e in range(M.x_ptr[idx], M.x_ptr[idx + 1]):
        bump(M, st, M.x_m[e], -M.x_c[e])
    for e in range(M.ag_ptr[idx], M.ag_ptr[idx + 1]):
        g = M.ag_g[e]
        st.group_count[g] -= 1
        if st.group_count[g] == 0:
            for f in range(M.any_ptr[g], M.any_ptr[g + 1]):
                bump(M, st, M.any_m[f], -M.any_c[f])
    old = st.placed[i]
    st.placed[i] = old - u
    placed_changed(M, st, i, old, old - u)
    st.day_units[M.day[s]] -= u


@kernel
def enter_slot(M, st, i, s):
    idx = i * (M.S + 1) + s
    u = M.units[s]
    for k in range(3):
        st.stage_value[k] += M.price[k, i, s]
    for e in range(M.x_ptr[idx], M.x_ptr[idx + 1]):
        bump(M, st, M.x_m[e], M.x_c[e])
    for e in range(M.ag_ptr[idx], M.ag_ptr[idx + 1]):
        g = M.ag_g[e]
        st.group_count[g] += 1
        if st.group_count[g] == 1:
            for f in range(M.any_ptr[g], M.any_ptr[g + 1]):
                bump(M, st, M.any_m[f], M.any_c[f])
    old = st.placed[i]
    st.placed[i] = old + u
    placed_changed(M, st, i, old, old + u)
    st.day_units[M.day[s]] += u


@kernel
def apply_start_change(M, st, i, t, before, after):
    if before == after or i < 0 or t < 0 or t >= M.S:
        return
    idx = i * (M.S + 1) + t
    for e in range(M.st_ptr[idx], M.st_ptr[idx + 1]):
        bump(M, st, M.st_m[e], (after - before) * M.st_c[e])


@kernel
def set_owner(M, st, s, new):
    """Give slot s to item `new` (−1 frees it), keep every total exact, and log the change."""
    old = st.owner[s]
    if old == new:
        return
    n = st.counters[0]
    st.log_slot[n] = s
    st.log_owner[n] = old
    st.counters[0] = n + 1
    old_here = starts_chunk(M, st.owner, old, s)
    old_next = starts_chunk(M, st.owner, old, s + 1)
    new_here = starts_chunk(M, st.owner, new, s)
    new_next = starts_chunk(M, st.owner, new, s + 1)
    if old >= 0:
        leave_slot(M, st, old, s)
    st.owner[s] = new
    if new >= 0:
        enter_slot(M, st, new, s)
    # A chunk start can change at s and at the slot after it, for both owners.
    apply_start_change(M, st, old, s, old_here, starts_chunk(M, st.owner, old, s))
    apply_start_change(M, st, old, s + 1, old_next, starts_chunk(M, st.owner, old, s + 1))
    apply_start_change(M, st, new, s, new_here, starts_chunk(M, st.owner, new, s))
    apply_start_change(M, st, new, s + 1, new_next, starts_chunk(M, st.owner, new, s + 1))


@kernel
def undo(M, st):
    n = st.counters[0]
    while n > 0:
        n -= 1
        # Restoring reuses set_owner, which logs; pointing the counter at this entry overwrites it.
        st.counters[0] = n
        set_owner(M, st, st.log_slot[n], st.log_owner[n])
        st.counters[0] = n
    st.counters[0] = 0


@kernel
def init_state(M, st, owner):
    """Empty state → the plan in `owner`, slot by slot."""
    st.owner[:] = -1
    st.placed[:] = 0
    st.group_count[:] = 0
    st.stage_value[:] = 0
    st.day_units[:] = 0
    for m in range(M.M):
        st.measure_value[m] = M.m_const[m]
        st.stage_value[M.m_stage[m]] += measure_cost(M, m, M.m_const[m])
    for i in range(M.I):
        missing = overflow(M, i, 0)
        if missing != 0:
            for k in range(3):
                st.stage_value[k] += M.over_cost[k, i] * missing
            for e in range(M.ov_ptr[i], M.ov_ptr[i + 1]):
                bump(M, st, M.ov_m[e], M.ov_c[e] * missing)
    st.counters[0] = 0
    for s in range(M.S):
        if owner[s] >= 0:
            set_owner(M, st, s, owner[s])
    st.counters[0] = 0
    recompute_violations(M, st)


@kernel
def item_violations(M, st, i):
    """W2–W4, W6–W8 for item i. W1 holds by construction, W5 is per day, W9 is checked by the chain."""
    owner = st.owner
    count = 0
    placed = 0
    chunks = 0
    chunk_units = 0
    has_coarse = False
    in_chunk = False
    kind = M.amount_kind[i]
    units_today = 0
    current_day = -1
    first_unlocked = -1
    for s in range(M.first_slot[i], M.last_slot[i] + 2):
        here = s <= M.last_slot[i] and owner[s] == i
        if here:
            u = M.units[s]
            placed += u
            if u > 1:
                has_coarse = True
            if in_chunk:
                chunk_units += u
            else:
                chunks += 1
                chunk_units = u
            if first_unlocked < 0 and not M.locked[i, s]:
                first_unlocked = s
            if kind == 3:
                d = M.day[s]
                if d != current_day:
                    if current_day >= 0:
                        limit = M.ceiling_day0[i] if current_day == 0 else M.ceiling[i]
                        if units_today > limit:
                            count += 1
                    current_day = d
                    units_today = 0
                units_today += u
            in_chunk = True
        else:
            if in_chunk:
                if chunk_units < M.min_chunk[i]:
                    count += 1
                if M.max_chunk[i] >= 0 and chunk_units > M.max_chunk[i]:
                    count += 1
            in_chunk = False
    if kind == 3 and current_day >= 0:
        limit = M.ceiling_day0[i] if current_day == 0 else M.ceiling[i]
        if units_today > limit:
            count += 1
    if kind == 0:
        if placed > M.need[i] and (placed > M.need[i] + 1 or not has_coarse):
            count += 1
    elif (kind == 1 or kind == 2) and placed > M.amount_cap[i]:
        count += 1
    if M.one_sitting[i]:
        if chunks > 1:
            count += 1
        if kind == 0 and placed > 0 and placed < M.need[i]:
            count += 1
    # The first unlocked slot decides each dependency, because the lag slot never decreases.
    for d in range(M.dep_ptr[i], M.dep_ptr[i + 1]):
        if first_unlocked < 0:
            continue
        source = M.dep_source[d]
        done = 0
        ready_at = M.S + 5
        for s in range(M.first_slot[source], M.last_slot[source] + 1):
            if owner[s] == source:
                done += M.units[s]
                if done >= M.dep_required[d]:
                    ready_at = s + 1
                    break
        if M.dep_lag[d, first_unlocked] < ready_at:
            count += 1
    return count


@kernel
def day_violations(M, st):
    count = 0
    for d in range(M.D):
        if st.day_units[d] > M.day_cap[d]:
            count += 1
    return count


@kernel
def recompute_violations(M, st):
    total = 0
    for i in range(M.I):
        st.item_violations[i] = item_violations(M, st, i)
        total += st.item_violations[i]
    st.counters[1] = total


@kernel
def total_violations(M, st):
    return st.counters[1] + day_violations(M, st)


@kernel
def rule_totals(M, owner, out, values, counts, placed):
    """Every rule's cost of the plan in `owner`, from scratch, into out[R]; equals evaluate().rule_totals.

    values[M], counts[G] and placed[I] are work arrays.
    """
    W = M.S + 1
    for r in range(M.R):
        out[r] = 0
    for m in range(M.M):
        values[m] = M.m_const[m]
    for g in range(M.G):
        counts[g] = 0
    for i in range(M.I):
        placed[i] = 0
    for s in range(M.S):
        i = owner[s]
        if i < 0:
            continue
        idx = i * W + s
        placed[i] += M.units[s]
        for r in range(M.R):
            out[r] += M.rule_price[r, i, s]
        for e in range(M.x_ptr[idx], M.x_ptr[idx + 1]):
            values[M.x_m[e]] += M.x_c[e]
        if s == 0 or owner[s - 1] != i:
            for e in range(M.st_ptr[idx], M.st_ptr[idx + 1]):
                values[M.st_m[e]] += M.st_c[e]
        for e in range(M.ag_ptr[idx], M.ag_ptr[idx + 1]):
            counts[M.ag_g[e]] += 1
    for g in range(M.G):
        if counts[g] > 0:
            for f in range(M.any_ptr[g], M.any_ptr[g + 1]):
                values[M.any_m[f]] += M.any_c[f]
    for i in range(M.I):
        missing = overflow(M, i, placed[i])
        if missing != 0:
            for r in range(M.R):
                out[r] += M.rule_over[r, i] * missing
            for e in range(M.ov_ptr[i], M.ov_ptr[i + 1]):
                values[M.ov_m[e]] += M.ov_c[e] * missing
    for m in range(M.M):
        out[M.m_rule[m]] += measure_cost(M, m, values[m])


def protected_items(M: Model, owner: np.ndarray) -> np.ndarray:
    """W9: hard-deadline items that are complete and on time in `owner`; walls keep them that way."""
    placed = np.zeros(M.I, dtype=np.int64)
    on_time = np.ones(M.I, dtype=bool)
    for s in range(M.S):
        i = owner[s]
        if i >= 0:
            placed[i] += M.units[s]
            if not M.on_time[i, s]:
                on_time[i] = False
    return M.hard_due & on_time & (placed >= M.need)
