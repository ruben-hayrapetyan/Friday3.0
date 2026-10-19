"""E008: move-set ablation. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.bench import update_best
from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance
from fr.engines.api import warmup
from fr.engines.kernel import MOVE_NAMES
from fr.engines.prepare import prepare
from fr.samplers.anneal import DEFAULT_PROBS, protected
from fr.samplers.runner import rate, solve_sampler

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(seeds=[0], budget_s=1.0)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def variants():
    yield "all", DEFAULT_PROBS.copy()
    for k, name in enumerate(MOVE_NAMES):
        p = DEFAULT_PROBS.copy()
        p[k] = 0.0
        yield f"no_{name}", p
    p = np.zeros_like(DEFAULT_PROBS)
    for name in ("shift", "far", "insert", "drop"):
        p[MOVE_NAMES.index(name)] = DEFAULT_PROBS[MOVE_NAMES.index(name)]
    yield "minimal", p


def main() -> None:
    warmup()
    rows = []
    for kind in ("ref40", "cornell"):
        for seed in cfg["seeds"]:
            sc = reference_instance(40, seed) if kind == "ref40" else cornell_semester(seed)
            p = sc.build()
            pr = prepare(p)
            r = rate(pr, protected(pr.c, pr.owner), seed)
            for name, probs in variants():
                t = time.perf_counter()
                owner, _ = solve_sampler(pr, cfg["budget_s"], "sa_geo", seed, steps_per_s=r, probs=probs)
                dt = time.perf_counter() - t
                plan = pr.c.plan_from_owner(owner)
                v = check(p, plan)
                lex = evaluate(p, plan).lex()
                if not v:
                    update_best(sc.name, lex, f"E008/{name}")
                rows.append(dict(instance=sc.name, kind=kind, seed=seed, variant=name, seconds=round(dt, 2),
                                 violations=len(v), late=lex[0], wellbeing=lex[1], preferences=lex[2]))
                log(f"{sc.name} {name} lex={lex}")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
