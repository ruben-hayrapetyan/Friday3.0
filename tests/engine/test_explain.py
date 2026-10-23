"""Explanations are exact: block costs add up to the evaluator's totals, why-not equals the evaluator's
difference, and a forbidden alternative names its wall."""

import numpy as np
import pytest

from friday.engine.checker import check
from friday.engine.construct import prepare_start
from friday.engine.evaluate import evaluate
from friday.engine.explain import OTHER, block_costs, blocks_of, per_rule, why_not
from friday.engine.kernel import init_state, new_state
from friday.engine.moves import chunk_around, relocate
from friday.engine.scheduler import schedule
from friday.planner.build import Dependency, Pin
from tests.engine.configs import fast
from tests.engine.helpers import MON10, at, item, problem
from tests.engine.instances import variant


@pytest.mark.parametrize("name", ["ref20", "dst-fine", "extra", "mixed", "overload", "deps"])
def test_block_costs_and_the_rest_add_up_to_every_rule_total(name: str) -> None:
    p = variant(name)
    result = schedule(p, fast(steps=10_000, fallback=False))
    per_block, other = block_costs(p, result.plan, blocks_of(result.plan))
    for rule, total in result.evaluation.rule_totals.items():
        assert sum(b.get(rule, 0) for b in per_block) + other.get(rule, 0) == total, rule
    assert OTHER  # the name the planner reports unplaced cost under


def test_why_not_is_exactly_the_evaluators_difference() -> None:
    p = variant("ref20")
    start = prepare_start(p)
    c, owner = start.c, start.owner
    before = evaluate(p, c.plan_from_owner(owner))
    assert per_rule(c, owner) == {name: before.rule_totals.get(name, 0) for name in c.rule_names}
    occupied = [s for s in range(len(owner)) if owner[s] >= 0 and not c.m.locked[owner[s], s]]
    checked = 0
    for s in occupied[:: max(1, len(occupied) // 40)]:
        for shift in (-8, 4, 40, 300):
            answer = why_not(c, owner, s, s + shift)
            if not answer.delta:
                continue
            st = new_state(c.m)
            init_state(c.m, st, owner)
            a, b = chunk_around(c.m, st, s)
            relocate(c.m, st, np.zeros(c.m.I, dtype=bool), int(owner[s]), a, b, s + shift, np.zeros(64, dtype=np.int64))
            after = evaluate(p, c.plan_from_owner(st.owner))
            assert answer.total == after.total - before.total
            checked += 1
    assert checked >= 10


def test_the_cheapest_other_place_is_valid_and_no_dearer_than_any_valid_alternative() -> None:
    p = variant("ref20")
    start = prepare_start(p)
    c, owner = start.c, start.owner
    movable = (s for s in range(len(owner)) if owner[s] >= 0 and not c.m.locked[owner[s], s])
    # In this full week some blocks have nowhere else to go; staying put doesn't count as another place.
    s, best = next((s, b) for s in movable if (b := why_not(c, owner, s)).valid)
    assert best.delta != {}  # an empty delta is staying put
    i = int(owner[s])
    for t in range(c.m.first_slot[i], c.m.last_slot[i] + 1, 7):
        other = why_not(c, owner, s, t)
        if other.valid and other.delta:
            assert best.total <= other.total


def first_slot_of(c, owner, key: str) -> int:  # noqa: ANN001
    i = c.keys.index(key)
    return int(np.flatnonzero(owner == i)[0])


def explain_move(p, key: str, new_start: int):  # noqa: ANN001, ANN201
    start = prepare_start(p)
    return why_not(start.c, start.owner, first_slot_of(start.c, start.owner, key), new_start)


def test_a_forbidden_alternative_names_its_wall() -> None:
    meeting = item("commitment", 9, title="Standup", start_utc=MON10 + 60, end_utc=MON10 + 90)
    work = item("assignment", 1, title="PS5", duration_units=2, due_utc=MON10 + 480, release_utc=MON10 + 15)
    p = problem([meeting, work], ["late_work"], slots=12)
    assert explain_move(p, "item:1", 0).walls == ["Before its release"]
    assert explain_move(p, "item:1", 4).walls == ["Busy: Standup"]
    late = problem([item("assignment", 1, duration_units=2, due_utc=at(1, "00:00"))], ["late_work"],
                   now=at(0, "23:00"), slots=8)  # fmt: skip
    assert explain_move(late, "item:1", 6).walls == ["Sleep"]


def test_a_locked_or_taken_slot_and_a_dependency_are_named() -> None:
    gym = item("chore", 2, title="Gym", duration_units=2)
    work = item("assignment", 1, title="PS5", duration_units=2, due_utc=MON10 + 480)
    locked = problem([work, gym], ["late_work"], pins=[Pin(2, MON10 + 60, MON10 + 90)])
    assert explain_move(locked, "item:1", 4).walls == ["Locked: Gym"]
    a = item("assignment", 1, title="Draft", duration_units=2, due_utc=MON10 + 480)
    b = item("assignment", 2, title="Final", duration_units=2, due_utc=MON10 + 480)
    p = problem([a, b], ["late_work"], deps=[Dependency(2, 1)], slots=12)
    start = prepare_start(p)
    final = first_slot_of(start.c, start.owner, "item:2")
    assert why_not(start.c, start.owner, final, 0).walls in (["Waits for Draft"], ["Taken by Draft"])


def test_a_protected_item_cannot_be_moved_past_its_due() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 60)], ["late_work"], slots=12)
    answer = explain_move(p, "item:1", 8)
    assert not answer.valid and answer.walls == ["Past its due"]
    assert check(p, prepare_start(p).c.plan_from_owner(prepare_start(p).owner)) == []
