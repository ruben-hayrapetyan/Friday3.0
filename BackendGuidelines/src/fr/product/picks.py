"""Learning rule weights from the plan the user picks out of three (RQ15).

A pick is a choice: P(pick k) = softmax_k(-theta . phi_k / (n * scale)), where phi_k are the plans' rule features and n
normalises the set's differences (the same scale invariance as Bradley-Terry on pairs, E011b). Pairs and drags from the
existing feedback keep their Bradley-Terry likelihood. The fit is a MAP with a Gaussian prior toward the hand-set
weights; a Laplace approximation gives a posterior for Thompson sampling and query design. `mode="rankbreak"` replaces
each pick by two pairwise wins (winner > each loser), the cheap approximation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..sim.world import Ranking

THETA_MIN = 0.02
SCALE = 0.05


@dataclass
class Choice:
    phis: np.ndarray  # [k, D]; row 0 is the plan Friday recommended
    chosen: int
    week: int


def _choice_design(c: Choice) -> np.ndarray:
    d = c.phis - c.phis[0]
    n = np.abs(d).sum() / max(len(d) - 1, 1)
    return d / n if n > 1e-12 else d


@dataclass
class ChoiceLearner:
    D: int
    mode: str = "mnl"  # mnl | rankbreak | none
    use_pairs: bool = True
    sigma: float = 1.0
    scale: float = SCALE
    drag_weight: float = 3.0
    pick_weight: float = 1.0
    choices: list[Choice] = field(default_factory=list)
    rankings: list[Ranking] = field(default_factory=list)

    def __post_init__(self):
        self.theta0 = np.ones(self.D)
        self.theta = self.theta0.copy()
        self.cov = np.eye(self.D) * self.sigma ** 2

    def add(self, choices: list[Choice] = (), rankings: list[Ranking] = ()) -> None:
        self.choices += list(choices)
        if self.use_pairs:
            self.rankings += list(rankings)
        self.fit()

    def _pairs(self) -> tuple[np.ndarray, np.ndarray]:
        X = [r.diff() / max(np.abs(r.diff()).sum(), 1e-12) for r in self.rankings]
        w = [self.drag_weight if r.kind == "drag" else 1.0 for r in self.rankings]
        if self.mode == "rankbreak":
            for c in self.choices:
                for k in range(len(c.phis)):
                    if k != c.chosen:
                        d = c.phis[c.chosen] - c.phis[k]
                        X.append(d / max(np.abs(d).sum(), 1e-12))
                        w.append(self.pick_weight)
        D = self.D
        return (np.array(X).reshape(-1, D), np.array(w))

    def fit(self) -> None:
        if self.mode == "none":
            return
        X, w = self._pairs()
        C = [(_choice_design(c), c.chosen) for c in self.choices] if self.mode == "mnl" else []
        s, prior, sig = self.scale, self.theta0, np.full(self.D, self.sigma)

        def f(th):
            nll = 0.5 * np.sum(((th - prior) / sig) ** 2)
            g = (th - prior) / sig ** 2
            if len(X):
                z = -(X @ th) / s
                nll += float((w * np.logaddexp(0, -z)).sum())
                g = g + X.T @ (w * (1 - 1 / (1 + np.exp(-z))) / s)
            for Dm, k in C:
                u = -(Dm @ th) / s
                m = u.max()
                lse = m + np.log(np.exp(u - m).sum())
                p = np.exp(u - lse)
                nll += self.pick_weight * float(lse - u[k])
                g = g + self.pick_weight * (-(Dm.T @ p) + Dm[k]) / s
            return nll, g

        res = minimize(f, self.theta.copy(), jac=True, method="L-BFGS-B", bounds=[(THETA_MIN, None)] * self.D)
        th = res.x
        self.theta = th
        self.cov = np.linalg.inv(self._hessian(th, X, w, C) + 1e-9 * np.eye(self.D))

    def _hessian(self, th, X, w, C) -> np.ndarray:
        s = self.scale
        H = np.diag(np.full(self.D, 1 / self.sigma ** 2))
        if len(X):
            z = -(X @ th) / s
            p = 1 / (1 + np.exp(-z))
            H += (X.T * (w * p * (1 - p))) @ X / s ** 2
        for Dm, _ in C:
            u = -(Dm @ th) / s
            p = np.exp(u - u.max())
            p /= p.sum()
            H += self.pick_weight * Dm.T @ (np.diag(p) - np.outer(p, p)) @ Dm / s ** 2
        return H

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        """Posterior samples (Laplace), clipped at the lower bound."""
        L = np.linalg.cholesky(self.cov + 1e-12 * np.eye(self.D))
        return np.maximum(THETA_MIN, self.theta + rng.standard_normal((n, self.D)) @ L.T)

    def choice_probs(self, phis: np.ndarray, theta: np.ndarray) -> np.ndarray:
        Dm = _choice_design(Choice(phis, 0, 0))
        u = -(Dm @ theta) / self.scale
        p = np.exp(u - u.max())
        return p / p.sum()
