"""A warm replan searches from the plan you have too, in one more chain, when that is better than the start made from
it (14 Nov: a half hour at 1:45am, with a cheaper evening free, kept by every replan). The start put back what the plan
had left out and repaired the result; when that came out worse than the plan you have, the plan you have stood whole,
and no replan could better it a block at a time."""

import numpy as np
import pytest

import friday.engine.scheduler as scheduler
from friday.engine.evaluate import evaluate
from tests.engine.configs import fast
from tests.engine.helpers import at, item, plan, problem

EVENING = at(0, "21:30")  # slots 0–7: 21:30 to 23:30, bedtime 23:30


def evening():  # noqa: ANN201
    """A problem set and a reading due at bedtime; the plan you have has the reading at 23:00, the latest it can."""
    problem_set = item("assignment", 1, duration_units=4, due_utc=at(0, "23:30"))
    reading = item("reading", 2, duration_units=2, due_utc=at(0, "23:30"), firmness="hard")
    current = {1: [(EVENING, EVENING + 60)], 2: [(EVENING + 90, EVENING + 120)]}
    return problem([problem_set, reading], ("late_work", "late_night", "minimize_changes"), now=EVENING, slots=8,
                   current=current)  # fmt: skip


@pytest.fixture
def worse_start(monkeypatch: pytest.MonkeyPatch) -> list[list[dict]]:
    """Every start made from the plan you have comes out worse (all of it left out); returns the anneal's starts."""
    real_started, real_anneal = scheduler.started, scheduler.anneal

    def started(c, built, config, cancel, warm, seed):  # noqa: ANN001, ANN202
        owner, trace = real_started(c, built, config, cancel, warm, seed)
        return np.full_like(owner, -1), trace

    seen: list[list[dict]] = []

    def anneal(c, starts, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        seen.append([c.plan_from_owner(s) for s in [*starts, *(kwargs.get("extra") or [])]])
        return real_anneal(c, starts, *args, **kwargs)

    monkeypatch.setattr(scheduler, "started", started)
    monkeypatch.setattr(scheduler, "anneal", anneal)
    return seen


def test_the_search_starts_from_the_plan_you_have_when_the_start_made_from_it_is_worse(worse_start) -> None:  # noqa: ANN001
    result = scheduler.schedule(evening(), fast(), warm=True)
    have = plan(item_1=(0, 1, 2, 3), item_2=(6, 7))
    assert any(start == have for start in worse_start[0])
    assert "kept" in result.deadlines_after
    assert result.plan == plan(item_1=(0, 1, 2, 3), item_2=(4, 5))
    late = lambda placed: evaluate(evening(), placed).rule_totals["late_night"]  # noqa: E731
    assert late(result.plan) < late(have)


def test_a_start_better_than_the_plan_you_have_is_searched_from_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []
    real_anneal = scheduler.anneal

    def anneal(c, starts, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        seen.append(len(starts) + len(kwargs.get("extra") or []))
        return real_anneal(c, starts, *args, **kwargs)

    monkeypatch.setattr(scheduler, "anneal", anneal)
    result = scheduler.schedule(evening(), fast(), warm=True)
    assert seen == [1] and "kept" not in result.deadlines_after
    assert result.plan == plan(item_1=(0, 1, 2, 3), item_2=(4, 5))  # the reading moved up to meet the problem set
