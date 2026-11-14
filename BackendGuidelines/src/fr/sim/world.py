"""The world a simulated user lives in: one planning instance, Friday's planner, and a week of behavior.

`Universe` compiles the instance once with every rule anybody uses (the library, the user's missing rule, rules the
supervisor proposes), so every plan has one feature vector. Friday's planner sees only the rules it knows, with its
current weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..baseline.cpsat import demote_locks
from ..core.defaults import REFERENCE_RULES, build_rules
from ..core.generate import Scenario
from ..engines.compile import compile_problem
from ..engines.kernel import rule_totals
from ..engines.prepare import prepare
from ..samplers.anneal import SAConfig, anneal, protected
from .user import LEARNABLE, SimUser

W_PLAN = np.array([1e6, 1.0, 1.0])  # deadlines stay a wall; wellbeing and preferences in one weighted sum


class Universe:
    def __init__(self, sc: Scenario, extra_rules: list[dict] | None = None):
        self.sc = sc
        self.extra = [dict(r) for r in (extra_rules or [])]
        self.fixed = [dict(r) for r in sc.extra_rules]  # the user's own fixed rules (e.g. walls); never learned
        self.p = sc.build(rules=build_rules(None, self.fixed + self.extra))
        self.pr = prepare(self.p)
        self.c = self.pr.c
        self.names = self.c.rule_names
        self.learn_ix = np.array([self.names.index(r) for r in LEARNABLE])
        self.extra_ix = {r["name"]: self.names.index(r["name"]) for r in self.extra}
        self.ref_w = {d["name"]: d.get("weight", 1.0) for d in REFERENCE_RULES + self.extra}
        M = self.c.m
        self._work = (np.zeros(M.R, dtype=np.int64), np.zeros(M.M, dtype=np.int64), np.zeros(max(M.G, 1), dtype=np.int64),
                      np.zeros(M.I, dtype=np.int64))
        self._planners: dict = {}

    # -- features (points)
    def totals(self, owner: np.ndarray) -> np.ndarray:
        out, mv, cnt, placed = self._work
        rule_totals(self.c.m, owner, out, mv, cnt, placed)
        return out.astype(np.float64) / self.p.settings.scale

    def phi(self, owner: np.ndarray) -> np.ndarray:
        return self.totals(owner)[self.learn_ix]

    def phi_extra(self, owner: np.ndarray, name: str) -> float:
        return float(self.totals(owner)[self.extra_ix[name]])

    def deadline_cost(self, owner: np.ndarray) -> float:
        t = self.totals(owner)
        return float(sum(t[self.names.index(n)] for n in ("late_work", "quota") if n in self.names))

    # -- Friday's planner with a given weight vector
    def planner(self, theta: np.ndarray, extra_w: dict[str, float] | None = None):
        key = (tuple(np.round(theta, 6)), tuple(sorted((extra_w or {}).items())))
        if key in self._planners:
            return self._planners[key]
        specs = []
        for d in REFERENCE_RULES:
            d = dict(d)
            if d["name"] in LEARNABLE:
                d["weight"] = float(d.get("weight", 1.0) * theta[LEARNABLE.index(d["name"])])
            specs.append(d)
        specs += [dict(r) for r in self.fixed]
        for r in self.extra:
            w = (extra_w or {}).get(r["name"], 0.0)
            if w > 0:
                d = dict(r)
                d["weight"] = float(r.get("weight", 1.0) * w)
                specs.append(d)
        p = self.sc.build(rules=build_rules(specs))
        if self.pr.demoted:
            demote_locks(p, list(self.pr.demoted))
        c = compile_problem(p)
        if len(self._planners) > 64:
            self._planners.clear()
        self._planners[key] = c
        return c

    def plan(self, theta: np.ndarray, extra_w: dict[str, float] | None = None, steps: int = 300_000, seed: int = 0,
             start: np.ndarray | None = None) -> np.ndarray:
        c = self.planner(theta, extra_w)
        start = self.pr.owner if start is None else start
        r = anneal(c, start, SAConfig(steps=steps, wts=W_PLAN, seed=seed, t0_scale=0.1, t1_scale=0.003),
                   protected(c, self.pr.owner))
        return r.owner

    def sample(self, theta: np.ndarray, start: np.ndarray, T: float, steps: int, seed: int,
               extra_w: dict[str, float] | None = None) -> np.ndarray:
        """A sample from p(x) ~ exp(-E_theta(x) / T) by a Metropolis chain from `start` (T in points)."""
        c = self.planner(theta, extra_w)
        T_scaled = T * self.p.settings.scale
        r = anneal(c, start, SAConfig(steps=steps, wts=W_PLAN, seed=seed, t0=T_scaled, t1=T_scaled),
                   protected(c, self.pr.owner))
        return r.final

    def sample_c(self, c, start: np.ndarray, T: float, steps: int, seed: int) -> np.ndarray:
        T_scaled = max(T, 1e-6) * self.p.settings.scale
        r = anneal(c, start, SAConfig(steps=steps, wts=W_PLAN, seed=seed, t0=T_scaled, t1=T_scaled),
                   protected(c, self.pr.owner))
        return r.final

    def perturb(self, owner: np.ndarray, moves: int, seed: int) -> np.ndarray:
        """A random valid neighbor: `moves` accepted moves of a zero-energy chain (every valid move is accepted)."""
        # about one proposal in ten is a valid move, so propose ten times as many
        r = anneal(self.c, owner, SAConfig(steps=moves * 10, wts=np.zeros(3), seed=seed, t0=1.0, t1=1.0),
                   protected(self.c, self.pr.owner))
        return r.final


@dataclass
class Ranking:
    phi_a: np.ndarray
    phi_b: np.ndarray
    a_better: bool
    kind: str  # "pair" | "drag"
    week: int
    extra_a: dict = field(default_factory=dict)
    extra_b: dict = field(default_factory=dict)

    def diff(self) -> np.ndarray:
        """phi(winner) - phi(loser): a correct model has theta . diff < 0."""
        return (self.phi_a - self.phi_b) if self.a_better else (self.phi_b - self.phi_a)


@dataclass
class Week:
    index: int
    mood: str
    friday: np.ndarray
    lived: np.ndarray
    phi_friday: np.ndarray
    phi_lived: np.ndarray
    rankings: list[Ranking]
    skips: int
    blocks: int
    review: float
    checkin: str
    scale: float
    e_true_friday: float
    alternatives: list[np.ndarray] = field(default_factory=list)


def true_energy(u: Universe, user: SimUser, owner: np.ndarray, mood: str | None = None) -> float:
    phi = u.phi(owner)
    miss = u.phi_extra(owner, "missing:fri_sat_evening") if "missing:fri_sat_evening" in u.extra_ix else 0.0
    return user.energy(phi, miss, mood) + 1e4 * u.deadline_cost(owner)


def chunks_in_first_week(u: Universe, owner: np.ndarray) -> int:
    g = u.p.grid
    n, prev = 0, -1
    for s in range(g.S):
        o = int(owner[s])
        if g.day[s] < 7 and o >= 0 and o != prev:
            n += 1
        prev = o
    return n


def move_scale(u: Universe, c, owner: np.ndarray, seed: int = 0) -> float:
    """Median |energy change| of one random valid move under compiled model c, in points."""
    from ..samplers.anneal import calibrate

    med, _ = calibrate(c, owner, protected(c, u.pr.owner), SAConfig(wts=W_PLAN, seed=seed, t0_scale=1.0), n=1500)
    return med / u.p.settings.scale


def live_week(u: Universe, user: SimUser, friday: np.ndarray, theta_friday: np.ndarray, week: int, seed: int,
              chain_steps: int = 4000, n_pool: int = 6, n_pairs: int = 6, pool_steps: int = 4000,
              select=None) -> Week:
    """The user lives Friday's plan for a week.

    Day to day they drift from it by local choices in proportion to exp(-E_true / tau): a short Metropolis chain under the
    true energy (mood included) started at Friday's plan. Rankings are asked on pairs from Friday's own samples at T > 0.
    """
    rng = np.random.default_rng(seed)
    extra_true = {"missing:fri_sat_evening": user.kind.missing_weight} if "missing:fri_sat_evening" in u.extra_ix else {}
    c_true = u.planner(user.theta_now(), extra_true)
    scale = move_scale(u, c_true, friday, seed)
    lived = u.sample_c(c_true, friday, user.kind.choice_tau * scale, chain_steps, int(rng.integers(1 << 30)))
    blocks = chunks_in_first_week(u, lived)
    skips = int(rng.binomial(blocks, min(1.0, user.skip_p())))
    e_fr, e_lv = true_energy(u, user, friday), true_energy(u, user, lived)
    rankings: list[Ranking] = []
    if rng.random() < user.kind.drag_p and e_lv < e_fr - scale:
        rankings.append(Ranking(u.phi(lived), u.phi(friday), True, "drag", week, _extra(u, lived), _extra(u, friday)))
    c_f = u.planner(theta_friday)
    t_f = move_scale(u, c_f, friday, seed + 1)
    pool = [friday] + [u.sample_c(c_f, friday, t_f, pool_steps, int(rng.integers(1 << 30))) for _ in range(n_pool)]
    e_pool = [true_energy(u, user, x) for x in pool]
    # `select(phis, n)` lets an active learner choose which pairs to ask; default: random pairs
    chosen = select([u.phi(x) for x in pool], n_pairs) if select is not None else \
        [tuple(rng.choice(len(pool), size=2, replace=False)) for _ in range(n_pairs)]
    for i, j in chosen:
        rankings.append(Ranking(u.phi(pool[i]), u.phi(pool[j]), user.rank(e_pool[i], e_pool[j], scale), "pair", week,
                                _extra(u, pool[i]), _extra(u, pool[j])))
    return Week(week, user.mood, friday, lived, u.phi(friday), u.phi(lived), rankings, skips, blocks,
                user.review(e_lv - min(e_pool + [e_lv]), scale), user.checkin(), scale, e_fr, pool)


def _extra(u: Universe, owner: np.ndarray) -> dict:
    if not u.extra_ix:
        return {}
    t = u.totals(owner)
    return {name: float(t[k]) for name, k in u.extra_ix.items()}
