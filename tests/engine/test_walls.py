"""No move the chain accepts ever breaks a wall, and a protected item never becomes late (DESIGN §11.4)."""

import numpy as np
import pytest

from friday.core.settings import DEFAULT_MOVE_WEIGHTS
from friday.engine.chain import run_chain
from friday.engine.checker import check
from friday.engine.compile import compile_problem
from friday.engine.kernel import N_MOVES, init_state, move_cumulative, new_state, protected_items, total_violations
from tests.engine.golden import plan_of, problem, read

HOT = 1e12  # every valid move is accepted, so the walls are the only thing that rejects
WEIGHTS = np.array([1e6, 1e3, 1.0])

# Fixtures whose constructed start plans are valid and that stress the walls in question.
CASES = {
    "W1 W2 W3 locks and allowed slots": "pins-s0",
    "W4 amounts of elastic, target and open items": "cornell-push",
    "W5 daily cap under overload": "overload-s1",
    "W6 one-sitting items": "onesit-s1",
    "W7 chunk lengths in fragmented time": "fragmented-s1",
    "W8 dependency chains": "deps-s1",
    "W9 tight deadlines": "tight-s1",
    "everything at once": "cornell-extra-s1",
}


def hot_batches(name: str, seed: int, batches: int = 30, steps: int = 400):  # noqa: ANN201
    fixture = read(name)
    p = problem(fixture)
    c = compile_problem(p)
    start = c.owner_from_plan(plan_of(fixture["plans"][0], p))
    protected = protected_items(c.m, start)
    st = new_state(c.m)
    init_state(c.m, st, start)
    assert total_violations(c.m, st) == 0
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    work = (np.zeros(64, dtype=np.int64), np.zeros(64, dtype=np.int64))
    protected_keys = [c.keys[i] for i in range(c.m.I) if protected[i]]
    for batch in range(batches):
        run_chain(c.m, st, protected, WEIGHTS, np.full(3, -1, dtype=np.int64), move_cumulative(DEFAULT_MOVE_WEIGHTS),
                  *work, steps, HOT, HOT, 1, 0.0, seed * 1000 + batch, st.owner.copy(), stats, np.zeros(3),
                  np.zeros(1, dtype=np.int64))  # fmt: skip
        yield p, c.plan_from_owner(st.owner), protected_keys, stats


@pytest.mark.parametrize("case", list(CASES))
def test_no_accepted_move_breaks_a_wall(case: str) -> None:
    stats = None
    for p, plan, protected, stats in hot_batches(CASES[case], seed=1):  # noqa: B007
        assert check(p, plan, protected) == []
    assert stats is not None
    assert stats[:, 1].sum() > 0, "nothing was accepted, so the test proved nothing"
    assert stats[:, 2].sum() > 0, "no wall ever had to reject a move"


def test_protected_items_exist_in_the_tight_case() -> None:
    p = problem(read("tight-s1"))
    c = compile_problem(p)
    start = c.owner_from_plan(plan_of(read("tight-s1")["plans"][0], p))
    assert protected_items(c.m, start).sum() >= 6


def test_a_protected_item_is_never_made_late_even_when_lateness_is_cheap() -> None:
    # With the deadline stage weighted 0, nothing but the wall keeps protected items on time.
    fixture = read("tight-s0")
    p = problem(fixture)
    c = compile_problem(p)
    start = c.owner_from_plan(plan_of(fixture["plans"][0], p))
    protected = protected_items(c.m, start)
    st = new_state(c.m)
    init_state(c.m, st, start)
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    run_chain(
        c.m,
        st,
        protected,
        np.array([0.0, 1.0, 1.0]),
        np.full(3, -1, dtype=np.int64),
        move_cumulative(DEFAULT_MOVE_WEIGHTS),
        np.zeros(64, dtype=np.int64),
        np.zeros(64, dtype=np.int64),
        20_000,
        HOT,
        HOT,
        1,
        0.0,
        3,
        st.owner.copy(),
        stats,
        np.zeros(3),
        np.zeros(1, dtype=np.int64),
    )
    keys = [c.keys[i] for i in range(c.m.I) if protected[i]]
    assert check(p, c.plan_from_owner(st.owner), keys) == []


def test_a_set_cancel_flag_stops_the_chain_before_its_next_block_of_steps() -> None:
    fixture = read("ref20-s0")
    p = problem(fixture)
    c = compile_problem(p)
    st = new_state(c.m)
    init_state(c.m, st, c.owner_from_plan(plan_of(fixture["plans"][0], p)))
    stats = np.zeros((N_MOVES, 3), dtype=np.int64)
    run_chain(
        c.m,
        st,
        np.zeros(c.m.I, dtype=bool),
        WEIGHTS,
        np.full(3, -1, dtype=np.int64),
        move_cumulative(DEFAULT_MOVE_WEIGHTS),
        np.zeros(64, dtype=np.int64),
        np.zeros(64, dtype=np.int64),
        200_000,
        1.0,
        1.0,
        1,
        0.0,
        0,
        st.owner.copy(),
        stats,
        np.zeros(3),
        np.ones(1, dtype=np.int64),
    )
    assert stats[:, 0].sum() == 0
