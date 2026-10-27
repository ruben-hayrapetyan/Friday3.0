"""The Lin evaluator and the direct evaluator share no structure; they must agree to the integer."""

import numpy as np
import pytest

from friday.engine.evaluate import evaluate
from tests.engine.direct_eval import direct_rule_costs
from tests.engine.instances import VARIANTS, single_rule, variant
from tests.engine.plans import random_plan


@pytest.mark.parametrize("name", VARIANTS)
def test_evaluators_agree(name: str) -> None:
    p = variant(name)
    rng = np.random.default_rng(7)
    for fill in (0.05, 0.3, 0.7, 0.95):
        plan = random_plan(p, rng, fill, prefer_energy="deep" if fill > 0.9 else None)
        ours, theirs = evaluate(p, plan).rule_totals, direct_rule_costs(p, plan)
        assert ours == theirs, {k: (ours[k], theirs[k]) for k in ours if ours[k] != theirs[k]}


def test_every_rule_type_fires_in_the_extra_variant() -> None:
    p = variant("extra")
    rng = np.random.default_rng(3)
    fired = set()
    for fill in (0.2, 0.6, 0.95):
        ev = evaluate(p, random_plan(p, rng, fill, prefer_energy="deep" if fill > 0.9 else None))
        fired |= {r.type for r in p.rules if ev.rule_totals[r.name]}
    assert fired >= {"quota", "time_preference", "finish_early", "batch_by_day", "deep_run", "minimize_changes",
                     "after_event", "late_night", "reserve", "buffer"}  # fmt: skip


@pytest.mark.parametrize("rule_type", ["travel_kept", "fit_gaps", "runs_while_working", "pin_hold"])
def test_evaluators_agree_on_one_rule_that_fires(rule_type: str) -> None:
    p = single_rule(rule_type)  # travel_kept: the week's routines get a quarter hour there and back
    rng = np.random.default_rng(11)
    for fill in (0.2, 0.6, 0.95):
        plan = random_plan(p, rng, fill)
        ours, theirs = evaluate(p, plan).rule_totals, direct_rule_costs(p, plan)
        assert ours == theirs, {k: (ours[k], theirs[k]) for k in ours if ours[k] != theirs[k]}
    assert any(evaluate(p, random_plan(p, rng, 0.95)).rule_totals.values())
