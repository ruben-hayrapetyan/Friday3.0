"""E003: strict QUBO / Hopfield on the price-only slice. Usage: uv run python run.py (from this folder)."""
from __future__ import annotations

import csv
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.baseline.cpsat import solve
from fr.core.evaluate import check, evaluate
from fr.core.generate import price_only
from fr.core.rules import price_row
from fr.engines.qubo import build_qubo, decode, qubo_energy, qubo_sa

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in __import__("sys").argv:
    cfg.update(sizes=[6], seeds=[0], alphas=[1, 10], t0_over_p0=[0.05], flips=100000)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def p0_of(p) -> float:
    g = p.grid
    best = 0.0
    for r in p.rules:
        if r.has_price:
            for it in p.items.values():
                if r.applies(it) and it.amount == "fixed":
                    best = max(best, float(price_row(p, r, it)[g.S]))
    return best


def score(p, plan):
    v = check(p, plan)
    ev = evaluate(p, plan)
    kinds = {}
    for x in v:
        kinds[x.code] = kinds.get(x.code, 0) + 1
    return ev, v, kinds


def main() -> None:
    rows = []
    for n in cfg["sizes"]:
        for seed in cfg["seeds"]:
            sc = price_only(seed, n)
            p = sc.build()
            opt = solve(p).evaluation
            P0 = p0_of(p)
            for alpha in cfg["alphas"]:
                q = build_qubo(p, A=alpha * P0, B=alpha * P0 / 2)
                nz = np.abs(q.J[q.J != 0])
                allc = np.concatenate([nz, np.abs(q.h[q.h != 0])])
                dyn = float(allc.max() / allc.min())
                for t0f in cfg["t0_over_p0"]:
                    x = np.zeros(q.n)
                    best = np.zeros(q.n)
                    info = np.zeros(3)
                    t = time.perf_counter()
                    qubo_sa(q.J, q.h, x, np.zeros(q.n), cfg["flips"], t0f * P0, t0f * P0 / 100, seed, best, info, 0)
                    dt = time.perf_counter() - t
                    # the sampler's final state, not its best-ever one, is what a machine at rest returns; take the best-ever
                    plan = decode(q, best)
                    ev, v, kinds = score(p, plan)
                    rows.append(dict(n=n, seed=seed, alpha=alpha, t0_over_p0=t0f, vars=q.n, dyn_range=round(dyn, 1),
                                     seconds=round(dt, 2), qubo_energy=round(float(info[0] + q.const), 1),
                                     violations=len(v), double_booked=kinds.get("double_booked", 0),
                                     over_placed=kinds.get("over_placed", 0), misses=len(ev.deadline_misses),
                                     late=ev.stage_values["deadlines"], wellbeing=ev.stage_values["wellbeing"],
                                     preferences=ev.stage_values["preferences"], total=ev.total,
                                     opt_late=opt.stage_values["deadlines"], opt_wellbeing=opt.stage_values["wellbeing"],
                                     opt_preferences=opt.stage_values["preferences"], opt_total=opt.total,
                                     opt_misses=len(opt.deadline_misses), accepted=int(info[1]), mode="sa"))
                log(f"n={n} seed={seed} alpha={alpha} done ({len(rows)} rows)")
            # Hopfield-style greedy descent at alpha 1 and 10, from empty and from a 5% random start
            for alpha in (1, 10):
                q = build_qubo(p, A=alpha * P0, B=alpha * P0 / 2)
                for start in ("empty", "random"):
                    rng = np.random.default_rng(seed)
                    x = (rng.random(q.n) < 0.05).astype(np.float64) if start == "random" else np.zeros(q.n)
                    best = np.zeros(q.n)
                    info = np.zeros(3)
                    qubo_sa(q.J, q.h, x, np.zeros(q.n), cfg["flips"], 0.0, 0.0, seed, best, info, 1)
                    plan = decode(q, x)  # a descent ends where it stops, so score the final state
                    ev, v, kinds = score(p, plan)
                    rows.append(dict(n=n, seed=seed, alpha=alpha, t0_over_p0=0.0, vars=q.n, violations=len(v),
                                     double_booked=kinds.get("double_booked", 0), over_placed=kinds.get("over_placed", 0),
                                     misses=len(ev.deadline_misses), late=ev.stage_values["deadlines"],
                                     wellbeing=ev.stage_values["wellbeing"], preferences=ev.stage_values["preferences"],
                                     total=ev.total, opt_late=opt.stage_values["deadlines"], opt_total=opt.total,
                                     opt_misses=len(opt.deadline_misses), mode=f"hopfield-{start}"))
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                keys = sorted({k for r in rows for k in r})
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
