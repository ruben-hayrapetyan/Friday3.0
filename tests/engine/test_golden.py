"""v3's evaluator and checker reproduce the research evaluator on every golden fixture, to the integer."""

import numpy as np
import pytest

from friday.engine.checker import check
from friday.engine.evaluate import evaluate
from tests.engine.golden import fixture_names, plan_of, problem, read, slots_of

NAMES = fixture_names()


def test_there_are_forty_fixtures() -> None:
    assert len(NAMES) == 40


@pytest.mark.parametrize("name", NAMES)
def test_grid_and_blocked_time_match_the_research(name: str) -> None:
    fixture = read(name)
    p = problem(fixture)
    assert fixture["grid"]["slots"] == p.grid.S
    assert p.grid.horizon_end == fixture["grid"]["horizon_end"] + 4 * 1440
    assert np.flatnonzero(p.blocked).tolist() == slots_of(fixture["blocked"])
    assert np.flatnonzero(p.core).tolist() == slots_of(fixture["core"])


@pytest.mark.parametrize("name", NAMES)
def test_stage_values_and_rule_totals_match_the_research(name: str) -> None:
    fixture = read(name)
    p = problem(fixture)
    for raw in fixture["plans"]:
        plan = plan_of(raw, p)
        ev = evaluate(p, plan)
        assert ev.stage_values == raw["stage_values"], raw["label"]
        assert ev.rule_totals == raw["rule_totals"], raw["label"]
        assert sorted(f"{v.code}:{v.key}" for v in check(p, plan)) == raw["violations"], raw["label"]
