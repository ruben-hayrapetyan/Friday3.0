"""End-to-end systems for P8: the recommended v3 (sampler + learning + hidden units + supervisor) and the v2 baseline
(staged CP-SAT + v2's inverse optimisation from moves + paces), run against simulated users week after week.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .baseline.cpsat import ModelInfeasible, SolveTimeout, solve
from .core.defaults import REFERENCE_RULES, build_rules
from .engines.prepare import Prepared
from .learn.hidden import PACE_H, U_DIAL, HiddenLearner
from .learn.methods import V2Moves
from .samplers.runner import solve_sampler
from .sim.user import LEARNABLE
from .sim.world import Universe, Week
from .supervisor.discover import fitted_weight, propose

NOMINAL_RATE = 300_000.0  # steps per second the step budget assumes; fixed, so plans do not depend on machine load


def plan_sampler(u: Universe, theta: np.ndarray, extra_w: dict, budget_s: float, seed: int,
                 method: str = "sa_geo", stages: str = "weighted") -> tuple[np.ndarray, float]:
    """stages="weighted": one energy wellbeing + preferences (deadlines walled); "tiered": wellbeing first, then preferences."""
    if stages == "weighted":
        t = time.perf_counter()
        owner = u.plan(theta, extra_w, steps=int(NOMINAL_RATE * budget_s), seed=seed)
        return owner, time.perf_counter() - t
    c = u.planner(theta, extra_w)
    pr = Prepared(c, u.pr.owner, 0, [])
    t = time.perf_counter()
    owner, _ = solve_sampler(pr, budget_s, method, seed, steps_per_s=NOMINAL_RATE)
    return owner, time.perf_counter() - t


def plan_cpsat(u: Universe, theta: np.ndarray, budget_s: float, seed: int, workers: int = 8) -> tuple[np.ndarray, float, str]:
    specs = []
    for d in REFERENCE_RULES:
        d = dict(d)
        if d["name"] in LEARNABLE:
            d["weight"] = float(d.get("weight", 1.0) * theta[LEARNABLE.index(d["name"])])
        specs.append(d)
    specs += [dict(r) for r in u.fixed]
    p = u.sc.build(rules=build_rules(specs))
    p.settings.time_limit_s = budget_s
    p.settings.workers = workers
    p.settings.det_time = (budget_s * 3,) * 3
    t = time.perf_counter()
    try:
        res = solve(p, seed=seed)
        plan, status = res.plan, "/".join(s.status for s in res.stages)
    except (SolveTimeout, ModelInfeasible) as e:
        plan, status = {k: tuple(sorted(it.locked)) for k, it in p.items.items()}, f"FAIL:{type(e).__name__}"
    dt = time.perf_counter() - t
    owner = u.c.owner_from_plan({k: v for k, v in plan.items() if k in u.c.keys})
    return owner, dt, status


@dataclass
class V3System:
    """Wall sampler; Bradley-Terry ranking learning with dial-seeded hidden units; supervisor that proposes rules and
    chooses which pairs to ask (uncertainty sampling)."""
    budget_s: float = 2.0
    method: str = "sa_geo"
    discover_every: int = 2
    discover_from: int = 6  # E014: earlier proposals are often false
    confirm: object = None  # callable(rule name) -> bool: the user's answer to "add this rule?" (None: auto-add)
    threshold: float = 0.05
    candidates: list[str] = field(default_factory=list)
    hidden_mode: str = "dial"
    active: bool = True
    stages: str = "weighted"
    name: str = "v3"

    gate: float = 2.0  # E013: units are used only once they predict rankings this many nats better than taste alone

    def __post_init__(self):
        self.L = HiddenLearner(self.hidden_mode)
        self.L0 = HiddenLearner("none")
        self.extra_w: dict[str, float] = {}
        self.rankings = []
        self.h = np.zeros(self.L.K)
        self.gain = 0.0
        self.ll_units = 0.0
        self.ll_taste = {s: 0.0 for s in (0.02, 0.05, 0.1, 0.2, 0.5)}
        self._pace_week = False
        self.log: list[str] = []

    @property
    def units_on(self) -> bool:
        return self.gain > self.gate

    def start_week(self, checkin: str | None, pace: str | None) -> None:
        self._pace_week = pace is not None
        self.h = self.L.predict_h(checkin, pace)
        if pace is not None and self.L.K:  # a picked pace always clamps the dial units
            self.h[:4] = PACE_H[pace]

    def theta(self) -> np.ndarray:
        if self.units_on or self._pace_week:
            return self.L.theta_eff(self.h)
        return self.L0.theta_eff(np.zeros(0))

    def plan(self, u: Universe, seed: int) -> tuple[np.ndarray, float, str]:
        owner, dt = plan_sampler(u, self.theta(), self.extra_w, self.budget_s, seed, self.method, self.stages)
        return owner, dt, "sampler"

    def select(self):
        if not self.active:
            return None
        th = self.theta()

        committee = self._committee()

        def pick(phis, n):
            """Query-by-committee (E016): the pairs the bootstrap fits disagree on most; before there is enough data,
            uncertainty sampling (the pairs closest to a tie)."""
            pairs = []
            for i in range(len(phis)):
                for j in range(i + 1, len(phis)):
                    d = phis[i] - phis[j]
                    s = np.abs(d).sum()
                    if s <= 1e-9:
                        continue
                    if committee:
                        p = np.mean([(c @ d) < 0 for c in committee])
                        pairs.append((-p * (1 - p), abs(th @ d) / s, i, j))
                    else:
                        pairs.append((0.0, abs(th @ d) / s, i, j))
            pairs.sort()
            return [(i, j) for _, _, i, j in pairs[:n]]
        return pick

    def _committee(self, k: int = 6) -> list[np.ndarray]:
        from .supervisor.discover import bt_fit

        if len(self.rankings) < 10:
            return []
        rng = np.random.default_rng(len(self.rankings))
        X = np.array([r.diff() / max(np.abs(r.diff()).sum(), 1e-12) for r in self.rankings])
        D = X.shape[1]
        out = []
        for _ in range(k):
            idx = rng.integers(0, len(X), size=len(X))
            out.append(bt_fit(X[idx], np.ones(D), np.ones(D), np.full(D, 0.02)))
        return out

    def end_week(self, week: Week, pace: str | None, wk: int) -> None:
        from .learn.hidden import WeekEvidence, _norm_diff

        if week.rankings:  # predictive check, before learning from this week (E013c: against a calibrated baseline)
            X = np.array([_norm_diff(r) for r in week.rankings])
            ev = WeekEvidence(X, 0, 0, None, None)
            self.ll_units += self.L.week_ll(self.L.theta, self.h, ev)
            for s in self.ll_taste:
                z = -(X @ self.L0.theta_eff(np.zeros(0))) / s
                self.ll_taste[s] += float(-np.logaddexp(0, -z).sum())
            self.gain = self.ll_units - max(self.ll_taste.values())
        self.L.add_week(week, pace=pace)
        self.L0.add_week(week, pace=pace)
        self.rankings += week.rankings
        if self.candidates and wk + 1 >= self.discover_from and (wk + 1 - self.discover_from) % self.discover_every == 0:
            cands = [c for c in self.candidates if c not in self.extra_w]
            best, gain, _ = propose(self.rankings, cands, self.threshold, seed=wk)
            if best is not None and self.confirm is not None and not self.confirm(best):
                self.log.append(f"week {wk}: proposed {best} (gain {gain:.3f}); the user said no")
                self.candidates = [c for c in self.candidates if c != best]
                best = None
            if best is not None:
                th_lib, w = fitted_weight(self.rankings, best)
                self.extra_w[best] = max(w, 0.0) * float(np.mean(self.L.theta) / max(np.mean(th_lib), 1e-9))
                self.log.append(f"week {wk}: added {best} (gain {gain:.3f}, weight {self.extra_w[best]:.2f})")


@dataclass
class V2System:
    """Staged CP-SAT; v2's learning outline (max-margin from manual moves only, step cap); paces scale the dial rules."""
    budget_s: float = 30.0
    name: str = "v2"

    def __post_init__(self):
        self.L = V2Moves()
        self.pace: str | None = None
        self.log: list[str] = []

    def start_week(self, checkin: str | None, pace: str | None) -> None:
        self.pace = pace

    def theta(self) -> np.ndarray:
        th = self.L.theta.copy()
        if self.pace is not None:  # a pace is v2's own hidden unit, set by the user
            th = th * np.exp(PACE_H[self.pace] @ U_DIAL)
        return th

    def plan(self, u: Universe, seed: int) -> tuple[np.ndarray, float, str]:
        return plan_cpsat(u, self.theta(), self.budget_s, seed)

    def select(self):
        return None

    def end_week(self, week: Week, pace: str | None, wk: int) -> None:
        self.L.update(week, None, wk)
