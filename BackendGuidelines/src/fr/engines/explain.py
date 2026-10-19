"""Explanations (RQ9): per-rule energy of a plan, and "why not elsewhere" as an exact energy difference."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .compile import Compiled
from .kernel import (add_touched_dependents, init_state, item_viol, new_state, relocate, rule_totals, run_around,
                     total_violations, day_viol)


def per_rule(c: Compiled, owner: np.ndarray) -> dict[str, int]:
    M = c.m
    out = np.zeros(M.R, dtype=np.int64)
    rule_totals(M, owner, out, np.zeros(M.M, dtype=np.int64), np.zeros(max(M.G, 1), dtype=np.int64),
                np.zeros(M.I, dtype=np.int64))
    return {n: int(out[k]) for k, n in enumerate(c.rule_names)}


@dataclass
class WhyNot:
    valid: bool  # False: the alternative breaks a hard rule (a wall), so it was never an option
    delta: dict[str, int]  # per rule: energy(alternative) - energy(plan); > 0 means the alternative costs more
    total: int

    def reasons(self, k: int = 3) -> list[tuple[str, int]]:
        return sorted(((n, d) for n, d in self.delta.items() if d), key=lambda x: -abs(x[1]))[:k]


def why_not(c: Compiled, owner: np.ndarray, slot: int, new_start: int) -> WhyNot:
    """Move the chunk that holds `slot` so it starts at `new_start` (same units) and report the exact difference."""
    M = c.m
    st = new_state(M)
    init_state(M, st, owner)
    before = per_rule(c, owner)
    i = int(owner[slot])
    a, b = run_around(M, st, slot)
    touched = np.zeros(64, dtype=np.int64)
    prot = np.zeros(M.I, dtype=bool)
    st.ctr[0] = 0
    if not relocate(M, st, prot, i, a, b, new_start, touched):
        return WhyNot(False, {}, 0)
    n = add_touched_dependents(M, touched, 1)
    for k in range(n):
        st.vitem[touched[k]] = item_viol(M, st, touched[k])
    st.ctr[1] = int(st.vitem.sum())
    valid = total_violations(M, st) == 0
    after = per_rule(c, st.owner)
    delta = {k: after[k] - before[k] for k in before}
    return WhyNot(bool(valid), delta, sum(delta.values()))
