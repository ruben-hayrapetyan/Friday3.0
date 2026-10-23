"""Learned weights (DESIGN §21.2), ported from the research's Bradley–Terry learner (`learn/methods.py`,
`supervisor/discover.py`).

A comparison is two plans' feature vectors φ (each learnable rule's total at its hand-set weight, in points) and
which one the user preferred. The model: P(winner) = σ(−θ·x / s), x = (φ_winner − φ_loser) / ‖φ_winner − φ_loser‖₁.
θ are multipliers on the hand-set weights, MAP-fitted with a N(1, prior_sd) prior and θ ≥ θ_min. Pure: numpy, scipy.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

SCALE = 0.05
NOISE_GRID = (0.02, 0.05, 0.1, 0.2, 0.5)


@dataclass(frozen=True)
class Comparison:
    winner: dict[str, float]  # rule name → points
    loser: dict[str, float]
    weight: float = 1.0  # a drag counts `drag_weight` times


def design(comparisons: Sequence[Comparison], rules: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    """Normalized differences [n, D] (winner minus loser) and per-comparison weights."""
    x = np.array([[c.winner.get(r, 0.0) - c.loser.get(r, 0.0) for r in rules] for c in comparisons], dtype=float)
    x = x.reshape(len(comparisons), len(rules))
    size = np.abs(x).sum(axis=1, keepdims=True)
    size[size < 1e-12] = 1.0
    return x / size, np.array([c.weight for c in comparisons], dtype=float)


def bt_fit(
    x: np.ndarray, prior: np.ndarray, sd: np.ndarray, low: np.ndarray, weight: np.ndarray | None = None,
    scale: float = SCALE,
) -> np.ndarray:  # fmt: skip
    """MAP of P(winner) = σ(−θ·x / scale) under a Gaussian prior and lower bounds, with optional weights."""
    weight = np.ones(len(x)) if weight is None else weight

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        z = -(x @ theta) / scale
        nll = (weight * np.logaddexp(0, -z)).sum() + 0.5 * np.sum(((theta - prior) / sd) ** 2)
        grad = x.T @ (weight * (1 - 1 / (1 + np.exp(-z))) / scale) + (theta - prior) / sd**2
        return float(nll), grad

    found = minimize(objective, prior.copy(), jac=True, method="L-BFGS-B", bounds=[(lo, None) for lo in low])
    return np.asarray(found.x)


def loglik(x: np.ndarray, theta: np.ndarray, scale: float = SCALE) -> np.ndarray:
    return np.asarray(-np.logaddexp(0, (x @ theta) / scale))


def answer_scale(x: np.ndarray, prior: np.ndarray, weight: np.ndarray | None = None, seed: int = 0) -> float:
    """The user's answer noise as a Bradley–Terry temperature, by cross-validated likelihood (fewer than 12
    comparisons: the default). It sets policy (how much to ask), never the fit."""
    n, d = x.shape
    if n < 12:
        return SCALE
    parts = np.array_split(np.random.default_rng(seed).permutation(n), 3)
    best, best_ll = SCALE, -np.inf
    for s in NOISE_GRID:
        ll = 0.0
        for test in parts:
            train = np.setdiff1d(np.arange(n), test)
            theta = bt_fit(x[train], prior, np.ones(d), np.full(d, 0.02), None if weight is None else weight[train], s)
            ll += float(loglik(x[test], theta, s).sum())
        if ll > best_ll:
            best, best_ll = s, ll
    return best


def fit(
    comparisons: Sequence[Comparison], rules: Sequence[str], prior_sd: float = 1.0, theta_min: float = 0.02,
    scale: float = SCALE,
) -> dict[str, float]:  # fmt: skip
    """θ per learnable rule. Only the direction is learned: θ is rescaled to keep the hand-set weights' total."""
    if not comparisons or not rules:
        return dict.fromkeys(rules, 1.0)
    x, weight = design(comparisons, rules)
    d = len(rules)
    theta = bt_fit(x, np.ones(d), np.full(d, prior_sd), np.full(d, theta_min), weight, scale)
    theta = np.maximum(theta * (d / max(theta.sum(), 1e-12)), theta_min)
    return {r: float(t) for r, t in zip(rules, theta, strict=True)}


def accuracy(comparisons: Sequence[Comparison], rules: Sequence[str], theta: dict[str, float]) -> float:
    """The share of comparisons θ predicts the right way (a tie counts half)."""
    if not comparisons:
        return 0.0
    x, _ = design(comparisons, rules)
    z = -(x @ np.array([theta.get(r, 1.0) for r in rules]))
    return float(((z > 0) + 0.5 * (z == 0)).mean())
