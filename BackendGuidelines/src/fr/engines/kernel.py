"""Numba kernel: incremental energy, hard-rule violation counts and chunk-level moves.

State (all arrays, mutated in place):
  owner[s]   item index or -1
  placed[i]  units placed
  mval[m]    value of measure m's linear expression
  cnt[g]     members of `any` group g that are occupied
  sv[k]      stage values (deadlines, wellbeing, preferences), exact integers
  dayu[d]    units placed on planning day d
  vitem[i]   cached hard-violation count of item i (same count as `check()` reports)

Moves are built from `set_owner` calls and logged so they can be undone.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numba import njit

from .compile import Model


class State(NamedTuple):
    owner: np.ndarray
    placed: np.ndarray
    mval: np.ndarray
    cnt: np.ndarray
    sv: np.ndarray
    dayu: np.ndarray
    vitem: np.ndarray
    log_s: np.ndarray
    log_old: np.ndarray
    ctr: np.ndarray  # [0]=log length, [1]=sum of vitem


N_MOVES = 8
MOVE_NAMES = ("shift", "swap", "grow", "shrink", "transfer", "split", "merge", "far")


def new_state(M: Model) -> State:
    return State(
        np.full(M.S, -1, dtype=np.int16), np.zeros(M.I, dtype=np.int64), np.zeros(M.M, dtype=np.int64),
        np.zeros(M.G, dtype=np.int64), np.zeros(3, dtype=np.int64), np.zeros(M.D, dtype=np.int64),
        np.zeros(M.I, dtype=np.int64), np.zeros(4096, dtype=np.int64), np.zeros(4096, dtype=np.int64),
        np.zeros(4, dtype=np.int64),
    )


# ------------------------------------------------------------------ energy bookkeeping


@njit(cache=True)
def mcost(M, m, v):
    c = 0
    for h in range(M.h_ptr[m], M.h_ptr[m + 1]):
        d = v - M.h_theta[h] if M.h_dir[h] == 0 else M.h_theta[h] - v
        if d > 0:
            c += M.h_coef[h] * d
    return c


@njit(cache=True)
def bump(M, st, m, dv):
    if dv == 0:
        return
    old = st.mval[m]
    new = old + dv
    st.mval[m] = new
    st.sv[M.m_stage[m]] += mcost(M, m, new) - mcost(M, m, old)


@njit(cache=True)
def start_val(M, owner, i, t):
    if i < 0 or t < 0 or t >= M.S:
        return 0
    if owner[t] != i:
        return 0
    if t > 0 and owner[t - 1] == i:
        return 0
    return 1


@njit(cache=True)
def _over(M, i, placed):
    if M.kind[i] != 0:
        return 0
    return max(0, M.need[i] - placed)


@njit(cache=True)
def _placed_changed(M, st, i, old_placed, new_placed):
    do = _over(M, i, new_placed) - _over(M, i, old_placed)
    if do == 0:
        return
    for k in range(3):
        st.sv[k] += M.over_cost[k, i] * do
    for e in range(M.ov_ptr[i], M.ov_ptr[i + 1]):
        bump(M, st, M.ov_m[e], M.ov_c[e] * do)


@njit(cache=True)
def _x_off(M, st, i, s):
    """Item i leaves slot s (owner[s] is updated by the caller)."""
    W = M.S + 1
    idx = i * W + s
    u = M.units[s]
    for k in range(3):
        st.sv[k] -= M.price[k, i, s]
    for e in range(M.x_ptr[idx], M.x_ptr[idx + 1]):
        bump(M, st, M.x_m[e], -M.x_c[e])
    for e in range(M.ag_ptr[idx], M.ag_ptr[idx + 1]):
        g = M.ag_g[e]
        st.cnt[g] -= 1
        if st.cnt[g] == 0:
            for f in range(M.any_ptr[g], M.any_ptr[g + 1]):
                bump(M, st, M.any_m[f], -M.any_c[f])
    op = st.placed[i]
    st.placed[i] = op - u
    _placed_changed(M, st, i, op, op - u)
    st.dayu[M.day[s]] -= u


@njit(cache=True)
def _x_on(M, st, i, s):
    W = M.S + 1
    idx = i * W + s
    u = M.units[s]
    for k in range(3):
        st.sv[k] += M.price[k, i, s]
    for e in range(M.x_ptr[idx], M.x_ptr[idx + 1]):
        bump(M, st, M.x_m[e], M.x_c[e])
    for e in range(M.ag_ptr[idx], M.ag_ptr[idx + 1]):
        g = M.ag_g[e]
        st.cnt[g] += 1
        if st.cnt[g] == 1:
            for f in range(M.any_ptr[g], M.any_ptr[g + 1]):
                bump(M, st, M.any_m[f], M.any_c[f])
    op = st.placed[i]
    st.placed[i] = op + u
    _placed_changed(M, st, i, op, op + u)
    st.dayu[M.day[s]] += u


@njit(cache=True)
def _apply_start(M, st, i, t, before, after):
    if before == after or i < 0 or t < 0 or t >= M.S:
        return
    idx = i * (M.S + 1) + t
    for e in range(M.st_ptr[idx], M.st_ptr[idx + 1]):
        bump(M, st, M.st_m[e], (after - before) * M.st_c[e])


@njit(cache=True)
def set_owner(M, st, s, new):
    """Give slot s to item `new` (-1 frees it), keep every running total exact, and log the change."""
    old = st.owner[s]
    if old == new:
        return
    n = st.ctr[0]
    st.log_s[n] = s
    st.log_old[n] = old
    st.ctr[0] = n + 1
    b_old_s = start_val(M, st.owner, old, s)
    b_old_n = start_val(M, st.owner, old, s + 1)
    b_new_s = start_val(M, st.owner, new, s)
    b_new_n = start_val(M, st.owner, new, s + 1)
    if old >= 0:
        _x_off(M, st, old, s)
    st.owner[s] = new
    if new >= 0:
        _x_on(M, st, new, s)
    _apply_start(M, st, old, s, b_old_s, start_val(M, st.owner, old, s))
    _apply_start(M, st, old, s + 1, b_old_n, start_val(M, st.owner, old, s + 1))
    _apply_start(M, st, new, s, b_new_s, start_val(M, st.owner, new, s))
    _apply_start(M, st, new, s + 1, b_new_n, start_val(M, st.owner, new, s + 1))


@njit(cache=True)
def undo(M, st):
    n = st.ctr[0]
    while n > 0:
        n -= 1
        s = st.log_s[n]
        old = st.log_old[n]
        # restore without logging: temporarily set the counter so the log entry is overwritten
        st.ctr[0] = n
        set_owner(M, st, s, old)
        st.ctr[0] = n
    st.ctr[0] = 0


@njit(cache=True)
def init_state(M, st, owner):
    """Empty state -> the plan in `owner`, built slot by slot."""
    st.owner[:] = -1
    st.placed[:] = 0
    st.cnt[:] = 0
    st.sv[:] = 0
    st.dayu[:] = 0
    # mval holds the whole expression value, so it starts at the constant
    for m in range(M.M):
        st.mval[m] = M.m_const[m]
        st.sv[M.m_stage[m]] += mcost(M, m, M.m_const[m])
    for i in range(M.I):
        o = _over(M, i, 0)
        if o != 0:
            for k in range(3):
                st.sv[k] += M.over_cost[k, i] * o
            for e in range(M.ov_ptr[i], M.ov_ptr[i + 1]):
                bump(M, st, M.ov_m[e], M.ov_c[e] * o)
    st.ctr[0] = 0
    for s in range(M.S):
        if owner[s] >= 0:
            set_owner(M, st, s, owner[s])
    st.ctr[0] = 0
    recompute_violations(M, st)


# ------------------------------------------------------------------ hard-rule violations (same count as check())


@njit(cache=True)
def item_viol(M, st, i):
    owner = st.owner
    v = 0
    placed = 0
    runs = 0
    run_units = 0
    coarse = False
    prev = False
    kind = M.kind[i]
    day_units = 0
    cur_day = -1
    first_free_slot = -1
    for s in range(M.lo[i], M.hi[i] + 2):
        here = s <= M.hi[i] and owner[s] == i
        if here:
            u = M.units[s]
            placed += u
            if u > 1:
                coarse = True
            if prev:
                run_units += u
            else:
                runs += 1
                run_units = u
            if first_free_slot < 0 and not M.locked[i, s]:
                first_free_slot = s
            if kind == 3:
                d = M.day[s]
                if d != cur_day:
                    if cur_day >= 0:
                        c = M.ceil0[i] if cur_day == 0 else M.ceil[i]
                        if day_units > c:
                            v += 1
                    cur_day = d
                    day_units = 0
                day_units += u
            prev = True
        else:
            if prev:
                if run_units < M.min_chunk[i]:
                    v += 1
                if M.max_chunk[i] >= 0 and run_units > M.max_chunk[i]:
                    v += 1
            prev = False
    if kind == 3 and cur_day >= 0:
        c = M.ceil0[i] if cur_day == 0 else M.ceil[i]
        if day_units > c:
            v += 1
    if kind == 0:
        if placed > M.need[i] and (placed > M.need[i] + 1 or not coarse):
            v += 1
    elif kind == 1 or kind == 2:
        if placed > M.amount_cap[i]:
            v += 1
    if M.one_sit[i]:
        if runs > 1:
            v += 1
        if kind == 0 and placed > 0 and placed < M.need[i]:
            v += 1
    # dependencies: the first unlocked slot decides (lag_slot is non-decreasing in the slot)
    for d in range(M.dep_ptr[i], M.dep_ptr[i + 1]):
        if first_free_slot < 0:
            continue
        src = M.dep_src[d]
        req = M.dep_req[d]
        acc = 0
        t_ready = M.S + 5
        for s in range(M.lo[src], M.hi[src] + 1):
            if owner[s] == src:
                acc += M.units[s]
                if acc >= req:
                    t_ready = s + 1
                    break
        if M.dep_lag[d, first_free_slot] < t_ready:
            v += 1
    return v


@njit(cache=True)
def day_viol(M, st):
    v = 0
    for d in range(M.D):
        if st.dayu[d] > M.day_cap[d]:
            v += 1
    return v


@njit(cache=True)
def recompute_violations(M, st):
    tot = 0
    for i in range(M.I):
        st.vitem[i] = item_viol(M, st, i)
        tot += st.vitem[i]
    st.ctr[1] = tot


@njit(cache=True)
def total_violations(M, st):
    return st.ctr[1] + day_viol(M, st)


# ------------------------------------------------------------------ move helpers


@njit(cache=True)
def ok_slot(M, prot, i, t):
    if t < 0 or t >= M.S:
        return False
    if prot[i]:
        return M.wall_ok[i, t]
    return M.allowed[i, t]


@njit(cache=True)
def pick_slot(M, st):
    for _ in range(40):
        s = np.random.randint(0, M.S)
        o = st.owner[s]
        if o >= 0 and not M.locked[o, s]:
            return s
    return -1


@njit(cache=True)
def run_around(M, st, s):
    i = st.owner[s]
    a = s
    b = s
    while a - 1 >= 0 and st.owner[a - 1] == i and not M.locked[i, a - 1]:
        a -= 1
    while b + 1 < M.S and st.owner[b + 1] == i and not M.locked[i, b + 1]:
        b += 1
    return a, b


@njit(cache=True)
def free_for(M, st, prot, i, a, b, c, d):
    """May item i occupy slots c..d, given it currently holds a..b (which it vacates)?"""
    for t in range(c, d + 1):
        if not ok_slot(M, prot, i, t):
            return False
        o = st.owner[t]
        if o != -1 and not (a <= t <= b and o == i):
            return False
    return True


@njit(cache=True)
def move_slots(M, st, i, a, b, c):
    """Move item i's slots a..b so that they start at c."""
    for t in range(a, b + 1):
        set_owner(M, st, t, -1)
    for t in range(b - a + 1):
        set_owner(M, st, c + t, i)


@njit(cache=True)
def propose(M, st, prot, kind_ix, touched):
    """Apply one random move of the given type. Returns the number of touched items (0 = nothing proposed)."""
    S = M.S
    s = pick_slot(M, st)
    if s < 0:
        return 0
    i = st.owner[s]
    a, b = run_around(M, st, s)
    L = b - a + 1
    nt = 0
    if kind_ix == 0:  # shift a chunk by a few slots
        dlt = np.random.randint(1, 5)
        if np.random.random() < 0.5:
            dlt = -dlt
        c = a + dlt
        if c < 0 or c + L - 1 >= S or not free_for(M, st, prot, i, a, b, c, c + L - 1):
            return 0
        move_slots(M, st, i, a, b, c)
        touched[0] = i
        return 1
    if kind_ix == 7:  # far shift: a uniformly random start inside the item's window
        lo = M.lo[i]
        hi = M.hi[i] - L + 1
        if hi < lo:
            return 0
        c = np.random.randint(lo, hi + 1)
        if c == a or not free_for(M, st, prot, i, a, b, c, c + L - 1):
            return 0
        move_slots(M, st, i, a, b, c)
        touched[0] = i
        return 1
    if kind_ix == 1:  # swap two chunks of equal length
        s2 = pick_slot(M, st)
        if s2 < 0:
            return 0
        j = st.owner[s2]
        if j == i:
            return 0
        c, d = run_around(M, st, s2)
        if d - c != b - a:
            return 0
        for t in range(L):
            if not ok_slot(M, prot, i, c + t) or not ok_slot(M, prot, j, a + t):
                return 0
        for t in range(L):
            set_owner(M, st, a + t, -1)
            set_owner(M, st, c + t, -1)
        for t in range(L):
            set_owner(M, st, a + t, j)
            set_owner(M, st, c + t, i)
        touched[0] = i
        touched[1] = j
        return 2
    if kind_ix == 2:  # grow a chunk by one slot
        if np.random.random() < 0.5:
            t = a - 1
        else:
            t = b + 1
        if t < 0 or t >= S or st.owner[t] != -1 or not ok_slot(M, prot, i, t):
            return 0
        set_owner(M, st, t, i)
        touched[0] = i
        return 1
    if kind_ix == 3:  # shrink a chunk by one slot (the item loses a unit)
        t = a if np.random.random() < 0.5 else b
        if prot[i] and M.hard_due[i] and st.placed[i] - M.units[t] < M.need[i]:
            return 0
        set_owner(M, st, t, -1)
        touched[0] = i
        return 1
    if kind_ix == 4:  # move one slot between two chunks of the same item (amount is kept when units match)
        t1 = a if np.random.random() < 0.5 else b
        for _ in range(12):
            s2 = np.random.randint(M.lo[i], M.hi[i] + 1)
            if st.owner[s2] != i or M.locked[i, s2] or (a <= s2 <= b):
                continue
            c, d = run_around(M, st, s2)
            t2 = c - 1 if np.random.random() < 0.5 else d + 1
            if t2 < 0 or t2 >= S or st.owner[t2] != -1 or not ok_slot(M, prot, i, t2):
                continue
            if M.units[t2] != M.units[t1]:
                continue
            set_owner(M, st, t1, -1)
            set_owner(M, st, t2, i)
            touched[0] = i
            return 1
        return 0
    if kind_ix == 5:  # split: lift one end slot to a random free place
        t1 = a if np.random.random() < 0.5 else b
        for _ in range(8):
            t2 = np.random.randint(M.lo[i], M.hi[i] + 1)
            if st.owner[t2] != -1 or not ok_slot(M, prot, i, t2) or M.units[t2] != M.units[t1]:
                continue
            set_owner(M, st, t1, -1)
            set_owner(M, st, t2, i)
            touched[0] = i
            return 1
        return 0
    if kind_ix == 6:  # merge: move the chunk next to another chunk of the same item
        for _ in range(12):
            s2 = np.random.randint(M.lo[i], M.hi[i] + 1)
            if st.owner[s2] != i or (a <= s2 <= b):
                continue
            c, d = run_around(M, st, s2)
            if np.random.random() < 0.5:
                tgt = d + 1
            else:
                tgt = c - L
            if tgt < 0 or tgt + L - 1 >= S or tgt == a:
                continue
            if not free_for(M, st, prot, i, a, b, tgt, tgt + L - 1):
                continue
            move_slots(M, st, i, a, b, tgt)
            touched[0] = i
            return 1
        return 0
    return nt


@njit(cache=True)
def add_touched_dependents(M, touched, n):
    """Items that wait on a touched item need their violations re-checked too."""
    m = n
    for k in range(n):
        i = touched[k]
        for e in range(M.dnt_ptr[i], M.dnt_ptr[i + 1]):
            j = M.dnt_dst[e]
            seen = False
            for q in range(m):
                if touched[q] == j:
                    seen = True
            if not seen and m < touched.shape[0]:
                touched[m] = j
                m += 1
    return m


@njit(cache=True)
def violation_delta(M, st, touched, n, newv):
    """Recompute violations of the touched items; returns the change in the total (items only)."""
    delta = 0
    for k in range(n):
        i = touched[k]
        v = item_viol(M, st, i)
        newv[k] = v
        delta += v - st.vitem[i]
    return delta


@njit(cache=True)
def scalar(sv, wts):
    return wts[0] * sv[0] + wts[1] * sv[1] + wts[2] * sv[2]


@njit(cache=True)
def run_chain(M, st, prot, wts, probs, n_steps, T0, T1, wall, lam, seed, best_owner, stats, best_info):
    """Metropolis chain with a geometric schedule T0 -> T1.

    wall = 1: reject every move that leaves the hard-feasible set (the state starts feasible).
    wall = 0: violations cost `lam` each (a penalty), and only violation-free states can be 'best'.
    stats[k] = (proposed, accepted, rejected_hard); best_info = (best energy, step of best, violations of best).
    """
    np.random.seed(seed)
    touched = np.zeros(64, dtype=np.int64)
    newv = np.zeros(64, dtype=np.int64)
    cum = np.cumsum(probs)
    e_cur = scalar(st.sv, wts) + lam * total_violations(M, st)
    best_e = 1e300
    if total_violations(M, st) == 0:
        best_e = scalar(st.sv, wts)
        best_owner[:] = st.owner
        best_info[0] = best_e
        best_info[1] = 0
    ratio = (T1 / T0) if T0 > 0 else 1.0
    for step in range(n_steps):
        T = T0 * ratio ** (step / n_steps) if T0 > 0 else 0.0
        r = np.random.random() * cum[cum.shape[0] - 1]
        kx = 0
        while kx < cum.shape[0] - 1 and r > cum[kx]:
            kx += 1
        stats[kx, 0] += 1
        st.ctr[0] = 0
        old_sv0 = st.sv[0]
        old_sv1 = st.sv[1]
        old_sv2 = st.sv[2]
        old_vtot_items = st.ctr[1]
        nt = propose(M, st, prot, kx, touched)
        if nt == 0:
            st.ctr[0] = 0
            continue
        nt = add_touched_dependents(M, touched, nt)
        dv_items = violation_delta(M, st, touched, nt, newv)
        vtot_new = old_vtot_items + dv_items + day_viol(M, st)
        reject = False
        if wall == 1:
            if vtot_new > 0:
                reject = True
                stats[kx, 2] += 1
            else:
                for k in range(nt):
                    i = touched[k]
                    if prot[i] and M.hard_due[i] and st.placed[i] < M.need[i]:
                        reject = True
                        stats[kx, 2] += 1
                        break
        if not reject:
            e_new = wts[0] * st.sv[0] + wts[1] * st.sv[1] + wts[2] * st.sv[2] + lam * vtot_new
            d = e_new - e_cur
            if d <= 0.0:
                acc = True
            elif T <= 0.0:
                acc = False
            else:
                acc = np.random.random() < np.exp(-d / T)
            if acc:
                for k in range(nt):
                    st.vitem[touched[k]] = newv[k]
                st.ctr[1] = old_vtot_items + dv_items
                e_cur = e_new
                stats[kx, 1] += 1
                if vtot_new == 0:
                    e_s = scalar(st.sv, wts)
                    if e_s < best_e - 1e-9:
                        best_e = e_s
                        best_owner[:] = st.owner
                        best_info[0] = e_s
                        best_info[1] = step
                st.ctr[0] = 0
                continue
        undo(M, st)
        st.sv[0] = old_sv0
        st.sv[1] = old_sv1
        st.sv[2] = old_sv2
        st.ctr[0] = 0
    best_info[2] = total_violations(M, st)
    return e_cur
