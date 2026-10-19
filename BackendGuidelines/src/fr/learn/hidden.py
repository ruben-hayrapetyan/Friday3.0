"""Hidden units for state (RQ6, RQ7): E(x, h) = sum_r (theta_r + sum_j U_jr h_j) phi_r(x).

The four v2 dials are hand-set hidden units: `U_DIAL` says which rule weights each dial moves (reference section 10, read
as weight changes). A week's units h_w are inferred (MAP) from that week's rankings plus cheap evidence (skipped blocks, a
one-tap check-in); taste theta, free units' loadings U_free and the evidence links are fitted jointly over all weeks.

Modes: "none" (taste only), "dial" (four dial-seeded units, fixed U), "dial+free" (plus learned free units),
"free" (learned units, no seeding), "oracle" (the true mood is known: an upper bound).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..sim.user import LEARNABLE, MOODS
from ..sim.world import Ranking, Week

D = len(LEARNABLE)
DIALS = ("capacity", "rest", "spread", "growth")
_DIAL_RULES = {
    "capacity": {"daily_load": -1.0, "deep_run": -1.0},
    "rest": {"late_night": 1.0, "weekday_evenings": 1.0, "weekends": 1.0},
    "spread": {"even_load": 1.0},
    "growth": {"open_value": 1.0, "target_shortfall": 1.0, "unscheduled": 1.0},
}
U_DIAL = np.zeros((4, D))
for j, dial in enumerate(DIALS):
    for r, v in _DIAL_RULES[dial].items():
        U_DIAL[j, LEARNABLE.index(r)] = v
# check-in likelihood: logits of (normal, tired, motivated) given the four dial units
A_CHECKIN = np.array([[0.0, 0.0, 0.0, 0.0], [-1.5, 1.5, 0.0, -1.0], [1.5, -1.0, 0.0, 1.5]])
PACE_H = {"normal": np.zeros(4), "tired": np.array([-1.0, 1.0, 0.0, -1.0]), "motivated": np.array([1.0, -1.0, 0.0, 1.0])}


def _norm_diff(r: Ranking) -> np.ndarray:
    d = r.diff()
    n = np.abs(d).sum()
    return d / n if n > 1e-12 else d


@dataclass
class WeekEvidence:
    diffs: np.ndarray  # [n, D] normalised phi(winner) - phi(loser)
    skips: int
    blocks: int
    checkin: str | None
    pace: str | None  # a pace the user picked this week (clamps the dial units), or None
    weights: np.ndarray | None = None  # per ranking; drags (revealed behaviour) count more (E011)


@dataclass
class HiddenLearner:
    mode: str = "dial"
    n_free: int = 2
    scale: float = 0.05  # Bradley-Terry temperature on normalised differences
    sigma_theta: float = 1.0
    sigma_u: float = 0.5
    center: float = 0.0
    drag_weight: float = 3.0
    link: str = "mult"  # "mult": theta * exp(U h) (state rescales weights); "add": theta + U h, as first written
    theta: np.ndarray = field(default_factory=lambda: np.ones(D))
    weeks: list[WeekEvidence] = field(default_factory=list)
    h: list[np.ndarray] = field(default_factory=list)
    U_free: np.ndarray | None = None
    skip_link: np.ndarray | None = None  # intercept + one coefficient per unit
    name: str = ""

    def __post_init__(self):
        self.name = self.name or f"hidden_{self.mode}"
        self.K = {"none": 0, "dial": 4, "dial+free": 4 + self.n_free, "free": self.n_free + 2, "oracle": 4}[self.mode]
        nf = self.K - (4 if self.mode in ("dial", "dial+free", "oracle") else 0)
        rng = np.random.default_rng(0)
        self.U_free = rng.normal(0, 0.05, size=(nf, D)) if nf else np.zeros((0, D))
        self.skip_link = np.zeros(self.K + 1)
        self.skip_link[0] = -2.5
        if self.mode in ("dial", "dial+free", "oracle"):
            self.skip_link[1:5] = [-0.8, 1.0, 0.0, -0.4]  # tired-looking units skip more (seeded, then fitted)

    # -- model pieces
    def U(self) -> np.ndarray:
        if self.mode in ("dial", "dial+free", "oracle"):
            return np.vstack([U_DIAL, self.U_free]) if len(self.U_free) else U_DIAL
        return self.U_free

    def theta_eff(self, h: np.ndarray, theta: np.ndarray | None = None) -> np.ndarray:
        th = self.theta if theta is None else theta
        if self.K == 0:
            return np.maximum(th, 0.02)
        if self.link == "mult":
            return th * np.exp(np.clip(h @ self.U(), -5, 5))
        return np.maximum(th + h @ self.U(), 0.02)

    def _checkin_ll(self, h: np.ndarray, c: str | None) -> float:
        if c is None or self.mode not in ("dial", "dial+free"):
            return 0.0
        z = A_CHECKIN @ h[:4]
        z = z - z.max()
        return 0.7 * float(z[MOODS.index(c)] - np.log(np.exp(z).sum()))  # a check-in is right ~70% of the time

    # -- inference
    def predict_h(self, checkin: str | None, pace: str | None, true_mood: str | None = None) -> np.ndarray:
        """Units Friday plans with at the start of a week, before its rankings exist."""
        if self.K == 0:
            return np.zeros(0)
        if self.mode == "oracle":
            return PACE_H[true_mood or "normal"].copy()
        h = np.zeros(self.K)
        if pace is not None and self.mode in ("dial", "dial+free"):
            h[:4] = PACE_H[pace]  # a picked pace clamps the dial units
            return h
        if self.h:
            h = 0.5 * self.h[-1]  # states persist a little from week to week
        if checkin is not None and self.mode in ("dial", "dial+free"):
            res = minimize(lambda x: 0.5 * np.sum((x - h) ** 2) - self._checkin_ll(x, checkin), h, method="L-BFGS-B")
            h = res.x
        return h

    def week_ll(self, x_theta: np.ndarray, h: np.ndarray, ev: WeekEvidence) -> float:
        te = self.theta_eff(h, x_theta)
        ll = 0.0
        if len(ev.diffs):
            z = -(ev.diffs @ te) / self.scale
            w = ev.weights if ev.weights is not None else np.ones(len(z))
            ll += float(-(w * np.logaddexp(0, -z)).sum())
        if self.K and ev.blocks:
            p = 1 / (1 + np.exp(-(self.skip_link[0] + self.skip_link[1:] @ h)))
            p = np.clip(p, 1e-6, 1 - 1e-6)
            ll += ev.skips * np.log(p) + (ev.blocks - ev.skips) * np.log(1 - p)
        ll += self._checkin_ll(h, ev.checkin)
        return ll

    def add_week(self, week: Week, pace: str | None = None) -> None:
        diffs = np.array([_norm_diff(r) for r in week.rankings]) if week.rankings else np.zeros((0, D))
        w = np.array([self.drag_weight if r.kind == "drag" else 1.0 for r in week.rankings])
        self.weeks.append(WeekEvidence(diffs, week.skips, week.blocks, week.checkin, pace, w))
        self.h.append(np.zeros(self.K))
        self.fit(true_moods=None)

    def fit(self, true_moods: list[str] | None = None, iters: int = 200) -> None:
        """Joint MAP of theta, the weeks' units, free loadings and the skip link."""
        W, K, nf = len(self.weeks), self.K, len(self.U_free)
        if W == 0:
            return

        def unpack(x):
            th = x[:D]
            o = D
            hs = x[o:o + W * K].reshape(W, K)
            o += W * K
            uf = x[o:o + nf * D].reshape(nf, D)
            o += nf * D
            sl = x[o:o + K + 1] if K else self.skip_link
            return th, hs, uf, sl

        def f(x):
            th, hs, uf, sl = unpack(x)
            self.U_free, self.skip_link = uf, sl
            nll = 0.5 * np.sum((th - 1.0) ** 2) / self.sigma_theta ** 2 + 0.5 * np.sum(uf ** 2) / self.sigma_u ** 2
            if K and W > 1:  # theta and the average state are confounded: most weeks are ordinary, so centre the units
                nll += 0.5 * self.center * W * np.sum(hs.mean(axis=0) ** 2)
            for w, ev in enumerate(self.weeks):
                h = hs[w] if K else np.zeros(0)
                if self.mode == "oracle":
                    h = PACE_H[true_moods[w]] if true_moods else h
                elif ev.pace is not None and self.mode in ("dial", "dial+free"):
                    h = np.concatenate([PACE_H[ev.pace], h[4:]])
                nll += 0.5 * np.sum(h ** 2) - self.week_ll(th, h, ev)
            return nll

        x0 = np.concatenate([self.theta, np.array(self.h).ravel() if K else np.zeros(0), self.U_free.ravel(),
                             self.skip_link if K else np.zeros(0)])
        bounds = [(0.02, 20.0)] * D + [(-3, 3)] * (W * K) + [(-3, 3)] * (nf * D) + ([(-6, 6)] * (K + 1) if K else [])
        res = minimize(f, x0, method="L-BFGS-B", bounds=bounds, options=dict(maxiter=iters))
        th, hs, uf, sl = unpack(res.x)
        self.theta, self.U_free, self.skip_link = th, uf, sl
        self.h = [hs[w] for w in range(W)] if K else [np.zeros(0)] * W
        if self.mode == "oracle" and true_moods:
            self.h = [PACE_H[m].copy() for m in true_moods]

    def mood_of(self, h: np.ndarray) -> str:
        """Read a week's units as a mood (only meaningful for dial-seeded units)."""
        if self.K == 0 or self.mode == "free":
            return "normal"
        z = A_CHECKIN @ h[:4]
        return MOODS[int(np.argmax(z))] if z.max() - z[0] > 0.5 else "normal"
