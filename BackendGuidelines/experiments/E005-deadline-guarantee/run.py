"""E005: deadline guarantee. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.baseline.cpsat import GridModel, ModelInfeasible, SolveTimeout
from fr.core.edf import deadline_feasible
from fr.core.evaluate import check, evaluate
from fr.core import generate as G
from fr.engines.api import tiered_budget, warmup
from fr.engines.prepare import prepare
from fr.engines.repair import ensure_deadlines, late_value

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(family_seeds=[0], ref_seeds=[0], stress_seeds=[], truth_s=5.0)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def suite():
    fams = [("tight", G.tight_deadlines), ("overload", G.overload), ("fragmented", G.fragmented), ("deps", G.many_deps),
            ("onesit", G.many_one_sitting), ("pins", G.many_pins)]
    for name, f in fams:
        for s in cfg["family_seeds"]:
            yield name, s, f(s)
    for n in (20, 40, 60):
        for s in cfg["ref_seeds"]:
            yield f"ref{n}", s, G.reference_instance(n, s)
    for s in cfg["ref_seeds"]:
        yield "cornell", s, G.cornell_semester(s)
    for n in (100, 150):
        for s in cfg["stress_seeds"]:
            yield f"stress{n}", s, G.stress(n, s)


def truth(p):
    p.settings.workers = 8
    p.settings.det_time = (cfg["truth_s"] * 3,) * 3
    t = time.perf_counter()
    try:
        r = GridModel(p).solve(stages=["deadlines"], time_limit_s=cfg["truth_s"] / 0.4)  # stage share 0.4 -> truth_s
        sr = r.stages[0]
        return sr.status, sr.true_value, sr.bound, time.perf_counter() - t
    except (SolveTimeout, ModelInfeasible) as e:
        return f"FAIL:{type(e).__name__}", None, None, time.perf_counter() - t


def main() -> None:
    warmup()
    rows = []
    for fam, seed, sc in suite():
        p = sc.build()
        pr = prepare(p)
        edf = deadline_feasible(p)
        tr_status, tr_val, tr_bound, tr_s = truth(sc.build())
        t = time.perf_counter()
        late0 = late_value(pr, pr.owner)
        t_construct = time.perf_counter() - t
        rep = ensure_deadlines(pr, seed=seed, use_cpsat=False)
        rep2 = ensure_deadlines(pr, seed=seed, use_cpsat=True)
        row = dict(family=fam, seed=seed, items=len(p.items), start_violations=pr.violations, demoted=len(pr.demoted),
                   truth_status=tr_status, truth_late=tr_val, truth_bound=tr_bound, truth_s=round(tr_s, 2),
                   edf_feasible=edf.feasible, construct_late=late0, construct_s=round(t_construct, 4),
                   repair_late=rep.late, repair_s=round(rep.seconds, 3), repair_cpsat_late=rep2.late,
                   repair_cpsat_stage=rep2.stage, repair_cpsat_s=round(rep2.seconds, 3))
        # walls vs penalties from the repaired start (3 s each)
        for mode, wall in (("walls", True), ("penalty", False)):
            plan, info = tiered_budget(pr, 3.0, seed, wall=wall, start=rep.owner)
            ev = evaluate(p, plan)
            row[f"{mode}_late"] = ev.stage_values["deadlines"]
            row[f"{mode}_violations"] = len(check(p, plan))
            row[f"{mode}_rose"] = ev.stage_values["deadlines"] > rep.late
        rows.append(row)
        log(f"{fam}-{seed}: truth={tr_status}/{tr_val} edf={edf.feasible} construct={late0} repair={rep.late} "
            f"repair+cp={rep2.late}({rep2.stage}) walls={row['walls_late']} penalty={row['penalty_late']}")
        with (HERE / "results" / "runs.csv").open("w", newline="") as f:
            keys = sorted({k for r in rows for k in r})
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
