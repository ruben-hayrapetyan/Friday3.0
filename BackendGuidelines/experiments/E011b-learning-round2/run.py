"""E011: learning curves on simulated users. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.shard import mine, suffix
from fr.learn.methods import make_learner
from fr.sim.user import LEARNABLE, MISSING_RULE, SimUser
from fr.sim.world import Universe, live_week, true_energy

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(kinds=["easy"], users=1, weeks=2, plan_steps=50000, ref_steps=50000, heldout_pairs=30)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / f"progress{suffix()}.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def heldout(user: SimUser, n_pairs: int, seed: int):
    """Fixed test pairs: samples of plans under random weight vectors on one held-out instance."""
    rng = np.random.default_rng(seed)
    u = Universe(cornell_semester(900 + seed), [MISSING_RULE])
    pool = []
    for k in range(24):
        theta = np.exp(rng.normal(0, 0.8, size=len(LEARNABLE)))
        pool.append(u.plan(theta, steps=60_000, seed=k))
    feats = [u.phi(x) for x in pool]
    e = [true_energy(u, user, x, mood="normal") for x in pool]
    pairs = []
    while len(pairs) < n_pairs:
        i, j = rng.choice(len(pool), size=2, replace=False)
        if abs(e[i] - e[j]) > 1e-6:
            pairs.append((feats[i] - feats[j], e[i] < e[j]))
    return pairs


def accuracy(theta: np.ndarray, pairs) -> float:
    return float(np.mean([(theta @ d < 0) == truth for d, truth in pairs]))


def recovery(theta: np.ndarray, truth: np.ndarray) -> tuple[float, float]:
    a, b = theta / np.linalg.norm(theta), truth / np.linalg.norm(truth)
    return float(a @ b), float(np.linalg.norm(a - b))


def main() -> None:
    warmup()
    rows = []
    for kind in cfg["kinds"]:
        for uid in range(cfg["users"]):
            if not mine(cfg["kinds"].index(kind) * cfg["users"] + uid):
                continue
            user = SimUser.make(kind, 1000 * (1 + cfg["kinds"].index(kind)) + uid)
            pairs = heldout(user, cfg["heldout_pairs"], uid)
            learners = {name: make_learner(name) for name in cfg["learners"]}
            for wk in range(cfg["weeks"]):
                mood = user.step_mood()
                u = Universe(cornell_semester(100 + 13 * uid + wk + 200 * cfg["kinds"].index(kind)), [MISSING_RULE])
                extra_true = {"missing:fri_sat_evening": user.kind.missing_weight} if user.kind.missing_weight else {}
                x_star = u.plan(user.theta_now(), extra_true, steps=cfg["ref_steps"], seed=wk)
                e_star = true_energy(u, user, x_star)
                for name, L in learners.items():
                    t = time.perf_counter()
                    theta = L.planning_theta()
                    x_f = u.plan(theta, steps=cfg["plan_steps"], seed=wk)
                    week = live_week(u, user, x_f, theta, wk, seed=wk * 7919 + uid)
                    L.update(week, u, seed=wk * 101 + uid)
                    e_f = true_energy(u, user, x_f)
                    cos, err = recovery(L.theta, user.theta)
                    rows.append(dict(kind=kind, user=uid, week=wk, mood=mood, learner=name, regret=round(e_f - e_star, 2),
                                     regret_rel=round((e_f - e_star) / max(abs(e_star), 1.0), 4),
                                     heldout_acc=round(accuracy(L.theta, pairs), 4), cos=round(cos, 4), rel_err=round(err, 4),
                                     n_rankings=len(week.rankings), drags=sum(r.kind == "drag" for r in week.rankings),
                                     skips=week.skips, seconds=round(time.perf_counter() - t, 2),
                                     theta=" ".join(f"{v:.3f}" for v in L.theta)))
                log(f"{kind}-{uid} wk{wk} mood={mood} " + " ".join(
                    f"{r['learner']}:{r['heldout_acc']:.2f}/{r['regret_rel']:.3f}" for r in rows[-len(learners):]))
                with (HERE / "results" / f"runs{suffix()}.csv").open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
