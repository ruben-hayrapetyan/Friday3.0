"""E007: samplers on equal wall clock. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

from fr.bench import update_best
from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester, reference_instance
from fr.engines.api import warmup
from fr.engines.prepare import prepare
from fr.samplers.runner import rate, solve_sampler
from fr.samplers.anneal import protected

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(suites=[["ref", 40]], seeds=[0], budgets_s=[1.0])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def cold_jit_seconds() -> float:
    """numba compile time from an empty cache, in a fresh process."""
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, NUMBA_CACHE_DIR=d)
        code = ("import time;t=time.perf_counter();from fr.engines.api import warmup;warmup();"
                "from fr.samplers.runner import solve_sampler;from fr.engines.prepare import prepare;"
                "from fr.core.generate import reference_instance as r;pr=prepare(r(20,0).build());"
                "solve_sampler(pr,0.5,'pt8');print(time.perf_counter()-t)")
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        try:
            return float(out.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return float("nan")


def main() -> None:
    jit = cold_jit_seconds()
    log(f"cold JIT (empty numba cache, fresh process) {jit:.1f}s")
    warmup()
    rows = []
    for kind, n in cfg["suites"]:
        for seed in cfg["seeds"]:
            sc = reference_instance(n, seed) if kind == "ref" else cornell_semester(seed)
            p = sc.build()
            pr = prepare(p)
            r = rate(pr, protected(pr.c, pr.owner), seed)
            for budget in cfg["budgets_s"]:
                for m in cfg["methods"]:
                    t = time.perf_counter()
                    owner, info = solve_sampler(pr, budget, m, seed, steps_per_s=r)
                    dt = time.perf_counter() - t
                    plan = pr.c.plan_from_owner(owner)
                    v = check(p, plan)
                    lex = evaluate(p, plan).lex()
                    if not v:
                        update_best(sc.name, lex, f"E007/{m}")
                    rows.append(dict(instance=sc.name, kind=kind, n=n, seed=seed, budget_s=budget, method=m,
                                     seconds=round(dt, 3), steps_per_s=round(r), violations=len(v), late=lex[0],
                                     wellbeing=lex[1], preferences=lex[2], jit_cold_s=round(jit, 1)))
                    log(f"{sc.name} {m}@{budget:g}s lex={lex} viol={len(v)} {dt:.2f}s")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
