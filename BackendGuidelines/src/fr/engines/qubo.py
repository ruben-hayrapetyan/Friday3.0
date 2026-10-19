"""Strict QUBO / Boltzmann-machine formulation of the price-only slice of the problem.

Binary unit x[i, s] = item i occupies slot s, plus slack bits that turn "placed <= need" into an equality.
Every hard rule is a penalty: A for two items in one slot, B for exceeding an item's amount. Hinge measures,
chunk rules, dependencies and one-sitting items are not expressible with pairwise terms (they need helper bits
or higher-order terms), so this works on instances built only from price rules. That limit is itself a finding.

E(x) = sum_a h_a x_a + sum_{a<b} J_ab x_a x_b + const, J symmetric with a zero diagonal.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit

from ..core.problem import Problem


@dataclass
class Qubo:
    J: np.ndarray
    h: np.ndarray
    const: float
    index: list[tuple[int, int]]  # (item index, slot) per unit; slack units have slot -1
    keys: tuple
    n_slot_units: int
    A: float
    B: float

    @property
    def n(self) -> int:
        return len(self.h)


def build_qubo(problem: Problem, A: float, B: float) -> Qubo:
    g = problem.grid
    keys = tuple(problem.items)
    price = np.zeros((len(keys), g.S + 1))
    over = np.zeros(len(keys))
    from ..core.rules import price_row

    for rule in problem.rules:
        if not rule.has_price:
            continue
        for it in problem.items.values():
            if rule.applies(it):
                row = price_row(problem, rule, it)
                i = keys.index(it.key)
                price[i, : g.S] += row[: g.S]
                if it.amount == "fixed":
                    over[i] += row[g.S]
    index: list[tuple[int, int]] = []
    pos: dict[tuple[int, int], int] = {}
    for i, k in enumerate(keys):
        for s in problem.items[k].allowed:
            pos[(i, s)] = len(index)
            index.append((i, s))
    n_slot = len(index)
    slack: dict[int, list[int]] = {}
    for i, k in enumerate(keys):
        it = problem.items[k]
        if it.amount != "fixed":
            raise ValueError("the QUBO slice has fixed-amount items only")
        bits = max(1, int(it.need).bit_length())
        slack[i] = list(range(len(index), len(index) + bits))
        index += [(i, -1)] * bits
    n = len(index)
    J = np.zeros((n, n))
    h = np.zeros(n)
    const = 0.0
    by_slot: dict[int, list[int]] = {}
    for (i, s), a in pos.items():
        by_slot.setdefault(s, []).append(a)
        h[a] += price[i, s] - over[i] * g.units[s]
    const += float(sum(over[i] * problem.items[k].need for i, k in enumerate(keys)))
    for members in by_slot.values():
        for p in range(len(members)):
            for q in range(p + 1, len(members)):
                J[members[p], members[q]] += A
                J[members[q], members[p]] += A
    for i, k in enumerate(keys):
        it = problem.items[k]
        terms = [(pos[(i, s)], float(g.units[s])) for s in it.allowed] + [(a, float(2 ** b)) for b, a in enumerate(slack[i])]
        const += B * it.need**2
        for a, ca in terms:
            h[a] += B * (ca * ca - 2 * it.need * ca)
        for p in range(len(terms)):
            for q in range(p + 1, len(terms)):
                v = 2 * B * terms[p][1] * terms[q][1]
                J[terms[p][0], terms[q][0]] += v
                J[terms[q][0], terms[p][0]] += v
    return Qubo(J, h, const, index, keys, n_slot, A, B)


def qubo_energy(q: Qubo, x: np.ndarray) -> float:
    return float(q.h @ x + 0.5 * x @ q.J @ x + q.const)


@njit(cache=True, _nrt=False)
def qubo_sa(J, h, x, f, steps, T0, T1, seed, best_x, info, greedy):
    """Single-flip Metropolis on the QUBO with local fields. greedy=1 accepts only improving flips (a Hopfield descent)."""
    np.random.seed(seed)
    n = h.shape[0]
    for a in range(n):
        s = h[a]
        for b in range(n):
            if x[b] > 0:
                s += J[a, b]
        f[a] = s
    e = 0.0
    for a in range(n):
        if x[a] > 0:
            e += h[a] + 0.5 * (f[a] - h[a])
    best = e
    for a in range(n):
        best_x[a] = x[a]
    ratio = (T1 / T0) if T0 > 0 else 1.0
    acc = 0
    for step in range(steps):
        T = T0 * ratio ** (step / steps) if T0 > 0 else 0.0
        a = np.random.randint(0, n)
        d = (1 - 2 * x[a]) * f[a]
        if d <= 0.0 or (greedy == 0 and T > 0.0 and np.random.random() < np.exp(-d / T)):
            sgn = 1 - 2 * x[a]
            x[a] = 1 - x[a]
            for b in range(n):
                f[b] += sgn * J[b, a]
            e += d
            acc += 1
            if e < best - 1e-9:
                best = e
                for b in range(n):
                    best_x[b] = x[b]
    info[0] = best
    info[1] = acc
    info[2] = e


def decode(q: Qubo, x: np.ndarray) -> dict[str, tuple[int, ...]]:
    out: dict[str, list[int]] = {k: [] for k in q.keys}
    for a in range(q.n_slot_units):
        if x[a] > 0:
            i, s = q.index[a]
            out[q.keys[i]].append(s)
    return {k: tuple(sorted(v)) for k, v in out.items()}
