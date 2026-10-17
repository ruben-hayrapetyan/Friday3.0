"""Constructive start plan: items in earliest-deadline order, each into the earliest free slots.

Respects locks, windows, the daily cap, minimum/maximum chunks, one-sitting items and dependencies.
Hard-deadline items use only on-time slots first and spill into late slots only when nothing else is left,
so a plan that comes back with every hard item on time is a certificate, and one that does not tells the
caller which items need repair. Elastic, target and open items start empty; the sampler adds them.
"""
from __future__ import annotations

import math

import numpy as np

from .compile import Compiled


def _ready_slot_ok(M, owner, i):
    """Per dependency: the first slot index at which the dependent may start, or None if the source is short."""
    conds = []
    for d in range(M.dep_ptr[i], M.dep_ptr[i + 1]):
        src, req = int(M.dep_src[d]), int(M.dep_req[d])
        acc, t_ready = 0, None
        for s in range(M.lo[src], M.hi[src] + 1):
            if owner[s] == src:
                acc += int(M.units[s])
                if acc >= req:
                    t_ready = s + 1
                    break
        if t_ready is None:
            return None
        conds.append((d, t_ready))
    return conds


def construct(c: Compiled, order: str = "edf") -> np.ndarray:
    M, p = c.m, c.problem
    ix = {k: i for i, k in enumerate(c.keys)}
    owner = np.full(M.S, -1, dtype=np.int16)
    dayu = np.zeros(M.D, dtype=np.int64)
    placed = np.zeros(M.I, dtype=np.int64)
    for s, k in p.lock_owner.items():
        owner[s] = ix[k]
        dayu[M.day[s]] += M.units[s]
        placed[ix[k]] += M.units[s]

    due = np.array([p.items[k].due if p.items[k].due is not None else 10**12 for k in c.keys], dtype=np.float64)
    eff = due.copy()
    for _ in range(M.I):
        changed = False
        for j in range(M.I):
            for d in range(M.dep_ptr[j], M.dep_ptr[j + 1]):
                src = M.dep_src[d]
                if eff[j] < eff[src]:
                    eff[src] = eff[j]
                    changed = True
        if not changed:
            break
    hard = np.array([bool(M.hard_due[i]) or eff[i] < due[i] for i in range(M.I)])
    imp = np.array([p.items[k].importance for k in c.keys])
    prio = sorted(range(M.I), key=lambda i: (0 if hard[i] else 1, eff[i], -imp[i], i))
    if order == "importance":
        prio = sorted(range(M.I), key=lambda i: (-imp[i], eff[i], i))

    todo = [i for i in prio if M.kind[i] == 0 and placed[i] < M.need[i]]
    pending = list(todo)
    done: set[int] = set()
    guard = 0
    while pending and guard < 4 * M.I + 10:
        guard += 1
        for i in list(pending):
            deps_ok = all((int(M.dep_src[d]) in done) or M.kind[M.dep_src[d]] != 0 or placed[M.dep_src[d]] >= M.need[M.dep_src[d]]
                          or (M.dep_src[d] not in pending) for d in range(M.dep_ptr[i], M.dep_ptr[i + 1]))
            if not deps_ok:
                continue
            _place(M, owner, dayu, placed, i)
            done.add(i)
            pending.remove(i)
            break
        else:
            # cyclic or blocked: place the rest in priority order anyway
            for i in list(pending):
                _place(M, owner, dayu, placed, i)
                pending.remove(i)
    return owner


def _slot_lists(M, i, strict: bool):
    ok = M.wall_ok[i] if strict else M.allowed[i]
    return [s for s in range(M.lo[i], M.hi[i] + 1) if ok[s]]


def _extend_locked(M, owner, dayu, placed, i, remaining) -> int:
    """A one-sitting item with locked slots must grow out of the locked run, not start a second chunk."""
    held = [s for s in range(M.lo[i], M.hi[i] + 1) if owner[s] == i]
    lo, hi = held[0], held[-1]
    got = 0
    for step, rng in ((1, range(hi + 1, M.S)), (-1, range(lo - 1, -1, -1))):
        for s in rng:
            if got >= remaining or owner[s] != -1:
                break
            if not M.allowed[i, s] or dayu[M.day[s]] + M.units[s] > M.day_cap[M.day[s]]:
                break
            owner[s] = i
            dayu[M.day[s]] += M.units[s]
            placed[i] += M.units[s]
            got += int(M.units[s])
        if got >= remaining:
            break
    return got


def _place(M, owner, dayu, placed, i) -> None:
    remaining = int(M.need[i] - placed[i])
    if remaining <= 0:
        return
    if M.one_sit[i] and placed[i] > 0:
        _extend_locked(M, owner, dayu, placed, i, remaining)
        return
    conds = _ready_slot_ok(M, owner, i)
    if conds is None:
        return
    for strict in ((True, False) if M.hard_due[i] else (False,)):
        cand = [s for s in _slot_lists(M, i, strict)
                if owner[s] == -1 and all(M.dep_lag[d, s] >= tr for d, tr in conds)]
        got = _take(M, owner, dayu, placed, i, cand, remaining)
        remaining -= got
        if remaining <= 0:
            return


def _take(M, owner, dayu, placed, i, cand, remaining) -> int:
    """Write up to `remaining` units for item i into candidate slots; returns units written."""
    mn = int(M.min_chunk[i])
    mx = int(M.max_chunk[i])
    taken = 0
    if M.one_sit[i]:
        run: list[int] = []
        for s in cand + [-1]:
            if run and (s != run[-1] + 1):
                if _run_ok(M, dayu, run, remaining):
                    take = _prefix_for(M, run, remaining)
                    if mx < 0 or sum(int(M.units[t]) for t in take) <= mx:
                        return _write(M, owner, dayu, placed, i, take)
                run = []
            if s >= 0:
                run.append(s)
        return 0
    run = []
    for s in cand + [-1]:
        if run and s != run[-1] + 1:
            taken += _take_run(M, owner, dayu, placed, i, run, remaining - taken, mn, mx)
            run = []
            if remaining - taken <= 0:
                break
        if s >= 0:
            run.append(s)
    return taken


def _run_ok(M, dayu, run, need) -> bool:
    return sum(int(M.units[t]) for t in run) >= need and _day_ok(M, dayu, _prefix_for(M, run, need))


def _day_ok(M, dayu, slots) -> bool:
    add: dict[int, int] = {}
    for t in slots:
        add[int(M.day[t])] = add.get(int(M.day[t]), 0) + int(M.units[t])
    return all(dayu[d] + a <= M.day_cap[d] for d, a in add.items())


def _prefix_for(M, run, units) -> list[int]:
    out, acc = [], 0
    for t in run:
        if acc >= units:
            break
        out.append(t)
        acc += int(M.units[t])
    return out


def _take_run(M, owner, dayu, placed, i, run, remaining, mn, mx) -> int:
    """Fill a run of consecutive free slots with chunks of legal size, one planning day at a time."""
    pieces, cur = [], []
    for t in run:
        if cur and M.day[t] != M.day[cur[-1]]:
            pieces.append(cur)
            cur = []
        cur.append(t)
    pieces.append(cur)
    total = 0
    for piece in pieces:
        pos = 0
        while pos < len(piece) and remaining - total > 0:
            left = remaining - total
            d = M.day[piece[pos]]
            room = int(M.day_cap[d] - dayu[d])
            take, units = [], 0
            for t in piece[pos:]:
                u = int(M.units[t])
                if units >= left or units + u > room:
                    break
                take.append(t)
                units += u
            if mx >= 0 and units > mx:
                take, units = _cut(M, take, mx)
            if 0 < left - units < mn:  # leave a legal remainder
                take, units = _cut(M, take, left - mn)
            if units < mn or not take:
                pos += max(1, len(take))
                continue
            total += _write(M, owner, dayu, placed, i, take)
            pos += len(take) + 1  # a free slot between chunks keeps them from merging
    return total


def _cut(M, take, limit):
    out, acc = [], 0
    for t in take:
        if acc + int(M.units[t]) > limit:
            break
        out.append(t)
        acc += int(M.units[t])
    return out, acc


def _write(M, owner, dayu, placed, i, slots) -> int:
    n = 0
    for t in slots:
        owner[t] = i
        dayu[M.day[t]] += M.units[t]
        placed[i] += M.units[t]
        n += int(M.units[t])
    return n
