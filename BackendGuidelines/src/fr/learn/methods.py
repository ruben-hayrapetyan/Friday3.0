"""Weight learners (RQ5). Each keeps theta: multipliers on the reference weights of the LEARNABLE rules.

- `NoLearning`: theta stays at the hand-set values.
- `V2Moves`: v2's outline (reference section 11): each manual move gives theta . (phi(yours) - phi(Friday's)) <= 0; max-margin
  fit regularised toward the current weights, with a step cap. Moves only.
- `RankingQP`: the v3 supervisor's QP: every ranking and drag is kept as a constraint with slack; weights closest to the
  current ones, a step cap and a prior toward the hand-set values.
- `ContrastiveDivergence`: likelihood learning from lived weeks: theta += eta (<phi>_model - phi_data), the model term from
  short Metropolis chains started at the data (CD-k) or from persistent chains (PCD), plus a prior.
- `Combined`: a CD step, then the ranking QP centred on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np

from ..sim.user import LEARNABLE
from ..sim.world import Ranking, Universe, Week

D = len(LEARNABLE)
THETA_MIN = 0.02


def ranking_qp(theta_c: np.ndarray, rankings: list[Ranking], theta0: np.ndarray, mu: float = 0.1, C: float = 10.0,
               cap: float = 0.5, margin: float = 0.02, extra_dims: int = 0) -> tuple[np.ndarray, float]:
    """argmin |t - theta_c|^2 + mu |t - theta0|^2 + C sum(xi)  s.t.  t . d_k / |d_k|_1 <= -margin + xi_k, xi >= 0,
    t >= THETA_MIN, |t - theta_c| <= cap.  Returns (theta, total slack)."""
    if not rankings:
        return theta_c.copy(), 0.0
    Dm = np.array([r.diff() for r in rankings])
    if extra_dims:
        Dm = np.hstack([Dm, np.array([_extra_diff(r) for r in rankings])])
    norms = np.abs(Dm).sum(axis=1)
    keep = norms > 1e-9
    Dm, norms = Dm[keep], norms[keep]
    if len(Dm) == 0:
        return theta_c.copy(), 0.0
    Dn = Dm / norms[:, None]
    t = cp.Variable(len(theta_c))
    xi = cp.Variable(len(Dn), nonneg=True)
    obj = cp.sum_squares(t - theta_c) + mu * cp.sum_squares(t - theta0) + C * cp.sum(xi)
    cons = [Dn @ t <= -margin + xi, t >= THETA_MIN, cp.abs(t - theta_c) <= cap]
    prob = cp.Problem(cp.Minimize(obj), cons)
    try:
        prob.solve(solver=cp.OSQP, eps_abs=1e-7, eps_rel=1e-7, max_iter=20000)
    except cp.SolverError:
        prob.solve(solver=cp.CLARABEL)
    if t.value is None:
        return theta_c.copy(), float("inf")
    return np.maximum(np.asarray(t.value), THETA_MIN), float(np.sum(xi.value))


def _extra_diff(r: Ranking) -> np.ndarray:
    keys = sorted(r.extra_a)
    a = np.array([r.extra_a[k] for k in keys])
    b = np.array([r.extra_b[k] for k in keys])
    return (a - b) if r.a_better else (b - a)


@dataclass
class Learner:
    name: str = "none"
    theta: np.ndarray = field(default_factory=lambda: np.ones(D))
    theta0: np.ndarray = field(default_factory=lambda: np.ones(D))
    history: list[np.ndarray] = field(default_factory=list)

    def update(self, week: Week, u: Universe, seed: int) -> None:
        self.history.append(self.theta.copy())

    def planning_theta(self) -> np.ndarray:
        return self.theta


class NoLearning(Learner):
    def __init__(self):
        super().__init__("none")


class V2Moves(Learner):
    def __init__(self, cap: float = 0.3):
        super().__init__("v2_moves")
        self.moves: list[Ranking] = []
        self.cap = cap

    def update(self, week, u, seed):
        new = [r for r in week.rankings if r.kind == "drag"]
        if new:
            self.moves += new
            self.theta, _ = ranking_qp(self.theta, self.moves, self.theta0, mu=0.0, cap=self.cap)
        super().update(week, u, seed)


class RankingQP(Learner):
    def __init__(self, mu: float = 0.1, C: float = 10.0, cap: float = 0.5):
        super().__init__("rank_qp")
        self.rankings: list[Ranking] = []
        self.mu, self.C, self.cap = mu, C, cap
        self.slack = 0.0

    def update(self, week, u, seed):
        self.rankings += week.rankings
        self.theta, self.slack = ranking_qp(self.theta, self.rankings, self.theta0, self.mu, self.C, self.cap)
        super().update(week, u, seed)


class ContrastiveDivergence(Learner):
    """theta += eta * (<phi>_model - phi_data) / scale, with RMS-normalised steps and a prior toward theta0."""

    def __init__(self, eta: float = 0.15, k_steps: int = 3000, chains: int = 4, prior: float = 0.05,
                 persistent: bool = False, name: str = "cd"):
        super().__init__(name)
        self.eta, self.k, self.chains, self.prior, self.persistent = eta, k_steps, chains, prior, persistent
        self.rms = np.ones(D)
        self._persist: list[np.ndarray] | None = None

    def model_term(self, week: Week, u: Universe, seed: int) -> np.ndarray:
        e_alt = [float(self.theta @ u.phi(a)) for a in week.alternatives[1:]]
        e_fr = float(self.theta @ week.phi_friday)
        T = float(np.median(np.abs(np.array(e_alt) - e_fr))) or 1.0
        starts = [week.lived] * self.chains
        if self.persistent and self._persist is not None:
            starts = self._persist
        samples = [u.sample(self.theta, s, T, self.k, seed + 17 * c) for c, s in enumerate(starts)]
        if self.persistent:
            self._persist = samples
        return np.mean([u.phi(x) for x in samples], axis=0)

    def gradient(self, week: Week, u: Universe, seed: int) -> np.ndarray:
        return self.model_term(week, u, seed) - week.phi_lived

    def update(self, week, u, seed):
        # CD: one step from fresh chains at the data. PCD: several steps whose chains persist between steps
        # (a new week is a new instance, so chains start at that week's data).
        self._persist = None
        for inner in range(3 if self.persistent else 1):
            g = self.gradient(week, u, seed + 1000 * inner)
            self.rms = 0.8 * self.rms + 0.2 * g * g
            step = self.eta * g / (np.sqrt(self.rms) + 1e-9)
            self.theta = np.maximum(self.theta + step + self.prior * (self.theta0 - self.theta), THETA_MIN)
            self.theta *= self.theta0.sum() / self.theta.sum()  # the likelihood cannot fix the scale (it is the temperature)
        super().update(week, u, seed)


class Combined(ContrastiveDivergence):
    def __init__(self, **kw):
        super().__init__(name="combined", **kw)
        self.rankings: list[Ranking] = []

    def update(self, week, u, seed):
        g = self.gradient(week, u, seed)
        self.rms = 0.8 * self.rms + 0.2 * g * g
        centre = np.maximum(self.theta + self.eta * g / (np.sqrt(self.rms) + 1e-9), THETA_MIN)
        centre *= self.theta0.sum() / centre.sum()
        self.rankings += week.rankings
        self.theta, _ = ranking_qp(centre, self.rankings, self.theta0, mu=0.1, cap=0.5)
        self.history.append(self.theta.copy())


def make_learner(name: str) -> Learner:
    return {"none": NoLearning, "v2_moves": V2Moves, "rank_qp": RankingQP, "cd": ContrastiveDivergence,
            "pcd": lambda: ContrastiveDivergence(persistent=True, name="pcd"), "combined": Combined}[name]()
