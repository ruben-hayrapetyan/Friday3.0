"""Shared assertions: the kernel's state equals the evaluator's and the checker's view of the same plan."""

from collections import Counter

import numpy as np

from friday.engine.checker import check
from friday.engine.compile import Compiled
from friday.engine.evaluate import evaluate
from friday.engine.kernel import N_MOVES, State, item_violations, seed_rng, total_violations
from friday.engine.moves import add_dependents, propose
from friday.engine.problem import STAGES


def assert_kernel_matches(c: Compiled, st: State) -> None:
    p = c.problem
    plan = c.plan_from_owner(st.owner)
    ev = evaluate(p, plan)
    assert list(st.stage_value) == [ev.stage_values[s] for s in STAGES]
    violations = check(p, plan)
    per_item = Counter(v.key for v in violations if v.code != "day_cap")
    kernel_counts = {c.keys[i]: int(st.item_violations[i]) for i in range(c.m.I) if st.item_violations[i]}
    assert kernel_counts == dict(per_item)
    assert total_violations(c.m, st) == len(violations)


def random_moves(c: Compiled, st: State, steps: int, seed: int, check_every: int = 50,
                 moves: tuple[int, ...] = tuple(range(N_MOVES))) -> np.ndarray:  # fmt: skip
    """Apply moves without walls, keeping every count exact, and compare with the evaluator as it goes."""
    seed_rng(seed)
    touched = np.zeros(64, dtype=np.int64)
    fired = np.zeros(N_MOVES, dtype=int)
    unprotected = np.zeros(c.m.I, dtype=bool)
    for step in range(steps):
        move = moves[step % len(moves)]
        st.counters[0] = 0
        n = propose(c.m, st, unprotected, move, touched)
        if n:
            fired[move] += 1
            n = add_dependents(c.m, touched, n)
            for k in range(n):
                st.item_violations[touched[k]] = item_violations(c.m, st, touched[k])
            st.counters[1] = int(st.item_violations.sum())
        if step % check_every == 0:
            assert_kernel_matches(c, st)
    assert_kernel_matches(c, st)
    return fired
