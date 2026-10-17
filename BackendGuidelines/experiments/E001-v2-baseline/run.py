"""E001: v2 CP-SAT baseline matrix. Usage: uv run python run.py  (from this folder)."""
from __future__ import annotations

import csv
import json
import platform
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from fr.baseline.allocator import allocate
from fr.baseline.cpsat import solve
from fr.core.edf import deadline_feasible
from fr.core.generate import cornell_semester, reference_instance, warm_variant

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:  # one small instance, to check the pipeline end to end
    cfg.update(sizes=[20], seeds=[0], timing_repeats=0)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(msg: str) -> None:
    print(msg, flush=True)
    LOG.write(msg + "\n")
    LOG.flush()


def hardware() -> dict:
    sysctl = lambda k: subprocess.run(["sysctl", "-n", k], capture_output=True, text=True).stdout.strip()  # noqa: E731
    return dict(cpu=sysctl("machdep.cpu.brand_string"), cores=sysctl("hw.ncpu"), ram_bytes=sysctl("hw.memsize"),
                platform=platform.platform(), python=sys.version.split()[0])


def solve_row(sc, mode: str, hint=None, current=None, repeat: int = 0):
    sc.settings.workers = cfg["workers"]
    sc.settings.time_limit_s = cfg["time_limit_s"]
    sc.settings.det_time = tuple(cfg["det_time"])
    p = sc.build(current=current)
    edf = deadline_feasible(p)
    res = solve(p, hint=hint, trace=True)
    ev = res.evaluation
    row = dict(instance=sc.name, n=sc.meta["n"], seed=sc.meta["seed"], mode=mode, repeat=repeat,
               items=len(p.items), slots=p.grid.S, build_s=round(res.build_s, 3), total_s=round(res.total_s, 3),
               edf_feasible=edf.feasible, edf_lmax_min=edf.l_max,
               deadlines=ev.stage_values["deadlines"], wellbeing=ev.stage_values["wellbeing"],
               preferences=ev.stage_values["preferences"], overflow_h=ev.overflow_hours, late_h=round(ev.late_hours, 2),
               misses=len(ev.deadline_misses),
               demoted_locks=len(res.demoted_locks), zero_late=ev.stage_values["deadlines"] == 0,
               edf_optimistic=edf.feasible and ev.stage_values["deadlines"] > 0)
    traces = []
    for sr in res.stages:
        gap = (sr.true_value - sr.bound) / max(1.0, abs(sr.true_value)) if sr.bound is not None else float("nan")
        row[f"{sr.stage}_status"] = sr.status
        row[f"{sr.stage}_wall_s"] = round(sr.wall_s, 3)
        row[f"{sr.stage}_det"] = round(sr.det_time, 3)
        row[f"{sr.stage}_bound"] = round(sr.bound, 1) if sr.bound is not None else None
        row[f"{sr.stage}_gap"] = round(gap, 4)
        row[f"{sr.stage}_first_s"] = round(sr.trace[0][0], 3) if sr.trace else None
        traces += [dict(instance=sc.name, mode=mode, repeat=repeat, stage=sr.stage, t=round(t, 3), obj=o)
                   for t, o in sr.trace]
    return row, traces, res


def main() -> None:
    (HERE / "results" / "hardware.json").write_text(json.dumps(hardware(), indent=1))
    rows, traces = [], []
    for n in cfg["sizes"]:
        for seed in cfg["seeds"]:
            sc = reference_instance(n, seed)
            row, tr, cold = solve_row(sc, "cold")
            rows.append(row); traces += tr
            log(f"n={n} seed={seed} cold total={row['total_s']}s lex={row['deadlines']},{row['wellbeing']},{row['preferences']} "
                f"status={row['deadlines_status']}/{row['wellbeing_status']}/{row['preferences_status']}")
            wsc = warm_variant(sc, seed)
            wsc.meta = dict(sc.meta)
            # previous plan: keep slots of items that still exist
            keep = {k: v for k, v in cold.plan.items() if k in {f"item:{s.id}" for s in wsc.specs}}
            row, tr, _ = solve_row(wsc, "warm", hint=keep, current=keep)
            rows.append(row); traces += tr
            log(f"n={n} seed={seed} warm total={row['total_s']}s lex={row['deadlines']},{row['wellbeing']},{row['preferences']}")
            write(rows, traces)
    n = max(cfg["sizes"])
    for seed in cfg["seeds"][:3] if cfg["timing_repeats"] else []:
        for r in range(1, cfg["timing_repeats"] + 1):
            row, tr, _ = solve_row(reference_instance(n, seed), "cold-repeat", repeat=r)
            rows.append(row)
            log(f"repeat n={n} seed={seed} r={r} total={row['total_s']}s")
    write(rows, traces)

    # executor and allocator timings
    p = reference_instance(cfg["edf_items"], 0).build()
    t = []
    for _ in range(20):
        t0 = time.perf_counter(); deadline_feasible(p); t.append(time.perf_counter() - t0)
    sc = cornell_semester(0)
    t0 = time.perf_counter(); allocate(sc, sc.build()); alloc_s = time.perf_counter() - t0
    (HERE / "results" / "executor_allocator.json").write_text(json.dumps(
        dict(edf_items=cfg["edf_items"], edf_median_ms=float(np.median(t) * 1000), edf_p90_ms=float(np.percentile(t, 90) * 1000),
             allocator_s=alloc_s), indent=1))
    log("done")


def write(rows, traces) -> None:
    keys = sorted({k for r in rows for k in r})
    with (HERE / "results" / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)
    if traces:
        with (HERE / "results" / "traces.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(traces[0])); w.writeheader(); w.writerows(traces)


if __name__ == "__main__":
    main()
