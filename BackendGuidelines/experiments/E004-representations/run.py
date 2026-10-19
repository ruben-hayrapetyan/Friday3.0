"""E004: engines on equal budgets. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

from fr.bench import best_known, lex_gaps, update_best
from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance
from fr.engines.api import ENGINES, warmup
from fr.engines.prepare import prepare

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(suites=[["ref", 20]], seeds=[0], sampler_budget_s=3.0, cpsat_budgets_s=[10.0])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def scenario(kind: str, n: int, seed: int):
    return reference_instance(n, seed) if kind == "ref" else cornell_semester(seed)


def main() -> None:
    jit = warmup()
    log(f"numba warm-up (JIT) {jit:.1f}s")
    rows = []
    for kind, n in cfg["suites"]:
        for seed in cfg["seeds"]:
            sc = scenario(kind, n, seed)
            name = sc.name
            for engine in cfg["engines"]:
                budgets = cfg["cpsat_budgets_s"] if engine == "cpsat" else [cfg["sampler_budget_s"]]
                for budget in budgets:
                    sc = scenario(kind, n, seed)
                    p = sc.build()
                    pr = prepare(p)
                    fn = ENGINES[engine]
                    res = fn(p, pr, budget, seed=seed)
                    v = check(p, res.plan)
                    ev = evaluate(p, res.plan)
                    lex = ev.lex()
                    if not v:
                        update_best(name, lex, f"E004/{engine}")
                    row = dict(instance=name, n=n if kind == "ref" else 46, kind=kind, seed=seed, engine=engine,
                               budget_s=budget, seconds=round(res.seconds, 2), violations=len(v),
                               late=lex[0], wellbeing=lex[1], preferences=lex[2], late_h=round(ev.late_hours, 1),
                               misses=len(ev.deadline_misses), overflow_h=ev.overflow_hours,
                               status=res.info.get("status", ""), demoted=len(pr.demoted),
                               start_violations=pr.violations)
                    rows.append(row)
                    log(f"{name} {engine}@{budget:g}s viol={len(v)} lex={lex} t={res.seconds:.1f}")
            _write(rows)
    # gaps against the final best known, computed after everything ran
    for r in rows:
        b = best_known(r["instance"])
        r.update(lex_gaps((r["late"], r["wellbeing"], r["preferences"]), b))
        r["best_late"], r["best_wellbeing"], r["best_preferences"] = b
    _write(rows)
    log("done")


def _write(rows) -> None:
    keys = sorted({k for r in rows for k in r})
    with (HERE / "results" / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
