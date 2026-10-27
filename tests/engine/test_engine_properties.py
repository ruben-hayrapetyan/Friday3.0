"""The engine on random small problems: any mix of the reference and extra rules, rule weights, learned θ, paces,
time zones across DST, pins, dependencies and a previous plan. The Lin evaluator, the kernel's incremental state
after random moves and the direct evaluator agree to the integer, and every schedule keeps its walls."""

from dataclasses import dataclass

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from friday.core.pace import DEFAULT_PACES, Dials, scales
from friday.engine.checker import check
from friday.engine.compile import compile_problem
from friday.engine.evaluate import evaluate
from friday.engine.kernel import init_state, new_state
from friday.engine.problem import Problem
from friday.engine.scheduler import schedule
from tests.bench.generator import ADVERSARIAL, MONDAY, Scenario, reference_instance, reference_rules, tiny, warm_variant
from tests.engine.configs import fast
from tests.engine.direct_eval import direct_rule_costs
from tests.engine.instances import (
    DST_FINE_MONDAY,
    EXTRA_RULES,
    NEW_YORK,
    SPRING_MONDAY,
    add_quotas,
    current_plan,
    with_rules,
)
from tests.engine.kernel_check import random_moves
from tests.engine.plans import random_plan

QUICK = settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
SLOW = settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
ZONES = [("UTC", MONDAY), (NEW_YORK, DST_FINE_MONDAY), (NEW_YORK, SPRING_MONDAY), (NEW_YORK, MONDAY)]
REFERENCE = reference_rules()
DAY_DIALS = [scales(Dials()), scales(DEFAULT_PACES["Easy"]), scales(DEFAULT_PACES["Push"]),
             scales(Dials(capacity=0.8, rest=1.5, spread=2.0, growth=0.5))]  # fmt: skip


@dataclass(frozen=True)
class Case:
    """A random problem, as hypothesis draws and shrinks it."""

    family: str
    size: int
    seed: int
    zone: int
    load: float
    pins: int
    deps: int
    rules: tuple[int, ...]  # indexes into REFERENCE, then EXTRA_RULES
    weights: tuple[float, ...]
    thetas: tuple[float, ...] | None
    days: tuple[int, ...] | None  # each day's dials, by index into DAY_DIALS
    previous: bool
    quotas: bool
    warm: bool

    def scenario(self) -> Scenario:
        timezone, monday = ZONES[self.zone]
        if self.family == "reference":
            sc = reference_instance(self.size, self.seed, load=self.load, pins=self.pins, deps=self.deps,
                                    timezone=timezone, monday=monday)  # fmt: skip
        elif self.family == "tiny":
            sc = tiny(self.seed, 4 + self.size % 9, 1 + self.size % 3)
        else:
            sc = ADVERSARIAL[self.family](self.seed % 50)
        if self.warm and self.family != "tiny":
            sc = warm_variant(sc, self.seed)
        every = REFERENCE + EXTRA_RULES
        chosen = [dict(every[i]) | {"weight": w} for i, w in zip(self.rules, self.weights, strict=True)]
        sc = with_rules(sc, chosen)
        if self.days is not None:
            sc.day_scales = [DAY_DIALS[d] for d in self.days]
        return sc

    def problem(self) -> Problem:
        sc = self.scenario()
        names = [r.name for r in sc.settings["rules"]]
        thetas = dict(zip(names, self.thetas, strict=False)) if self.thetas else {}
        previous = current_plan(sc, self.seed) if self.previous else None
        p = sc.build(current=previous, multipliers=thetas, minimize_changes_scale=0.2 if self.previous else 1.0)
        return add_quotas(p) if self.quotas else p


@st.composite
def cases(draw: st.DrawFn, families: tuple[str, ...] = ("reference",)) -> Case:
    every = len(REFERENCE) + len(EXTRA_RULES)
    mask = draw(st.lists(st.booleans(), min_size=every, max_size=every))  # about half of all the rules, each time
    rules = [i for i, on in enumerate(mask) if on] or [draw(st.integers(0, every - 1))]
    return Case(
        family=draw(st.sampled_from(families)),
        size=draw(st.sampled_from([3, 5, 10, 20])),
        seed=draw(st.integers(0, 10**6)),
        zone=draw(st.integers(0, len(ZONES) - 1)),
        load=draw(st.sampled_from([0.2, 0.45, 0.9, 1.4])),
        pins=draw(st.integers(0, 5)),
        deps=draw(st.integers(0, 6)),
        rules=tuple(rules),
        weights=tuple(draw(st.sampled_from([0.5, 1.0, 2.0, 3.0, 7.3, 10.0])) for _ in rules),
        thetas=draw(st.none() | st.lists(st.floats(0.2, 4.0), min_size=len(rules), max_size=len(rules)).map(tuple)),
        days=draw(st.none() | st.lists(st.integers(0, len(DAY_DIALS) - 1), min_size=14, max_size=14).map(tuple)),
        previous=draw(st.booleans()),
        quotas=draw(st.booleans()),
        warm=draw(st.booleans()),
    )


@QUICK
@given(cases(), st.lists(st.floats(0.0, 1.0), min_size=1, max_size=3), st.sampled_from([None, "deep", "light"]))
def test_the_evaluators_agree_on_random_problems_and_plans(case: Case, fills: list[float], energy: str | None) -> None:
    p = case.problem()
    rng = np.random.default_rng(case.seed)
    for fill in fills:
        plan = random_plan(p, rng, fill, prefer_energy=energy)
        ours, theirs = evaluate(p, plan).rule_totals, direct_rule_costs(p, plan)
        assert ours == theirs, {k: (ours[k], theirs.get(k)) for k in ours if ours[k] != theirs.get(k)}


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(cases(), st.floats(0.05, 0.7))
def test_the_kernels_incremental_state_stays_exact_under_random_moves(case: Case, fill: float) -> None:
    p = case.problem()
    c = compile_problem(p)
    state = new_state(c.m)
    init_state(c.m, state, c.owner_from_plan(random_plan(p, np.random.default_rng(case.seed), fill)))
    random_moves(c, state, 300, case.seed % 10_000, check_every=75)  # kernel = evaluator = checker, as it goes
    plan = c.plan_from_owner(state.owner)
    assert evaluate(p, plan).rule_totals == direct_rule_costs(p, plan)


@SLOW
@given(cases(families=("reference", "reference", "tiny", *ADVERSARIAL)), st.integers(0, 99), st.booleans())
def test_every_schedule_keeps_its_walls_whatever_the_rules(case: Case, seed: int, fallback: bool) -> None:
    p = case.problem()
    result = schedule(p, fast(steps=3000, seed=seed, fallback=fallback, fallback_s=0.5))
    assert check(p, result.plan, result.protected) == []
    assert evaluate(p, result.plan).rule_totals == result.evaluation.rule_totals
