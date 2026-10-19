"""E016: active querying. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

import numpy as np

from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.sim.user import LEARNABLE, SimUser
from fr.sim.world import Universe, true_energy
from fr.supervisor.discover import SCALE, bt_fit

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(users_per_type=1, reps=1, max_queries=10, pool_per_instance=8)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")
D = len(LEARNABLE)


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def pool(user: SimUser, inst: int, n: int, rng):
    u = Universe(cornell_semester(inst))
    plans = [u.plan(np.exp(rng.normal(0, 0.8, D)), steps=60_000, seed=k) for k in range(n)]
    phi = np.array([u.phi(x) for x in plans])
    e = np.array([true_energy(u, user, x, mood="normal") for x in plans])
    return phi, e


def fit(X, y):
    """X: normalised phi(a) - phi(b); y: 1 if a won. Rows are oriented so the winner comes first."""
    if len(X) == 0:
        return np.ones(D)
    Z = np.where(y[:, None] == 1, X, -X)
    return bt_fit(Z, np.ones(D), np.ones(D), np.full(D, 0.02))


def main() -> None:
    warmup()
    rows = []
    for kind in ("easy", "noisy"):
        for uid in range(cfg["users_per_type"]):
            user = SimUser.make(kind, 8800 + 50 * (kind == "noisy") + uid)
            rng = np.random.default_rng(uid)
            cand_X, cand_e = [], []
            for inst in range(3):
                phi, e = pool(user, 5000 + 10 * uid + inst, cfg["pool_per_instance"], rng)
                for i in range(len(phi)):
                    for j in range(i + 1, len(phi)):
                        d = phi[i] - phi[j]
                        n = np.abs(d).sum()
                        if n > 1e-9:
                            cand_X.append(d / n)
                            cand_e.append((e[i], e[j]))
            cand_X, cand_e = np.array(cand_X), np.array(cand_e)
            phi_t, e_t = pool(user, 5000 + 10 * uid + 7, cfg["pool_per_instance"], rng)
            test = [(phi_t[i] - phi_t[j], e_t[i] < e_t[j]) for i in range(len(phi_t)) for j in range(i + 1, len(phi_t))
                    if e_t[i] != e_t[j]]
            test = [test[k] for k in rng.choice(len(test), size=min(200, len(test)), replace=False)]
            scale = float(np.median(np.abs(cand_e[:, 0] - cand_e[:, 1])))
            for strat in ("random", "uncertainty", "qbc"):
                for rep in range(cfg["reps"]):
                    srng = np.random.default_rng(1000 * rep + uid)
                    asked: list[int] = []
                    y: list[int] = []
                    theta = np.ones(D)
                    for q in range(cfg["max_queries"] + 1):
                        acc = float(np.mean([(theta @ d < 0) == t for d, t in test]))
                        rows.append(dict(kind=kind, user=uid, strategy=strat, rep=rep, queries=q, acc=round(acc, 4)))
                        if q == cfg["max_queries"]:
                            break
                        free = np.setdiff1d(np.arange(len(cand_X)), asked)
                        if strat == "random" or q < 2:
                            k = int(srng.choice(free))
                        elif strat == "uncertainty":
                            k = int(free[np.argmin(np.abs(cand_X[free] @ theta))])
                        else:
                            X, Y = cand_X[asked], np.array(y)
                            votes = []
                            for b in range(6):
                                idx = srng.integers(0, len(asked), size=len(asked))
                                votes.append((cand_X[free] @ fit(X[idx], Y[idx])) < 0)
                            p = np.mean(votes, axis=0)
                            k = int(free[np.argmax(p * (1 - p) + 1e-6 * srng.random(len(free)))])
                        ea, eb = cand_e[k]
                        y.append(int(user.rank(ea, eb, scale)))
                        asked.append(k)
                        theta = fit(cand_X[asked], np.array(y))
            log(f"{kind}-{uid} done")
            with (HERE / "results" / "curves.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
