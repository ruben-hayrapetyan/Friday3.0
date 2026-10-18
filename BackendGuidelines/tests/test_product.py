"""Duration models, the choice learner and the three-option generator."""
from __future__ import annotations

import math

import numpy as np
import pytest

from fr.core.evaluate import check
from fr.core.generate import cornell_semester
from fr.product.durations import POPULATION, AsGiven, Obs, make, quantile, remaining
from fr.product.options import METHODS, distinct, three
from fr.product.picks import Choice, ChoiceLearner
from fr.sim.user import LEARNABLE
from fr.sim.world import Universe

KINDS, COURSES = list(POPULATION), ["CS 2110", "MATH 2940"]


def test_cold_start_is_the_users_estimate():
    for name in ("as_given", "global_bias_recal", "hier_fused_drift_fa3_recal"):
        m, s = make(name, KINDS, COURSES).predict("CS 2110", "pset", 120.0, 0.0)
        assert math.exp(m) == pytest.approx(120.0), name
    m, _ = AsGiven().predict("CS 2110", "reading", None, 0.0)
    assert math.exp(m) == pytest.approx(POPULATION["reading"])


def test_learns_a_personal_ratio_and_a_course_effect():
    mdl = make("hier_fused_drift_fa3_recal", KINDS, COURSES)
    rng = np.random.default_rng(0)
    for k in range(12):  # CS problem sets take twice the estimate, math ones as estimated
        mdl.observe(Obs("CS 2110", "pset", 100.0, 200.0 * math.exp(rng.normal(0, 0.05)), k / 3))
        mdl.observe(Obs("MATH 2940", "pset", 100.0, 100.0 * math.exp(rng.normal(0, 0.05)), k / 3))
    cs = math.exp(mdl.predict("CS 2110", "pset", 100.0, 4.0)[0])
    ma = math.exp(mdl.predict("MATH 2940", "pset", 100.0, 4.0)[0])
    assert 160 < cs < 230 and 80 < ma < 125


def test_remaining_quantile_given_progress():
    m, s = math.log(120), 0.4
    assert remaining(m, s, 0.8, 0) == pytest.approx(quantile(m, s, 0.8))
    left = [remaining(m, s, 0.8, w) for w in (30, 60, 120, 240)]
    assert all(x > 0 for x in left)
    assert left[0] > left[1]  # early on, work done shortens what is left
    assert remaining(m, s, 0.8, 240) > 0  # past the median: still more to go, never negative


def test_choice_learner_recovers_direction_from_picks():
    rng = np.random.default_rng(1)
    D = len(LEARNABLE)
    truth = np.exp(rng.normal(0, 1.0, D))
    L = ChoiceLearner(D, mode="mnl", use_pairs=False)
    for w in range(150):
        phis = np.abs(rng.normal(5, 3, (3, D)))
        u = -(phis - phis[0]) @ truth
        p = np.exp((u - u.max()) / (np.abs(phis - phis[0]).sum() / 2 * 0.05))
        L.choices.append(Choice(phis, int(rng.choice(3, p=p / p.sum())), w))
    L.fit()
    cos = lambda a, b: float(a @ b / np.linalg.norm(a) / np.linalg.norm(b))
    assert 1 - cos(L.theta, truth) < 0.6 * (1 - cos(np.ones(D), truth))  # angle error cut by 40%+
    assert np.all(np.linalg.eigvalsh(L.cov) > 0)
    assert L.sample(4, rng).shape == (4, D)


@pytest.mark.parametrize("method", METHODS)
def test_three_options_are_valid_and_never_later(method):
    u = Universe(cornell_semester(3))
    L = ChoiceLearner(len(LEARNABLE))
    L.theta = np.exp(np.random.default_rng(2).normal(0, 0.3, len(LEARNABLE)))
    opts = three(u, L, method, steps=40_000, seed=1)
    assert len(opts.plans) == 3 and opts.labels[0] == "recommended"
    for x in opts.plans:
        assert check(u.p, u.c.plan_from_owner(x)) == []
        assert u.deadline_cost(x) <= u.deadline_cost(opts.plans[0]) + 1e-9
    assert max(distinct(u, opts.plans[0], x) for x in opts.plans[1:]) > 0.05
