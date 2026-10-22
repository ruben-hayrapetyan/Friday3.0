"""The Metropolis chain over the kernel (DESIGN §11.8): propose, check walls, accept or undo."""

import numpy as np

from friday.engine.kernel import (
    CANCEL_EVERY,
    copy_into,
    day_violations,
    item_violations,
    kernel,
    total_violations,
    undo,
)
from friday.engine.moves import add_dependents, propose


@kernel
def violation_change(M, st, touched, n, new_counts):
    """Re-count the touched items' violations; returns the change in the item total."""
    change = 0
    for k in range(n):
        i = touched[k]
        v = item_violations(M, st, i)
        new_counts[k] = v
        change += v - st.item_violations[i]
    return change


@kernel
def weighted(sv, weights):
    return weights[0] * sv[0] + weights[1] * sv[1] + weights[2] * sv[2]


@kernel
def pick_move(cumulative):
    r = np.random.random() * cumulative[cumulative.shape[0] - 1]
    move = 0
    while move < cumulative.shape[0] - 1 and r > cumulative[move]:
        move += 1
    return move


@kernel
def breaks_protection(M, st, protected, touched, n):
    """W9: a protected item may never lose units (its slots are already kept on time by may_take)."""
    for k in range(n):
        i = touched[k]
        if protected[i] and M.hard_due[i] and st.placed[i] < M.need[i]:
            return True
    return False


@kernel
def run_chain(
    M,
    st,
    protected,
    weights,
    cap,
    cumulative,
    touched,
    new_counts,
    n_steps,
    T0,
    T1,
    walls,
    penalty,
    seed,
    best_owner,
    stats,
    best_info,
    cancel,
):
    """A Metropolis chain with a geometric schedule from T0 to T1.

    walls = 1: every move that breaks a wall is rejected (the state starts valid).
    walls = 0: each violation costs `penalty` instead, and only valid states can become the best (repair).
    cap[k] ≥ 0 rejects any move raising stage k above it (the lexpolish polish phase).
    stats[move] = (proposed, accepted, rejected by a wall); best_info = (best energy, its step, violations).
    cancel[0] ≠ 0, checked every 50k steps, stops the chain early.
    """
    np.random.seed(seed)
    e_current = weighted(st.stage_value, weights) + penalty * total_violations(M, st)
    best_e = 1e300
    if total_violations(M, st) == 0:
        best_e = weighted(st.stage_value, weights)
        copy_into(best_owner, st.owner)
        best_info[0] = best_e
        best_info[1] = 0
    ratio = (T1 / T0) if T0 > 0 else 1.0
    for step in range(n_steps):
        if step % CANCEL_EVERY == 0 and cancel[0] != 0:
            break
        T = T0 * ratio ** (step / n_steps) if T0 > 0 else 0.0
        move = pick_move(cumulative)
        stats[move, 0] += 1
        st.counters[0] = 0
        old0 = st.stage_value[0]
        old1 = st.stage_value[1]
        old2 = st.stage_value[2]
        old_item_total = st.counters[1]
        n = propose(M, st, protected, move, touched)
        if n == 0:
            st.counters[0] = 0
            continue
        n = add_dependents(M, touched, n)
        item_change = violation_change(M, st, touched, n, new_counts)
        violations = old_item_total + item_change + day_violations(M, st)
        reject = False
        if walls == 1 and (violations > 0 or breaks_protection(M, st, protected, touched, n)):
            reject = True
            stats[move, 2] += 1
        if not reject:
            for k in range(3):
                if cap[k] >= 0 and st.stage_value[k] > cap[k]:
                    reject = True
                    stats[move, 2] += 1
                    break
        if not reject:
            e_new = weighted(st.stage_value, weights) + penalty * violations
            delta = e_new - e_current
            if delta <= 0.0:
                accept = True
            elif T <= 0.0:
                accept = False
            else:
                accept = np.random.random() < np.exp(-delta / T)
            if accept:
                for k in range(n):
                    st.item_violations[touched[k]] = new_counts[k]
                st.counters[1] = old_item_total + item_change
                e_current = e_new
                stats[move, 1] += 1
                if violations == 0:
                    e_valid = weighted(st.stage_value, weights)
                    if e_valid < best_e - 1e-9:
                        best_e = e_valid
                        copy_into(best_owner, st.owner)
                        best_info[0] = e_valid
                        best_info[1] = step
                st.counters[0] = 0
                continue
        undo(M, st)
        st.stage_value[0] = old0
        st.stage_value[1] = old1
        st.stage_value[2] = old2
        st.counters[0] = 0
    best_info[2] = total_violations(M, st)
    return e_current


@kernel
def sample_deltas(M, st, protected, weights, cumulative, touched, new_counts, n, seed, out):
    """Stage changes of n random valid moves from the current state, each undone. Returns how many."""
    np.random.seed(seed)
    k = 0
    for _ in range(n):
        move = pick_move(cumulative)
        st.counters[0] = 0
        o0 = st.stage_value[0]
        o1 = st.stage_value[1]
        o2 = st.stage_value[2]
        moved = propose(M, st, protected, move, touched)
        if moved == 0:
            st.counters[0] = 0
            continue
        moved = add_dependents(M, touched, moved)
        change = violation_change(M, st, touched, moved, new_counts)
        if st.counters[1] + change + day_violations(M, st) == 0:
            out[k, 0] = st.stage_value[0] - o0
            out[k, 1] = st.stage_value[1] - o1
            out[k, 2] = st.stage_value[2] - o2
            k += 1
        undo(M, st)
        st.counters[0] = 0
    return k


@kernel
def tabu(M, st, protected, weights, cap, cumulative, touched, new_counts, n_iters, n_candidates, tenure, seed,
         best_owner, best_info, tabu_until, candidate_move, candidate_seed):  # fmt: skip
    """Tabu search over the same moves (the finish of a large budget, DESIGN §11.8).

    Each iteration draws `n_candidates` moves, replaying each from its own seed, and applies the best valid one
    whose items are not tabu, even when it is worse. A new best is always allowed. best_info[0] holds the best
    energy so far on entry and on return.
    """
    np.random.seed(seed)
    best_e = best_info[0]
    e_current = weighted(st.stage_value, weights)
    for it in range(n_iters):
        for q in range(n_candidates):
            candidate_move[q] = pick_move(cumulative)
            candidate_seed[q] = np.random.randint(1, 2**30)
        best_q = -1
        best_delta = 1e300
        for q in range(n_candidates):
            np.random.seed(candidate_seed[q])
            st.counters[0] = 0
            o0 = st.stage_value[0]
            o1 = st.stage_value[1]
            o2 = st.stage_value[2]
            n = propose(M, st, protected, candidate_move[q], touched)
            if n == 0:
                st.counters[0] = 0
                continue
            n = add_dependents(M, touched, n)
            change = violation_change(M, st, touched, n, new_counts)
            valid = st.counters[1] + change + day_violations(M, st) == 0
            if breaks_protection(M, st, protected, touched, n):
                valid = False
            for k in range(3):
                if cap[k] >= 0 and st.stage_value[k] > cap[k]:
                    valid = False
            e_new = weighted(st.stage_value, weights)
            is_tabu = False
            for k in range(n):
                if tabu_until[touched[k]] > it:
                    is_tabu = True
            if valid and (not is_tabu or e_new < best_e - 1e-9) and e_new - e_current < best_delta:
                best_delta = e_new - e_current
                best_q = q
            undo(M, st)
            st.stage_value[0] = o0
            st.stage_value[1] = o1
            st.stage_value[2] = o2
            st.counters[0] = 0
        if best_q < 0:
            continue
        np.random.seed(candidate_seed[best_q])
        st.counters[0] = 0
        n = propose(M, st, protected, candidate_move[best_q], touched)
        n = add_dependents(M, touched, n)
        change = violation_change(M, st, touched, n, new_counts)
        for k in range(n):
            st.item_violations[touched[k]] = new_counts[k]
            tabu_until[touched[k]] = it + tenure
        st.counters[1] += change
        st.counters[0] = 0
        e_current = weighted(st.stage_value, weights)
        if e_current < best_e - 1e-9:
            best_e = e_current
            copy_into(best_owner, st.owner)
            best_info[1] = it
    best_info[0] = best_e
