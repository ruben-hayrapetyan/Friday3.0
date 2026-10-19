"""E009: warm replans, churn, determinism. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.bench import update_best
from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance, warm_variant
from fr.engines.api import run_cpsat, warmup
from fr.engines.construct import construct
from fr.engines.prepare import prepare
from fr.samplers.anneal import protected
from fr.samplers.runner import rate, solve_sampler

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(suites=[["ref", 40]], seeds=[0], prev_budget_s=1.0, sampler_budgets_s=[0.5], cpsat_budgets_s=[10.0])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def churn_hours(p, prev: dict, new: dict) -> float:
    """Hours of work of items present in both plans that are no longer where they were."""
    g = p.grid
    moved = 0
    for k, slots in prev.items():
        if k in new:
            moved += sum(int(g.units[s]) for s in set(slots) - set(new[k]))
    return moved * 0.25


def main() -> None:
    warmup()
    rows = []
    for kind, n in cfg["suites"]:
        for seed in cfg["seeds"]:
            sc = reference_instance(n, seed) if kind == "ref" else cornell_semester(seed)
            p0 = sc.build()
            pr0 = prepare(p0)
            prev_owner, _ = solve_sampler(pr0, cfg["prev_budget_s"], "sa_geo", seed)
            prev = pr0.c.plan_from_owner(prev_owner)
            wsc = warm_variant(sc, seed)
            keep = {k: v for k, v in prev.items() if k in {f"item:{s.id}" for s in wsc.specs}}

            def fresh():
                wp = wsc.build(current=keep)
                return wp, prepare(wp)

            wp, pr = fresh()
            base = pr.c.owner_from_plan({k: tuple(s for s in v if pr.c.m.allowed[pr.c.keys.index(k), s])
                                         for k, v in keep.items() if k in pr.c.keys})
            start = construct(pr.c, base=base)
            r = rate(pr, protected(pr.c, start), seed)

            def record(method, budget, plan, dt, extra=None):
                v = check(wp, plan)
                lex = evaluate(wp, plan).lex()
                if not v:
                    update_best(wsc.name, lex, f"E009/{method}")
                row = dict(instance=wsc.name, kind=kind, n=n, seed=seed, method=method, budget_s=budget,
                           seconds=round(dt, 3), violations=len(v), late=lex[0], wellbeing=lex[1], preferences=lex[2],
                           churn_h=churn_hours(wp, keep, plan))
                row.update(extra or {})
                rows.append(row)
                log(f"{wsc.name} {method}@{budget:g} lex={lex} churn={row['churn_h']} {dt:.2f}s {extra or ''}")

            for budget in cfg["sampler_budgets_s"]:
                for method, st0, t0s in (("sampler_warm", start, 0.01), ("sampler_cold", None, 0.1)):
                    t = time.perf_counter()
                    o, _ = solve_sampler(pr, budget, "sa_geo", seed, start=st0, steps_per_s=r, t0s=t0s)
                    dt = time.perf_counter() - t
                    o2, _ = solve_sampler(pr, budget, "sa_geo", seed, start=st0, steps_per_s=r, t0s=t0s)
                    record(method, budget, pr.c.plan_from_owner(o), dt, dict(identical_rerun=bool((o == o2).all())))
            for budget in cfg["cpsat_budgets_s"]:
                wp2, pr2 = fresh()
                res = run_cpsat(wp2, pr2, budget, seed, hint=keep)
                extra = dict(status=res.info.get("status", ""))
                if budget == min(cfg["cpsat_budgets_s"]):
                    wp3, pr3 = fresh()
                    res2 = run_cpsat(wp3, pr3, budget, seed, hint=keep)
                    extra["identical_rerun"] = res.plan == res2.plan
                record(f"cpsat_warm", budget, res.plan, res.seconds, extra)
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                keys = sorted({k for r in rows for k in r})
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
