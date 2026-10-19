"""Learning pieces on synthetic data where the answer is known."""
from __future__ import annotations

import numpy as np

from fr.learn.hidden import PACE_H, U_DIAL, HiddenLearner
from fr.learn.methods import ranking_qp
from fr.sim.user import LEARNABLE
from fr.sim.world import Ranking, Week
from fr.supervisor.discover import SCALE, bt_fit, cv_gain

D = len(LEARNABLE)


def synthetic_rankings(theta, n, rng, extra_w=0.0, noise=0.0, h=None):
    out = []
    for _ in range(n):
        a, b = rng.random(D) * 10, rng.random(D) * 10
        xa, xb = rng.random() * 5, rng.random() * 5
        th = theta if h is None else theta * np.exp(h @ U_DIAL)
        ea, eb = th @ a + extra_w * xa, th @ b + extra_w * xb
        win = ea < eb
        if noise and rng.random() < noise:
            win = not win
        out.append(Ranking(a, b, bool(win), "pair", 0, {"c": xa}, {"c": xb}))
    return out


def test_ranking_qp_satisfies_consistent_constraints():
    rng = np.random.default_rng(0)
    truth = np.exp(rng.normal(0, 0.5, D))
    rs = synthetic_rankings(truth, 40, rng)
    th, slack = ranking_qp(np.ones(D), rs, np.ones(D), mu=0.0, C=1000.0, cap=10.0, margin=1e-4)
    assert slack < 1e-3
    assert all(th @ r.diff() <= 1e-6 for r in rs)


def test_bt_fit_recovers_the_direction():
    rng = np.random.default_rng(1)
    truth = np.exp(rng.normal(0, 0.5, D))
    rs = synthetic_rankings(truth, 400, rng)
    X = np.array([r.diff() / np.abs(r.diff()).sum() for r in rs])
    th = bt_fit(X, np.ones(D), np.full(D, 10.0), np.full(D, 0.02))
    cos = th @ truth / np.linalg.norm(th) / np.linalg.norm(truth)
    assert cos > 0.9


def test_cv_gain_finds_a_planted_missing_feature_and_not_a_fake_one():
    rng = np.random.default_rng(2)
    truth = np.ones(D)
    with_missing = synthetic_rankings(truth, 150, rng, extra_w=3.0)
    without = synthetic_rankings(truth, 150, rng, extra_w=0.0)

    def design(rs):
        lib = np.array([r.diff() for r in rs])
        ext = np.array([[(r.extra_a["c"] - r.extra_b["c"]) * (1 if r.a_better else -1)] for r in rs])
        n = np.abs(lib).sum(axis=1, keepdims=True)
        return lib / n, ext / n

    g1 = cv_gain(*design(with_missing))[0]
    g0 = cv_gain(*design(without))[0]
    assert g1 > 0.05 > g0


def test_hidden_units_explain_a_planted_state():
    """One week in three is 'tired'; with check-ins the units read most weeks right. (Without an anchor, 'normal' is
    only defined relative to the other weeks: that is RQ7's ambiguity, tested in E013.)"""
    rng = np.random.default_rng(3)
    truth = np.ones(D)
    L = HiddenLearner("dial", scale=SCALE)
    moods = ["tired" if w % 3 == 1 else "normal" for w in range(9)]
    for w, m in enumerate(moods):
        rs = synthetic_rankings(truth, 40, rng, h=PACE_H[m])
        L.add_week(Week(w, m, None, None, None, None, rs, 0, 0, 3.0, m, 1.0, 0.0))
    reads = [L.mood_of(h) for h in L.h]
    assert np.mean([r == m for r, m in zip(reads, moods)]) >= 0.65, reads
