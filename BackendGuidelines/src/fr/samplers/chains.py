"""Sampler variants for P4 (RQ4): schedules, acceptance rules, parallel tempering, population annealing, tabu, multi-start.

All share the kernel's moves and incremental energy. Chains release the GIL, so replicas run on several cores
from Python threads; every chain seeds its own (thread-local) generator, so results do not depend on scheduling.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from numba import njit

from ..engines.compile import Compiled
from ..engines.kernel import (N_MOVES, State, add_touched_dependents, copy_into, day_viol, init_state, new_state,
                              propose, total_violations, undo, violation_delta)
from .anneal import DEFAULT_PROBS

GEOMETRIC, LINEAR, CONSTANT = 0, 1, 2
METROPOLIS, HEATBATH = 0, 1


@njit(cache=True, _nrt=False, nogil=True)
def chain(M, st, prot, wts, cap, cum, touched, newv, n_steps, T0, T1, schedule, accept_rule, wall, lam, seed,
          best_owner, stats, info):
    """A Metropolis / heat-bath chain. info = (best energy, step of best, final energy, accepted)."""
    np.random.seed(seed)
    vt = total_violations(M, st)
    e_cur = wts[0] * st.sv[0] + wts[1] * st.sv[1] + wts[2] * st.sv[2] + lam * vt
    best_e = info[0]
    if vt == 0 and e_cur < best_e:
        best_e = e_cur
        copy_into(best_owner, st.owner)
        info[1] = 0
    acc_n = 0
    for step in range(n_steps):
        f = step / n_steps
        if schedule == GEOMETRIC:
            T = T0 * (T1 / T0) ** f
        elif schedule == LINEAR:
            T = T0 + (T1 - T0) * f
        else:
            T = T0
        r = np.random.random() * cum[cum.shape[0] - 1]
        kx = 0
        while kx < cum.shape[0] - 1 and r > cum[kx]:
            kx += 1
        stats[kx, 0] += 1
        st.ctr[0] = 0
        o0, o1, o2 = st.sv[0], st.sv[1], st.sv[2]
        old_items = st.ctr[1]
        nt = propose(M, st, prot, kx, touched)
        if nt == 0:
            st.ctr[0] = 0
            continue
        nt = add_touched_dependents(M, touched, nt)
        dv = violation_delta(M, st, touched, nt, newv)
        vnew = old_items + dv + day_viol(M, st)
        ok = True
        if wall == 1:
            if vnew > 0:
                ok = False
            else:
                for k in range(nt):
                    i = touched[k]
                    if prot[i] and M.hard_due[i] and st.placed[i] < M.need[i]:
                        ok = False
        for k in range(3):
            if cap[k] >= 0 and st.sv[k] > cap[k]:
                ok = False
        if not ok:
            stats[kx, 2] += 1
        else:
            e_new = wts[0] * st.sv[0] + wts[1] * st.sv[1] + wts[2] * st.sv[2] + lam * vnew
            d = e_new - e_cur
            if accept_rule == METROPOLIS:
                acc = d <= 0.0 or (T > 0.0 and np.random.random() < np.exp(-d / T))
            else:  # heat bath (Glauber): p = 1 / (1 + exp(d / T))
                if T <= 0.0:
                    acc = d < 0.0
                else:
                    x = d / T
                    acc = x < -50.0 or (x < 50.0 and np.random.random() < 1.0 / (1.0 + np.exp(x)))
            if acc:
                for k in range(nt):
                    st.vitem[touched[k]] = newv[k]
                st.ctr[1] = old_items + dv
                e_cur = e_new
                acc_n += 1
                stats[kx, 1] += 1
                if vnew == 0 and e_new < best_e - 1e-9:
                    best_e = e_new
                    copy_into(best_owner, st.owner)
                    info[1] = step
                st.ctr[0] = 0
                continue
        undo(M, st)
        st.sv[0] = o0
        st.sv[1] = o1
        st.sv[2] = o2
        st.ctr[0] = 0
    info[0] = best_e
    info[2] = e_cur
    info[3] = acc_n


@njit(cache=True, _nrt=False, nogil=True)
def tabu(M, st, prot, wts, cap, cum, touched, newv, n_iters, k_cand, tenure, seed, best_owner, info, tabu_until,
         cand_kind, cand_seed):
    """Tabu search over the same moves: each iteration samples k_cand moves (replaying each from its own seed), applies
    the best one whose items are not tabu (aspiration: a new best is always allowed), even if it is worse."""
    np.random.seed(seed)
    best_e = info[0]
    e_cur = wts[0] * st.sv[0] + wts[1] * st.sv[1] + wts[2] * st.sv[2]
    for it in range(n_iters):
        for q in range(k_cand):
            r = np.random.random() * cum[cum.shape[0] - 1]
            kx = 0
            while kx < cum.shape[0] - 1 and r > cum[kx]:
                kx += 1
            cand_kind[q] = kx
            cand_seed[q] = np.random.randint(1, 2 ** 30)
        best_q = -1
        best_d = 1e300
        for q in range(k_cand):
            np.random.seed(cand_seed[q])
            st.ctr[0] = 0
            o0, o1, o2 = st.sv[0], st.sv[1], st.sv[2]
            nt = propose(M, st, prot, cand_kind[q], touched)
            if nt == 0:
                st.ctr[0] = 0
                continue
            nt = add_touched_dependents(M, touched, nt)
            dv = violation_delta(M, st, touched, nt, newv)
            ok = st.ctr[1] + dv + day_viol(M, st) == 0
            for k in range(nt):
                i = touched[k]
                if prot[i] and M.hard_due[i] and st.placed[i] < M.need[i]:
                    ok = False
            for k in range(3):
                if cap[k] >= 0 and st.sv[k] > cap[k]:
                    ok = False
            e_new = wts[0] * st.sv[0] + wts[1] * st.sv[1] + wts[2] * st.sv[2]
            is_tabu = False
            for k in range(nt):
                if tabu_until[touched[k]] > it:
                    is_tabu = True
            if ok and (not is_tabu or e_new < best_e - 1e-9) and e_new - e_cur < best_d:
                best_d = e_new - e_cur
                best_q = q
            undo(M, st)
            st.sv[0] = o0
            st.sv[1] = o1
            st.sv[2] = o2
            st.ctr[0] = 0
        if best_q < 0:
            continue
        np.random.seed(cand_seed[best_q])
        st.ctr[0] = 0
        nt = propose(M, st, prot, cand_kind[best_q], touched)
        nt = add_touched_dependents(M, touched, nt)
        dv = violation_delta(M, st, touched, nt, newv)
        for k in range(nt):
            st.vitem[touched[k]] = newv[k]
            tabu_until[touched[k]] = it + tenure
        st.ctr[1] += dv
        st.ctr[0] = 0
        e_cur = wts[0] * st.sv[0] + wts[1] * st.sv[1] + wts[2] * st.sv[2]
        if e_cur < best_e - 1e-9:
            best_e = e_cur
            copy_into(best_owner, st.owner)
            info[1] = it
    info[0] = best_e
    info[2] = e_cur
    np.random.seed(seed + 1)


# ------------------------------------------------------------------ Python drivers


@dataclass
class Replica:
    st: State
    best: np.ndarray
    stats: np.ndarray
    info: np.ndarray
    touched: np.ndarray = field(default_factory=lambda: np.zeros(64, dtype=np.int64))
    newv: np.ndarray = field(default_factory=lambda: np.zeros(64, dtype=np.int64))

    @staticmethod
    def make(c: Compiled, owner: np.ndarray) -> "Replica":
        st = new_state(c.m)
        init_state(c.m, st, owner)
        info = np.array([np.inf, -1.0, 0.0, 0.0])
        return Replica(st, owner.copy(), np.zeros((N_MOVES, 3), dtype=np.int64), info)

    def energy(self, wts) -> float:
        return float(wts @ self.st.sv)


@dataclass
class Spec:
    """What one tier optimises: stage weights, an optional cap per stage, walls or a penalty."""
    wts: np.ndarray
    cap: tuple[int, int, int] = (-1, -1, -1)
    wall: bool = True
    lam: float = 0.0
    probs: np.ndarray = field(default_factory=lambda: DEFAULT_PROBS.copy())


def run(c: Compiled, rep: Replica, prot, spec: Spec, steps: int, T0: float, T1: float, seed: int,
        schedule: int = GEOMETRIC, accept: int = METROPOLIS) -> None:
    chain(c.m, rep.st, prot, spec.wts.astype(np.float64), np.array(spec.cap, dtype=np.int64), np.cumsum(spec.probs),
          rep.touched, rep.newv, int(steps), float(T0), float(T1), schedule, accept, 1 if spec.wall else 0,
          float(spec.lam), int(seed), rep.best, rep.stats, rep.info)


def parallel_tempering(c: Compiled, owner: np.ndarray, prot, spec: Spec, temps: np.ndarray, rounds: int,
                       steps_per_round: int, seed: int, threads: int = 1, anneal_ladder: float = 1.0):
    """Replica k runs at temps[k] (ascending). After each round neighbours try to swap with the usual
    min(1, exp((E_i - E_j)(1/T_i - 1/T_j))) rule. anneal_ladder < 1 shrinks the whole ladder geometrically per round."""
    rng = np.random.default_rng(seed)
    reps = [Replica.make(c, owner) for _ in temps]
    ladder = np.array(temps, dtype=np.float64)
    swaps = np.zeros((len(temps) - 1, 2), dtype=np.int64)
    pool = ThreadPoolExecutor(threads) if threads > 1 else None
    for rd in range(rounds):
        jobs = [(reps[k], ladder[k], seed * 1000 + rd * len(temps) + k) for k in range(len(temps))]
        if pool:
            list(pool.map(lambda a: run(c, a[0], prot, spec, steps_per_round, a[1], a[1], a[2], CONSTANT), jobs))
        else:
            for a in jobs:
                run(c, a[0], prot, spec, steps_per_round, a[1], a[1], a[2], CONSTANT)
        for k in range(rd % 2, len(temps) - 1, 2):
            ei, ej = reps[k].energy(spec.wts), reps[k + 1].energy(spec.wts)
            arg = (ei - ej) * (1.0 / ladder[k] - 1.0 / ladder[k + 1])
            swaps[k, 0] += 1
            if arg >= 0 or rng.random() < np.exp(arg):
                reps[k], reps[k + 1] = reps[k + 1], reps[k]
                swaps[k, 1] += 1
        ladder *= anneal_ladder
    if pool:
        pool.shutdown()
    best = min(reps, key=lambda r: r.info[0])
    return best.best.copy(), float(best.info[0]), swaps, reps


def population_annealing(c: Compiled, owner: np.ndarray, prot, spec: Spec, n_pop: int, T0: float, T1: float,
                         n_temps: int, steps_per_temp: int, seed: int, threads: int = 1):
    """Population annealing: at each temperature step, resample the population with weights exp(-(b' - b) E), then let
    every member run a short chain at the new temperature."""
    rng = np.random.default_rng(seed)
    temps = T0 * (T1 / T0) ** (np.arange(n_temps) / max(1, n_temps - 1))
    reps = [Replica.make(c, owner) for _ in range(n_pop)]
    pool = ThreadPoolExecutor(threads) if threads > 1 else None
    for k, T in enumerate(temps):
        if k > 0:
            e = np.array([r.energy(spec.wts) for r in reps])
            w = -(1.0 / T - 1.0 / temps[k - 1]) * (e - e.min())
            w = np.exp(w - w.max())
            w /= w.sum()
            idx = rng.choice(n_pop, size=n_pop, p=w)
            owners = [reps[i].st.owner.copy() for i in idx]
            olds = [reps[i] for i in idx]
            reps = []
            for o, old in zip(owners, olds):
                r = Replica.make(c, o)
                r.best[:] = old.best
                r.info[:] = old.info
                reps.append(r)
        jobs = [(reps[j], seed * 100_000 + k * n_pop + j) for j in range(n_pop)]
        if pool:
            list(pool.map(lambda a: run(c, a[0], prot, spec, steps_per_temp, T, T, a[1], CONSTANT), jobs))
        else:
            for a in jobs:
                run(c, a[0], prot, spec, steps_per_temp, T, T, a[1], CONSTANT)
    if pool:
        pool.shutdown()
    best = min(reps, key=lambda r: r.info[0])
    return best.best.copy(), float(best.info[0]), reps


def multistart(c: Compiled, owner: np.ndarray, prot, spec: Spec, n: int, steps: int, T0: float, T1: float, seed: int,
               threads: int = 1):
    reps = [Replica.make(c, owner) for _ in range(n)]
    jobs = [(reps[j], seed * 7919 + j) for j in range(n)]
    if threads > 1:
        with ThreadPoolExecutor(threads) as pool:
            list(pool.map(lambda a: run(c, a[0], prot, spec, steps, T0, T1, a[1]), jobs))
    else:
        for a in jobs:
            run(c, a[0], prot, spec, steps, T0, T1, a[1])
    best = min(reps, key=lambda r: r.info[0])
    return best.best.copy(), float(best.info[0]), reps


def run_tabu(c: Compiled, rep: Replica, prot, spec: Spec, iters: int, k_cand: int, tenure: int, seed: int) -> None:
    tabu(c.m, rep.st, prot, spec.wts.astype(np.float64), np.array(spec.cap, dtype=np.int64), np.cumsum(spec.probs),
         rep.touched, rep.newv, int(iters), int(k_cand), int(tenure), int(seed), rep.best, rep.info,
         np.zeros(c.m.I, dtype=np.int64), np.zeros(k_cand, dtype=np.int64), np.zeros(k_cand, dtype=np.int64))
