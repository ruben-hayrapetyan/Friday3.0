"""Weeks of picking one of three schedules (RQ14, RQ15). A simulated user (sim.user) sees Friday's three options, picks
one by true energy with their answer noise (Bradley-Terry temperature, adversarial flips, an optional lean toward the
recommended option), lives the picked plan, and Friday learns from the pick (and, optionally, the usual pairs and drags).
"""
from __future__ import annotations

import time

import numpy as np

from ..core.generate import cornell_semester
from ..product.options import distinct, three
from ..product.picks import Choice, ChoiceLearner
from .user import LEARNABLE, MISSING_RULE, SimUser
from .world import Universe, live_week, move_scale, true_energy


def pick(user: SimUser, energies: np.ndarray, scale: float, rng: np.random.Generator, p_default: float = 0.0) -> int:
    if p_default and rng.random() < p_default:
        return 0
    if user.kind.flip and rng.random() < user.kind.flip:
        return int(rng.integers(len(energies)))
    t = max(1e-9, user.kind.rank_tau * scale)
    z = -(energies - energies.min()) / t
    p = np.exp(z)
    return int(rng.choice(len(energies), p=p / p.sum()))


def run_user(kind: str, seed: int, method: str, mode: str = "mnl", weeks: int = 10, feedback: bool = True,
             p_default: float = 0.0, steps: int = 300_000, star_steps: int = 600_000, instance_seed: int | None = None,
             alt_frac: float = 0.5, lam_scale: float = 1.0) -> list[dict]:
    """mode: none (no learning) | pairs_only (learn from pairs and drags, ignore picks) | rankbreak | mnl."""
    user = SimUser.make(kind, seed)
    rng = np.random.default_rng(seed + 17)
    L = ChoiceLearner(len(LEARNABLE), mode="mnl" if mode == "pairs_only" else mode, use_pairs=feedback)
    base = seed * 100 if instance_seed is None else instance_seed
    rows = []
    for wk in range(weeks):
        mood = user.step_mood()
        extra = [MISSING_RULE] if user.kind.missing_weight else []
        u = Universe(cornell_semester(base + wk), extra)
        extra_true = {"missing:fri_sat_evening": user.kind.missing_weight} if user.kind.missing_weight else {}
        x_star = u.plan(user.theta_now(), extra_true, steps=star_steps, seed=wk)
        e_star = true_energy(u, user, x_star)
        t0 = time.perf_counter()
        opts = three(u, L, method, steps=steps, seed=wk, alt_frac=alt_frac, lam_scale=lam_scale)
        dt = time.perf_counter() - t0
        E = np.array([true_energy(u, user, x) for x in opts.plans])
        scale = move_scale(u, u.planner(user.theta_now(), extra_true), x_star, wk)
        k = pick(user, E, scale, rng, p_default)
        rankings = []
        if feedback:
            rankings = live_week(u, user, opts.plans[k], L.theta, wk, seed=wk * 7919 + seed).rankings
        choices = [Choice(np.stack([u.phi(x) for x in opts.plans]), k, wk)] if mode not in ("none", "pairs_only") else []
        prev = L.theta.copy()
        cos = float(L.theta @ user.theta / np.linalg.norm(L.theta) / np.linalg.norm(user.theta))
        d = [distinct(u, opts.plans[i], opts.plans[j]) for i, j in ((0, 1), (0, 2), (1, 2))]
        rel = max(abs(e_star), 1.0)
        rows.append(dict(kind=kind, seed=seed, method=method, mode=mode, feedback=feedback, p_default=p_default,
                         week=wk, mood=mood, picked=k, rec_picked=k == 0, regret_rec=(E[0] - e_star) / rel,
                         regret_pick=(E[k] - e_star) / rel, regret_best=(E.min() - e_star) / rel,
                         rec_is_best=int(np.argmin(E)) == 0, distinct_min=min(d), distinct_mean=float(np.mean(d)),
                         cos=cos, seconds=dt, steps=opts.steps, labels="|".join(opts.labels),
                         safe=all(u.deadline_cost(x) <= u.deadline_cost(opts.plans[0]) + 1e-9 for x in opts.plans)))
        L.add(choices, rankings)
        rows[-1]["step"] = float(1 - L.theta @ prev / np.linalg.norm(L.theta) / np.linalg.norm(prev))  # how far one week moved theta
    return rows
