"""Meals kept on a packed week (C92). Priya's week skipped 5–13 hours' worth of meals depending on the seed (every
week-two lunch and dinner on some): `meals_first`, which clears a meal's spot and puts the work back elsewhere, ran
only when work was late and only for meals a deadlines rule keeps, and its repair, counting lateness alone, took the
meals back out. Now it runs for meals a wellbeing rule keeps too, late work or not, its repair counts meals a little
(MEALS_KEPT), and a fresh plan starts from several starts, the chains shared among them."""

import numpy as np
import pytest

from friday.engine.compile import compile_problem
from friday.engine.repair import DEADLINES_ONLY, MEALS_KEPT
from friday.engine.sampler import anneal
from friday.engine.scheduler import meals_first, stage_values
from tests.engine.configs import fast
from tests.engine.helpers import at, item, problem

MEAL_RULE = [dict(type="elastic_shortfall", name="elastic_minimum", stage="wellbeing", params=dict(steep=20, gentle=0))]


def lunch_week():  # noqa: ANN201
    """10:00–14:00 in quarter hours (16 slots): lunch may go 12:00–13:00; 2 hours of work due 14:00."""
    lunch = item("routine", 1, title="Lunch", min_units=2, ideal_units=2, max_units=3,
                 release_utc=at(0, "12:00"), due_utc=at(0, "13:00"))  # fmt: skip
    work = item("assignment", 2, duration_units=8, due_utc=at(0, "14:00"), importance=3)
    return compile_problem(problem([lunch, work], ["late_work"], MEAL_RULE, slots=16))


def owners(c, **slots: list[int]) -> np.ndarray:  # noqa: ANN001
    owner = np.full(c.m.S, -1, dtype=np.int16)
    for key, where in slots.items():
        owner[where] = c.keys.index(key.replace("item_", "item:"))
    return owner


# Glass box


def test_a_meal_a_wellbeing_rule_keeps_is_placed_first_even_with_nothing_late() -> None:
    c = lunch_week()
    lunch = c.problem.items["item:1"]
    assert lunch.meal_window is not None and lunch.min == 2
    window = sorted(lunch.allowed)
    # the work sits right across lunch's window, with room before it; nothing is late, so this never ran before
    start = owners(c, item_2=[s for s in range(c.m.S) if s >= 6][:8])
    assert stage_values(c, start)[0] == 0
    fed = meals_first(c, start, fast(), np.zeros(1, dtype=np.int64))
    assert fed is not None
    held = int(sum(c.m.units[s] for s in range(c.m.S) if fed[s] == c.keys.index("item:1")))
    assert held >= lunch.min and all(fed[s] != c.keys.index("item:1") or s in window for s in range(c.m.S))
    assert stage_values(c, fed)[0] == 0 and stage_values(c, fed) < stage_values(c, start)  # work still on time


def test_nothing_comes_back_when_the_meals_already_have_their_time() -> None:
    c = lunch_week()
    start = owners(c, item_1=[8, 9], item_2=list(range(0, 8)))
    assert meals_first(c, start, fast(), np.zeros(1, dtype=np.int64)) is None


def test_the_meal_step_s_repair_counts_meals_far_below_any_lateness() -> None:
    assert DEADLINES_ONLY[1] == 0 and 0 < MEALS_KEPT[1] * 1000 < 1 and MEALS_KEPT[0] == 1  # a skipped meal ~0.1
    assert MEALS_KEPT[2] == 0


def test_chains_take_the_starts_in_turn_and_one_start_is_all_of_them() -> None:
    c = lunch_week()
    a = owners(c, item_1=[8, 9], item_2=list(range(0, 8)))
    b = owners(c, item_1=[10, 11], item_2=list(range(2, 10)))
    guard = np.zeros(c.m.I, dtype=bool)
    config = fast(chains=4).sampler
    shared = anneal(c, [a, b], [guard, guard], config, steps=0, warm=True, warm_t0=0.0)
    alone = anneal(c, a, guard, config, steps=0, warm=True, warm_t0=0.0)
    by_index = {o.index: o.owner for o in shared}
    assert np.array_equal(by_index[0], a) and np.array_equal(by_index[1], b) and np.array_equal(by_index[2], a)
    assert all(np.array_equal(o.owner, a) for o in alone)


# Black box: Priya's packed week, as the Cornell scenario plans it


@pytest.fixture(scope="module")
def priya_report() -> dict:
    import json
    import os
    import tempfile
    from pathlib import Path

    from friday.planner.service import replan
    from friday.sim.first_evening import open_student
    from friday.sim.students import STUDENTS
    from tests.scenarios.test_cornell import NOW

    os.environ.setdefault("FRIDAY_CONFIG", str(Path(tempfile.mkdtemp()) / "friday.toml"))
    conn = open_student(Path(tempfile.mkdtemp()) / "friday.db", STUDENTS["priya"], NOW)
    replan(conn, NOW)
    row = conn.execute("SELECT stage_values, report FROM plans WHERE status = 'current'").fetchone()
    return json.loads(row[1]) | {"stage_values": json.loads(row[0])}


def test_priya_s_packed_fortnight_skips_no_meal(priya_report: dict) -> None:
    assert priya_report["stage_values"]["deadlines"] == 0
    assert priya_report["rule_totals"].get("elastic_minimum", 0) == 0  # 12,000 before: twelve meals skipped
