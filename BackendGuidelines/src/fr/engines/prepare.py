"""Problem -> compiled model + a hard-feasible start plan when one can be built, relaxing contradictory locks."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..baseline.cpsat import demote_locks
from ..core.problem import Problem
from .compile import Compiled, compile_problem
from .construct import construct
from .kernel import init_state, new_state, total_violations


@dataclass
class Prepared:
    c: Compiled
    owner: np.ndarray  # construct() plan
    violations: int  # hard violations left in it (0 = a valid start)
    demoted: list[str] = field(default_factory=list)


def prepare(problem: Problem, max_rounds: int = 3) -> Prepared:
    demoted: list[str] = []
    for _ in range(max_rounds + 1):
        c = compile_problem(problem)
        owner = construct(c)
        st = new_state(c.m)
        init_state(c.m, st, owner)
        bad = [c.keys[i] for i in range(c.m.I) if st.vitem[i] > 0 and c.m.locked[i].any()]
        if not bad or len(demoted) >= len(c.keys):
            return Prepared(c, owner, int(total_violations(c.m, st)), demoted)
        demote_locks(problem, bad)
        demoted += bad
    return Prepared(c, owner, int(total_violations(c.m, st)), demoted)
