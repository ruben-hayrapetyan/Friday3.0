"""E006b: stage handling round 2. Usage: uv run python run.py [--smoke] (from this folder)."""
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
from fr.engines.api import _rate, warmup
from fr.engines.prepare import prepare
from fr.samplers.anneal import SAConfig, anneal, protected
from fr.samplers.tiered import W_DEADLINE

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(seeds=[0], budget_s=2.0)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def two_phase(pr, budget, seed, w1, share1, cap_after):
    t = time.perf_counter()
    c = pr.c
    prot = protected(c, pr.owner)
    rate = _rate(c, pr.owner, prot, seed)
    left = max(0.05, budget - (time.perf_counter() - t)) * 0.9
    n1, n2 = int(rate * left * share1), int(rate * left * (1 - share1))
    base = SAConfig(seed=seed, t0_scale=0.1, t1_scale=0.003)
    r1 = anneal(c, pr.owner, replace(base, steps=n1, wts=np.array(w1)), prot)
    if n2 <= 0:
        return r1.owner
    cap = (-1, r1.sv[1], -1) if cap_after else (-1, -1, -1)
    r2 = anneal(c, r1.owner, replace(base, steps=n2, wts=np.array([W_DEADLINE, 0.0, 1.0]), cap=cap, seed=seed + 1), prot)
    return r2.owner


VARIANTS = {
    "tiered": lambda pr, b, s: two_phase(pr, b, s, [W_DEADLINE, 1.0, 0.0], 0.35, True),
    "tiered_eps": lambda pr, b, s: two_phase(pr, b, s, [W_DEADLINE, 1.0, 0.001], 0.35, True),
    "weighted_1000": lambda pr, b, s: two_phase(pr, b, s, [W_DEADLINE, 1000.0, 1.0], 1.0, False),
    "lexpolish": lambda pr, b, s: two_phase(pr, b, s, [W_DEADLINE, 1000.0, 1.0], 0.6, True),
}


def main() -> None:
    warmup()
    rows = []
    for kind in ("ref40", "cornell"):
        for seed in cfg["seeds"]:
            sc = reference_instance(40, seed) if kind == "ref40" else cornell_semester(seed)
            p = sc.build()
            pr = prepare(p)
            for name, fn in VARIANTS.items():
                t = time.perf_counter()
                owner = fn(pr, cfg["budget_s"], seed)
                dt = time.perf_counter() - t
                plan = pr.c.plan_from_owner(owner)
                v = check(p, plan)
                lex = evaluate(p, plan).lex()
                if not v:
                    update_best(sc.name, lex, f"E006b/{name}")
                rows.append(dict(instance=sc.name, kind=kind, seed=seed, variant=name, seconds=round(dt, 2),
                                 violations=len(v), late=lex[0], wellbeing=lex[1], preferences=lex[2]))
                log(f"{sc.name} {name} lex={lex} {dt:.1f}s")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
