"""The shared Lin evaluator and the direct evaluator share no structure: they must agree to the integer."""
import numpy as np
import pytest

from fr.core.direct import direct_rule_costs
from fr.core.evaluate import evaluate
from fr.core.generate import ADVERSARIAL, cornell_semester, reference_instance, tiny
from fr.core.plans import random_plan
from fr.core.problem import EASY, PUSH, DayScales

CASES = (
    [("ref20-%d" % s, lambda s=s: reference_instance(20, s)) for s in range(3)]
    + [("ref60", lambda: reference_instance(60, 1)), ("cornell", lambda: cornell_semester(0))]
    + [(k, (lambda k=k: ADVERSARIAL[k](0))) for k in ADVERSARIAL]
    + [("tiny-%d" % s, lambda s=s: tiny(s, 8, 3)) for s in range(6)]
)


@pytest.mark.parametrize("name,make", CASES, ids=[c[0] for c in CASES])
def test_evaluators_agree(name, make):
    sc = make()
    p = sc.build()
    # give the current-plan rule something to measure
    cur = random_plan(p, np.random.default_rng(99), 0.3)
    p = sc.build(current=cur)
    rng = np.random.default_rng(7)
    for fill in (0.05, 0.3, 0.7):
        plan = random_plan(p, rng, fill)
        a = evaluate(p, plan).rule_totals
        b = direct_rule_costs(p, plan)
        assert a == b, {k: (a[k], b[k]) for k in a if a[k] != b[k]}


@pytest.mark.parametrize("scale", [EASY, PUSH, DayScales(0.8, 1.5, 2.0, 0.5)], ids=["easy", "push", "mixed"])
def test_dials_agree(scale):
    sc = cornell_semester(1)
    sc.scales = [scale] * 14
    p = sc.build(current=random_plan(sc.build(), np.random.default_rng(3), 0.3))
    plan = random_plan(p, np.random.default_rng(4), 0.4)
    assert evaluate(p, plan).rule_totals == direct_rule_costs(p, plan)


EXTRAS = [
    dict(type="time_preference", name="sunday_rest", weight=3, params=dict(days=["sun"], price=4)),
    dict(type="time_preference", name="no_mornings", weight=1, params=dict(start="04:00", end="08:00", price="forbid")),
    dict(type="time_preference", name="late_wrap", weight=1, params=dict(start="22:00", end="02:00", price=2)),
    dict(type="finish_early", name="finish_early", weight=1, params=dict(days=2)),
    dict(type="after_event", name="after_class", weight=1,
         params=dict(events=dict(event_kind="class"), measure_from="last", slope=1, cap=3),
         scope=dict(preset="habit")),
    dict(type="after_event", name="after_any", weight=1,
         params=dict(events=dict(event_kind="class"), measure_from="any", slope=2, cap=4, on_days_without="cap"),
         scope=dict(preset="chore")),
    dict(type="batch_by_day", name="batch_chores", weight=2, params=dict(by="preset"),
         scope=dict(preset=["chore", "errand"])),
    dict(type="batch_by_day", name="batch_area", weight=2, params=dict(by="area"), scope=dict(firmness="hard")),
]


@pytest.mark.parametrize("seed", range(4))
def test_evaluators_agree_with_extra_rules_and_quotas(seed):
    sc = cornell_semester(seed)
    sc.extra_rules = EXTRAS
    p = sc.build()
    for i, it in enumerate(p.items.values()):  # hand-made allocator output
        if i % 3 == 0 and it.amount == "fixed":
            it.quotas = {1: 4, 2: 8}
            it.progress_by_week = {1: 1}
    rng = np.random.default_rng(seed)
    fired = set()
    for fill in (0.2, 0.6, 0.95):
        plan = random_plan(p, rng, fill, prefer_energy="deep" if fill > 0.9 else None)
        ev = evaluate(p, plan)
        assert ev.rule_totals == direct_rule_costs(p, plan)
        fired |= {r for r, v in ev.rule_totals.items() if v}
    for needed in ("quota", "sunday_rest", "late_wrap", "finish_early", "batch_chores", "deep_run"):
        assert needed in fired, f"{needed} never fired, so the comparison proves nothing for it"
