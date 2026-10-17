"""E014: missing-feature detection. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

import numpy as np

from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.shard import mine, suffix
from fr.learn.methods import RankingQP
from fr.sim.user import LEARNABLE, MISSING_RULE, SimUser
from fr.sim.world import Universe, live_week, true_energy
from fr.supervisor.discover import fitted_weight, propose
from fr.supervisor.grammar import candidates, matches_truth

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(users_per_type=1, tuning_users=1, weeks=4, checkpoints=[4], plan_steps=50000, pairs_per_week=6)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / f"progress{suffix()}.txt").open("a")
CANDS = candidates()
CAND_NAMES = [c["name"] for c in CANDS]


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def main() -> None:
    warmup()
    rows, regret_rows = [], []
    for kind in ("missing", "easy"):
        for uid in range(cfg["users_per_type"]):
            if not mine((kind == "easy") * cfg["users_per_type"] + uid):
                continue
            user = SimUser.make(kind, 9000 + 100 * (kind == "easy") + uid)
            L = RankingQP()
            rankings = []
            last = None
            for wk in range(cfg["weeks"]):
                user.step_mood()
                u = Universe(cornell_semester(3000 + 50 * uid + wk + 1000 * (kind == "easy")), [MISSING_RULE] + CANDS)
                theta = L.planning_theta()
                x_f = u.plan(theta, steps=cfg["plan_steps"], seed=wk)
                week = live_week(u, user, x_f, theta, wk, seed=wk * 31 + uid, n_pairs=cfg["pairs_per_week"])
                L.update(week, u, seed=wk)
                rankings += week.rankings
                last = (u, x_f)
                if wk + 1 in cfg["checkpoints"]:
                    best, gain, gains = propose(rankings, CAND_NAMES, threshold=-np.inf, seed=uid)
                    order = np.argsort(-gains)
                    rows.append(dict(kind=kind, user=uid, tuning=uid < cfg["tuning_users"], week=wk + 1,
                                     n_rankings=len(rankings), best=best, best_gain=round(gain, 5),
                                     best_correct=matches_truth(best), second=CAND_NAMES[order[1]],
                                     second_gain=round(float(gains[order[1]]), 5),
                                     rank_of_truth=int(min(np.flatnonzero([matches_truth(CAND_NAMES[k]) for k in order])) + 1)))
                    log(f"{kind}-{uid} wk{wk + 1}: best={best} gain={gain:.4f} correct={matches_truth(best)}")
            # regret at the last week: flag-only vs auto-add (top candidate) vs oracle
            u, x_f = last
            extra_true = {"missing:fri_sat_evening": user.kind.missing_weight} if user.kind.missing_weight else {}
            e_star = true_energy(u, user, u.plan(user.theta_now(), extra_true, steps=600_000, seed=99))
            best, gain, _ = propose(rankings, CAND_NAMES, threshold=-np.inf, seed=uid)
            th_lib, w_new = fitted_weight(rankings, best)
            scale = float(np.mean(L.theta) / max(np.mean(th_lib), 1e-9))
            plans = {"flag_only": u.plan(L.theta, steps=600_000, seed=98),
                     "auto_add": u.plan(L.theta, {best: w_new * scale}, steps=600_000, seed=98),
                     "oracle_rule": u.plan(L.theta, {"missing:fri_sat_evening": max(user.kind.missing_weight, 1e-9)},
                                           steps=600_000, seed=98)}
            for pol, x in plans.items():
                e = true_energy(u, user, x)
                regret_rows.append(dict(kind=kind, user=uid, tuning=uid < cfg["tuning_users"], policy=pol, rule=best,
                                        rule_weight=round(w_new, 4), gain=round(gain, 5), regret=round(e - e_star, 2),
                                        regret_rel=round((e - e_star) / max(abs(e_star), 1), 4)))
            for name, rs in (("checkpoints", rows), ("regret", regret_rows)):
                with (HERE / "results" / f"{name}{suffix()}.csv").open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rs[0]))
                    w.writeheader()
                    w.writerows(rs)
    log("done")


if __name__ == "__main__":
    main()
