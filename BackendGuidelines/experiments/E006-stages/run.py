"""E006: stage handling. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from dataclasses import replace
from pathlib import Path

import numpy as np

from fr.bench import update_best
from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance
from fr.engines.api import _rate, tiered_budget, warmup
from fr.engines.prepare import prepare
from fr.samplers.anneal import SAConfig, anneal, protected
from fr.samplers.tiered import W_DEADLINE

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(seeds=[0], budget_s=2.0, ratios=[1, 1000])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def weighted(pr, budget, seed, r):
    t = time.perf_counter()
    prot = protected(pr.c, pr.owner)
    rate = _rate(pr.c, pr.owner, prot, seed)
    steps = int(rate * max(0.05, budget - (time.perf_counter() - t)) * 0.9)
    res = anneal(pr.c, pr.owner, SAConfig(steps=steps, wts=np.array([W_DEADLINE, float(r), 1.0]), seed=seed,
                                          t0_scale=0.1, t1_scale=0.003), prot)
    return pr.c.plan_from_owner(res.owner)


def tiered_tol(pr, budget, seed, tol):
    """Tiered, but the wellbeing cap is (1 + tol) x the tier-1 value."""
    from fr.samplers import anneal as A

    t = time.perf_counter()
    c = pr.c
    prot = protected(c, pr.owner)
    rate = _rate(c, pr.owner, prot, seed)
    left = max(0.05, budget - (time.perf_counter() - t))
    n1, n2 = int(rate * left * 0.35 * 0.9), int(rate * left * 0.65 * 0.9)
    base = SAConfig(seed=seed, t0_scale=0.1, t1_scale=0.003)
    r1 = anneal(c, pr.owner, replace(base, steps=n1, wts=np.array([W_DEADLINE, 1.0, 0.0])), prot)
    cap = (-1, int(r1.sv[1] * (1 + tol)), -1)
    r2 = anneal(c, r1.owner, replace(base, steps=n2, wts=np.array([W_DEADLINE, 0.0, 1.0]), cap=cap, seed=seed + 1), prot)
    return c.plan_from_owner(r2.owner)


def main() -> None:
    warmup()
    rows = []
    for kind in ("ref40", "cornell"):
        for seed in cfg["seeds"]:
            sc = reference_instance(40, seed) if kind == "ref40" else cornell_semester(seed)
            p = sc.build()
            pr = prepare(p)
            variants = {"tiered": lambda: tiered_budget(pr, cfg["budget_s"], seed)[0],
                        "tiered_tol5": lambda: tiered_tol(pr, cfg["budget_s"], seed, 0.05)}
            for r in cfg["ratios"]:
                variants[f"weighted_{r}"] = (lambda r=r: weighted(pr, cfg["budget_s"], seed, r))
            for name, fn in variants.items():
                t = time.perf_counter()
                plan = fn()
                dt = time.perf_counter() - t
                v = check(p, plan)
                lex = evaluate(p, plan).lex()
                if not v:
                    update_best(sc.name, lex, f"E006/{name}")
                rows.append(dict(instance=sc.name, kind=kind, seed=seed, variant=name, seconds=round(dt, 2),
                                 violations=len(v), late=lex[0], wellbeing=lex[1], preferences=lex[2]))
                log(f"{sc.name} {name} lex={lex} viol={len(v)} {dt:.1f}s")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
