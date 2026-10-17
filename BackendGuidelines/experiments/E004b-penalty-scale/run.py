"""E004b: penalty scale on the full model. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from dataclasses import replace
from pathlib import Path

import numpy as np

from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance
from fr.engines.api import warmup
from fr.engines.prepare import prepare
from fr.samplers.anneal import SAConfig, anneal, calibrate, protected
from fr.samplers.runner import rate, solve_sampler

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(seeds=[0], budget_s=1.0, lambda_factors=[1.0], deadline_weights=[10.0])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def tiered_penalty(pr, start, steps, wd: float, lam: float, seed: int):
    c = pr.c
    none = np.zeros(c.m.I, dtype=bool)
    out = start
    cap = (-1, -1, -1)
    for tier, w in enumerate(([wd, 1.0, 0.0], [wd, 0.0, 1.0])):
        wts = np.array(w)
        med, _ = calibrate(c, out, none, SAConfig(wts=wts, t0_scale=1.0, wall=False, lam=lam, seed=seed), n=1500)
        cfg_ = SAConfig(steps=steps[tier], wts=wts, wall=False, lam=lam, t0=0.1 * med, t1=0.003 * med, seed=seed + tier,
                        cap=cap)
        r = anneal(c, out, cfg_, none)
        out = r.owner
        if tier == 0:
            cap = (-1, int(r.sv[1]), -1)
    return out


def main() -> None:
    warmup()
    rows = []
    for kind in ("ref40", "cornell"):
        for seed in cfg["seeds"]:
            sc = reference_instance(40, seed) if kind == "ref40" else cornell_semester(seed)
            p = sc.build()
            pr = prepare(p)
            empty = pr.c.owner_from_plan({k: tuple(sorted(it.locked)) for k, it in p.items.items()})
            r = rate(pr, protected(pr.c, pr.owner), seed)
            steps = (int(r * cfg["budget_s"] * 0.35 * 0.85), int(r * cfg["budget_s"] * 0.65 * 0.85))
            med, _ = calibrate(pr.c, pr.owner, protected(pr.c, pr.owner), SAConfig(wts=np.array([1e6, 1.0, 0.0]), t0_scale=1.0))
            variants = [("wall", None, None)]
            variants += [(f"lam{f:g}", 1e6, f * med) for f in cfg["lambda_factors"]]
            variants += [(f"wD{w:g}", w, 1e6) for w in cfg["deadline_weights"]]
            for start_name, start in (("construct", pr.owner), ("empty", empty)):
                for name, wd, lam in variants:
                    t = time.perf_counter()
                    if name == "wall":
                        o, _ = solve_sampler(pr, cfg["budget_s"], "sa_geo", seed, start=start, steps_per_s=r)
                    else:
                        o = tiered_penalty(pr, start, steps, wd, lam, seed)
                    dt = time.perf_counter() - t
                    plan = pr.c.plan_from_owner(o)
                    v = check(p, plan)
                    ev = evaluate(p, plan)
                    rows.append(dict(instance=sc.name, kind=kind, seed=seed, start=start_name, variant=name,
                                     seconds=round(dt, 2), violations=len(v), late=ev.stage_values["deadlines"],
                                     wellbeing=ev.stage_values["wellbeing"], preferences=ev.stage_values["preferences"],
                                     misses=len(ev.deadline_misses), overflow_h=ev.overflow_hours))
                    log(f"{sc.name} {start_name} {name} lex={ev.lex()} misses={len(ev.deadline_misses)} viol={len(v)}")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
