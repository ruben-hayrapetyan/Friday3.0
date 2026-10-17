"""Missing-feature detection and rule proposal (RQ8).

Rankings are fitted with a Bradley-Terry model over the library features; a candidate rule (from `grammar`) is worth
proposing when adding its feature raises the cross-validated log-likelihood of the rankings by more than a threshold.
The threshold is tuned on users who have no missing feature (to bound false rules) and reported on fresh users.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from ..sim.world import Ranking

SCALE = 0.05


def design(rankings: list[Ranking], cands: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Normalised library differences [n, D] and the candidates' differences [n, C] on the same scale."""
    lib = np.array([r.diff() for r in rankings])
    ext = np.array([[(r.extra_a[c] - r.extra_b[c]) * (1 if r.a_better else -1) for c in cands] for r in rankings]) \
        if cands else np.zeros((len(rankings), 0))
    n = np.abs(lib).sum(axis=1, keepdims=True)
    n[n < 1e-12] = 1.0
    return lib / n, ext / n


def bt_fit(X: np.ndarray, prior: np.ndarray, sig: np.ndarray, lo: np.ndarray) -> np.ndarray:
    """MAP of P(winner) = sigmoid(-theta . x / SCALE), Gaussian prior, lower bounds."""
    def f(th):
        z = -(X @ th) / SCALE
        nll = np.logaddexp(0, -z).sum() + 0.5 * np.sum(((th - prior) / sig) ** 2)
        g = (X.T @ ((1 - 1 / (1 + np.exp(-z))) / SCALE)) + (th - prior) / sig ** 2
        return nll, g
    res = minimize(f, prior.copy(), jac=True, method="L-BFGS-B", bounds=[(l, None) for l in lo])
    return res.x


def loglik(X: np.ndarray, th: np.ndarray) -> np.ndarray:
    z = -(X @ th) / SCALE
    return -np.logaddexp(0, -z)


def cv_gain(lib: np.ndarray, ext: np.ndarray, folds: int = 5, seed: int = 0) -> np.ndarray:
    """Per candidate: held-out log-likelihood per ranking with the candidate minus without it."""
    n, D = lib.shape
    C = ext.shape[1]
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    parts = np.array_split(idx, min(folds, n))
    base_ll = np.zeros(n)
    cand_ll = np.zeros((C, n))
    for te in parts:
        tr = np.setdiff1d(idx, te)
        th = bt_fit(lib[tr], np.ones(D), np.ones(D), np.full(D, 0.02))
        base_ll[te] = loglik(lib[te], th)
        for c in range(C):
            X = np.hstack([lib, ext[:, c:c + 1]])
            th2 = bt_fit(X[tr], np.append(np.ones(D), 0.0), np.append(np.ones(D), 2.0), np.append(np.full(D, 0.02), 0.0))
            cand_ll[c, te] = loglik(X[te], th2)
    return (cand_ll - base_ll).mean(axis=1)


def propose(rankings: list[Ranking], cands: list[str], threshold: float, seed: int = 0) -> tuple[str | None, float, np.ndarray]:
    if len(rankings) < 10:
        return None, 0.0, np.zeros(len(cands))
    lib, ext = design(rankings, cands)
    gains = cv_gain(lib, ext, seed=seed)
    k = int(np.argmax(gains))
    return (cands[k] if gains[k] > threshold else None), float(gains[k]), gains


def fitted_weight(rankings: list[Ranking], cand: str) -> tuple[np.ndarray, float]:
    """Library multipliers and the new rule's weight after accepting `cand`."""
    lib, ext = design(rankings, [cand])
    D = lib.shape[1]
    X = np.hstack([lib, ext])
    th = bt_fit(X, np.append(np.ones(D), 0.0), np.append(np.ones(D), 2.0), np.append(np.full(D, 0.02), 0.0))
    return th[:D], float(th[D])
