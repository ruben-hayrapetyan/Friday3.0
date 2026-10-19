"""E018: weakness hunt. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.bench import update_best
from fr.core import generate as G
from fr.core.builder import spec
from fr.core.edf import deadline_feasible
from fr.core.evaluate import check, evaluate
from fr.engines.api import run_cpsat, tiered_budget, warmup
from fr.engines.prepare import prepare
from fr.engines.repair import ensure_deadlines

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(seeds=[0], budget_s=3.0, cpsat_s=10.0)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def tight_onesit(seed: int):
    sc = G.tight_deadlines(seed, n=10, fill=0.85)
    rng = np.random.default_rng(seed + 9)
    for s in sc.specs:
        if s.title.startswith("tight-"):
            s.shape = "one_sitting"
            s.duration_min = int(G.q15(s.duration_min * rng.uniform(0.6, 1.4), hi=600))
    sc.name = f"tight-onesit-s{seed}"
    return sc


def tight_bigchunk(seed: int):
    sc = G.tight_deadlines(seed, n=10, fill=0.85)
    for s in sc.specs:
        if s.title.startswith("tight-"):
            s.min_chunk_min = 120
    sc.name = f"tight-bigchunk-s{seed}"
    return sc


FAMILIES = {
    "tight_onesit": tight_onesit,
    "tight_bigchunk": tight_bigchunk,
    "deps_long": lambda s: G.many_deps(s, chain=30),
    "pins_heavy": lambda s: G.many_pins(s, n_pins=40),
    "overload2": lambda s: G.overload(s, load=2.2),
    "stress150": lambda s: G.stress(150, s),
}


def v3(p, pr, budget, seed, use_cp):
    t = time.perf_counter()
    rep = ensure_deadlines(pr, seed=seed, use_cpsat=use_cp)
    plan, info = tiered_budget(pr, max(0.5, budget - (time.perf_counter() - t)), seed, start=rep.owner, stages="lexpolish")
    return plan, time.perf_counter() - t, dict(repair_stage=rep.stage, repair_late=rep.late)


def main() -> None:
    warmup()
    rows = []
    for fam, make in FAMILIES.items():
        for seed in cfg["seeds"]:
            for engine in ("v3", "v3_nocp", "cpsat30"):
                sc = make(seed)
                p = sc.build()
                pr = prepare(p)
                edf = deadline_feasible(p).feasible
                if engine == "cpsat30":
                    res = run_cpsat(p, pr, cfg["cpsat_s"], seed)
                    plan, dt, info = res.plan, res.seconds, res.info
                else:
                    plan, dt, info = v3(p, pr, cfg["budget_s"], seed, engine == "v3")
                v = check(p, plan)
                ev = evaluate(p, plan)
                if not v:
                    update_best(sc.name, ev.lex(), f"E018/{engine}")
                rows.append(dict(family=fam, instance=sc.name, seed=seed, engine=engine, items=len(p.items),
                                 seconds=round(dt, 2), violations=len(v), late=ev.stage_values["deadlines"],
                                 wellbeing=ev.stage_values["wellbeing"], preferences=ev.stage_values["preferences"],
                                 late_h=round(ev.late_hours, 1), misses=len(ev.deadline_misses), edf_feasible=edf,
                                 start_violations=pr.violations, demoted=len(pr.demoted),
                                 **{k: str(val) for k, val in info.items() if k in ("status", "repair_stage", "repair_late")}))
                log(f"{sc.name} {engine} lex={ev.lex()} viol={len(v)} misses={len(ev.deadline_misses)} {dt:.1f}s {info}")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                keys = sorted({k for r in rows for k in r})
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
