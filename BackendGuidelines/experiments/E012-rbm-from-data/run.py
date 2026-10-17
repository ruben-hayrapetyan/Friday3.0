"""E012: RBM trained on lived weeks only. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import json
import sys
import tomllib
from pathlib import Path

import numpy as np

from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.sim.user import LEARNABLE, SimUser
from fr.sim.world import Universe, live_week, true_energy

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(users=1, weeks=6, train=4, epochs=20)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def encode(u: Universe, owner: np.ndarray) -> np.ndarray:
    """336 bits: (day, hour) x {deep work, other work} for the first planning week."""
    g, p = u.p.grid, u.p
    v = np.zeros((7, 24, 2))
    for s in range(g.S):
        i = int(owner[s])
        if i < 0 or g.day[s] >= 7:
            continue
        it = p.items[u.c.keys[i]]
        sl = g.slots[s]
        hour = (sl.local_minute // 60) % 24
        v[g.day[s], hour, 0 if it.energy == "deep" else 1] = 1
    return v.ravel()


class RBM:
    def __init__(self, n_v: int, n_h: int, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W = rng.normal(0, 0.01, (n_v, n_h))
        self.b = np.zeros(n_v)
        self.c = np.zeros(n_h)
        self.rng = rng

    def free_energy(self, v: np.ndarray) -> np.ndarray:
        return -(v @ self.b) - np.logaddexp(0, v @ self.W + self.c).sum(axis=-1)

    def ph(self, v):
        return 1 / (1 + np.exp(-(v @ self.W + self.c)))

    def pv(self, h):
        return 1 / (1 + np.exp(-(h @ self.W.T + self.b)))

    def fit(self, X: np.ndarray, epochs: int, lr: float, wd: float = 1e-4) -> list[float]:
        self.b = np.log(np.clip(X.mean(0), 1e-3, 1 - 1e-3) / (1 - np.clip(X.mean(0), 1e-3, 1 - 1e-3)))
        rec = []
        for _ in range(epochs):
            ph0 = self.ph(X)
            h0 = (self.rng.random(ph0.shape) < ph0).astype(float)
            v1 = (self.rng.random(X.shape) < self.pv(h0)).astype(float)
            ph1 = self.ph(v1)
            n = len(X)
            self.W += lr * ((X.T @ ph0 - v1.T @ ph1) / n - wd * self.W)
            self.b += lr * (X - v1).mean(0)
            self.c += lr * (ph0 - ph1).mean(0)
            rec.append(float(((X - self.pv(ph0)) ** 2).mean()))
        return rec

    def gibbs(self, n: int, steps: int = 500) -> np.ndarray:
        v = (self.rng.random((n, len(self.b))) < 0.5).astype(float)
        for _ in range(steps):
            h = (self.rng.random((n, len(self.c))) < self.ph(v)).astype(float)
            v = (self.rng.random(v.shape) < self.pv(h)).astype(float)
        return v


def main() -> None:
    warmup()
    out_rows, pair_rows, rerank_rows, sample_rows = [], [], [], []
    for uid in range(cfg["users"]):
        user = SimUser.make("easy", 7000 + uid)
        theta0 = np.ones(len(LEARNABLE))
        X, Xf, weeks = [], [], []
        for wk in range(cfg["weeks"]):
            u = Universe(cornell_semester(2000 + 100 * uid + wk))
            x_f = u.plan(theta0, steps=200_000, seed=wk)
            week = live_week(u, user, x_f, theta0, wk, seed=wk)
            X.append(encode(u, week.lived))
            Xf.append(encode(u, x_f))
            weeks.append((u, x_f, week))
            if wk % 10 == 0:
                log(f"user {uid}: week {wk} collected")
        X, Xf = np.array(X), np.array(Xf)
        tr, te = slice(0, cfg["train"]), slice(cfg["train"], cfg["weeks"])
        rbm = RBM(X.shape[1], cfg["hidden"], seed=uid)
        rec = rbm.fit(X[tr], cfg["epochs"], cfg["lr"])
        fe_lived = rbm.free_energy(X[te])
        fe_friday = rbm.free_energy(Xf[te])
        out_rows.append(dict(user=uid, recon_first=round(rec[0], 4), recon_last=round(rec[-1], 4),
                             fe_lived_mean=round(float(fe_lived.mean()), 2), fe_friday_mean=round(float(fe_friday.mean()), 2),
                             lived_lower_share=round(float((fe_lived < fe_friday).mean()), 3)))
        # pairwise ranking on held-out weeks: pairs of Friday samples of the same week
        rng = np.random.default_rng(uid)
        hits = {"rbm": [], "rules": [], "true": []}
        for (u, x_f, week) in weeks[cfg["train"]:]:
            c1 = u.planner(theta0)
            cands = [x_f] + [u.sample_c(c1, x_f, week.scale, 6000, 50 * k + uid) for k in range(15)]
            e_true = np.array([true_energy(u, user, x) for x in cands])
            e_rules = np.array([theta0 @ u.phi(x) for x in cands])
            e_rbm = rbm.free_energy(np.array([encode(u, x) for x in cands]))
            for _ in range(20):
                i, j = rng.choice(len(cands), size=2, replace=False)
                if e_true[i] == e_true[j]:
                    continue
                truth = e_true[i] < e_true[j]
                hits["rbm"].append((e_rbm[i] < e_rbm[j]) == truth)
                hits["rules"].append((e_rules[i] < e_rules[j]) == truth)
            best = e_true.min()
            rerank_rows.append(dict(user=uid, week=week.index, regret_rbm=round(float(e_true[np.argmin(e_rbm)] - best), 2),
                                    regret_rules=round(float(e_true[np.argmin(e_rules)] - best), 2),
                                    regret_random=round(float(np.mean(e_true) - best), 2)))
        pair_rows.append(dict(user=uid, acc_rbm=round(float(np.mean(hits["rbm"])), 3),
                              acc_rules=round(float(np.mean(hits["rules"])), 3), pairs=len(hits["rbm"])))
        # are RBM samples schedules? compare their work hours with the week's required hours
        S = rbm.gibbs(50)
        need_h = np.array([sum(it.need for it in w[0].p.items.values() if it.amount == "fixed") * 0.25 for w in weeks[:10]])
        work_h = S.reshape(-1, 7, 24, 2).max(axis=3).sum(axis=(1, 2))
        night = S.reshape(-1, 7, 24, 2)[:, :, 1:6, :].max(axis=3).sum(axis=(1, 2))
        sample_rows.append(dict(user=uid, sample_work_h_mean=round(float(work_h.mean()), 1),
                                lived_work_h_mean=round(float(X.reshape(-1, 7, 24, 2).max(axis=3).sum(axis=(1, 2)).mean()), 1),
                                needed_work_h_two_weeks_mean=round(float(need_h.mean()), 1),
                                sample_night_hours_mean=round(float(night.mean()), 2)))
        log(f"user {uid}: {out_rows[-1]} {pair_rows[-1]} {sample_rows[-1]}")
    for name, rows in (("rbm_fit", out_rows), ("pairs", pair_rows), ("rerank", rerank_rows), ("samples", sample_rows)):
        with (HERE / "results" / f"{name}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
