"""Three schedules to pick from (RQ14). Option 0 is always the recommended plan: the best plan under the learned weights.

Ways to make options 1 and 2 (E022 compares them):
- seeds: the same weights, other random seeds (what "run it again" gives).
- temperature: samples at T > 0 around the recommended plan (E010: diverse, calibrated when T matches the user's noise).
- diverse: re-plan with a price on every (task, slot) the earlier options used, so each option is good *and* different.
- thompson: plans for two weight vectors drawn from the learner's posterior: each option is optimal for a plausible you.
- archetype: plans for two named directions, "lighter" (the rest dials up) and "push" (get ahead), like v2's paces.
- qbc: draw several posterior plans, keep the two that make the pick most informative (mutual information between the
  pick and the weights under the posterior).
Every option comes from the same wall sampler, so every option keeps the hard rules and every avoidable deadline.
Alternatives start from the recommended plan with fewer steps (three options cost about two single plans).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

import numpy as np

from ..sim.user import LEARNABLE, MOOD_EFFECT
from ..sim.world import W_PLAN, Universe, move_scale
from ..samplers.anneal import SAConfig, anneal, protected
from .picks import ChoiceLearner

METHODS = ("seeds", "temperature", "diverse", "thompson", "archetype", "qbc")
ARCHETYPES = {"lighter": MOOD_EFFECT["tired"], "push": MOOD_EFFECT["motivated"]}


@dataclass
class Options:
    plans: list[np.ndarray]  # owners; [0] = recommended
    thetas: list[np.ndarray | None]
    labels: list[str]
    steps: int


def _theta_dir(theta: np.ndarray, effect: dict) -> np.ndarray:
    out = theta.copy()
    for r, f in effect.items():
        out[LEARNABLE.index(r)] *= f
    return out


def _with_overlap_price(c, plans: list[np.ndarray], lam: int):
    """A copy of compiled model c whose preference prices charge `lam` for each (task, slot) an earlier option used."""
    price = c.m.price.copy()
    for owner in plans:
        s = np.flatnonzero(owner >= 0)
        price[2, owner[s].astype(np.int64), s] += lam
    return replace(c, m=c.m._replace(price=price))


def _anneal(u: Universe, c, start, steps, seed, T=None) -> np.ndarray:
    cfg = SAConfig(steps=steps, wts=W_PLAN, seed=seed, t0_scale=0.1, t1_scale=0.003) if T is None else \
        SAConfig(steps=steps, wts=W_PLAN, seed=seed, t0=T, t1=T)
    r = anneal(c, start, cfg, protected(c, u.pr.owner))
    return r.owner if T is None else r.final


def rank(u: Universe, learner: ChoiceLearner, opts: Options, how: str, seed: int = 0) -> Options:
    """Reorder the three so that option 0 is the one Friday expects you to pick (E022 round 2). Alternatives start from
    the recommended plan and get more steps, so they are often better plans than it, even under Friday's own weights.
    map: lowest energy under the learned weights. post: highest pick probability averaged over the posterior."""
    phis = np.stack([u.phi(x) for x in opts.plans])
    if how == "map":
        score = phis @ learner.theta + 1e4 * np.array([u.deadline_cost(x) for x in opts.plans])
    elif how == "post":
        post = learner.sample(64, np.random.default_rng(seed + 11))
        score = -np.mean([learner.choice_probs(phis, t) for t in post], axis=0)
    else:
        raise KeyError(how)
    order = [int(i) for i in np.argsort(score, kind="stable")]
    labels = ["recommended" if k == 0 else opts.labels[i] if i else "first draft" for k, i in enumerate(order)]
    return Options([opts.plans[i] for i in order], [opts.thetas[i] for i in order], labels, opts.steps)


def three(u: Universe, learner: ChoiceLearner, method: str, steps: int = 300_000, alt_frac: float = 0.5, seed: int = 0,
          lam_scale: float = 1.0, pool: int = 6, extra_w: dict | None = None) -> Options:
    """`method` is one of METHODS, optionally with a ranking: "thompson+map" (see rank)."""
    if "+" in method:
        base, how = method.split("+")
        return rank(u, learner, three(u, learner, base, steps, alt_frac, seed, lam_scale, pool, extra_w), how, seed)
    rng = np.random.default_rng(seed)
    th = learner.theta
    rec = u.plan(th, extra_w, steps=steps, seed=seed)
    alt = int(steps * alt_frac)
    plans, thetas, labels = [rec], [th], ["recommended"]
    if method == "seeds":
        for k in (1, 2):
            plans.append(u.plan(th, extra_w, steps=steps, seed=seed + 101 * k))
            thetas.append(th)
            labels.append(f"seed {k}")
    elif method == "temperature":
        c = u.planner(th, extra_w)
        T = move_scale(u, c, rec, seed) * u.p.settings.scale
        for k in (1, 2):
            plans.append(_anneal(u, c, rec, alt, seed + k, T=T))
            thetas.append(th)
            labels.append(f"sample {k}")
    elif method == "diverse":
        c = u.planner(th, extra_w)
        lam = max(1, int(lam_scale * move_scale(u, c, rec, seed) * u.p.settings.scale))
        for k in (1, 2):
            ck = _with_overlap_price(c, plans, lam)
            plans.append(_anneal(u, ck, rec, alt, seed + k))
            thetas.append(th)
            labels.append(f"different {k}")
    elif method == "thompson":
        for k, t in enumerate(learner.sample(2, rng), start=1):
            plans.append(u.plan(t, extra_w, steps=alt, seed=seed + k, start=rec))
            thetas.append(t)
            labels.append(f"plausible {k}")
    elif method == "archetype":
        for k, (name, eff) in enumerate(ARCHETYPES.items(), start=1):
            t = _theta_dir(th, eff)
            plans.append(u.plan(t, extra_w, steps=alt, seed=seed + k, start=rec))
            thetas.append(t)
            labels.append(name)
    elif method == "qbc":
        ts = learner.sample(pool, rng)
        cands = [u.plan(t, extra_w, steps=max(alt // 3, 20_000), seed=seed + k, start=rec) for k, t in enumerate(ts, 1)]
        post = learner.sample(64, np.random.default_rng(seed + 7))
        phi0 = u.phi(rec)
        phis = [u.phi(x) for x in cands]
        best, best_mi = (0, 1), -1.0
        for i, j in itertools.combinations(range(len(cands)), 2):
            P = np.array([learner.choice_probs(np.stack([phi0, phis[i], phis[j]]), t) for t in post])
            pm = P.mean(axis=0)
            mi = float(-(pm * np.log(pm + 1e-12)).sum() + (P * np.log(P + 1e-12)).sum(axis=1).mean())
            if mi > best_mi:
                best, best_mi = (i, j), mi
        for k, i in enumerate(best, start=1):
            plans.append(cands[i])
            thetas.append(ts[i])
            labels.append(f"informative {k}")
    else:
        raise KeyError(method)
    used = steps + (2 * steps if method == "seeds" else 2 * alt if method != "qbc" else pool * max(alt // 3, 20_000))
    return Options(plans, thetas, labels, used)


def distinct(u: Universe, a: np.ndarray, b: np.ndarray) -> float:
    """Share of slots holding work in either plan whose owner differs."""
    work = (a >= 0) | (b >= 0)
    return float(((a != b) & work).sum() / max(work.sum(), 1))
