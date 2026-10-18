"""E021. Usage: uv run python experiments/E021-durations-downstream/run.py <round> <shard> <n_shards>
             uv run python experiments/E021-durations-downstream/run.py report"""
from __future__ import annotations

import sys
import time
import tomllib
from pathlib import Path

import pandas as pd

from fr.product.durations import make
from fr.sim.durations import COURSES, KINDS, Student, term
from fr.sim.term import TermConfig, simulate

HERE = Path(__file__).parent
CFG = tomllib.loads((HERE / "config.toml").read_text())
RES = HERE / "results"


def jobs(rnd: str) -> list[tuple]:
    r = CFG["rounds"][rnd]
    return [(t, s, m, tuple(q)) for t in CFG["types"] for s in CFG["seeds"] for m in r["models"] for q in r["quantiles"]]


def one(t: str, seed: int, model: str, q: tuple) -> tuple[dict, list[dict]]:
    st = Student.make(t, seed, load=CFG["load"])
    items = term(st, CFG["weeks"] + 2)
    cfg = TermConfig(weeks=CFG["weeks"], q_flex=q[0], q_hard=q[1], steps=tuple(CFG["steps"]), seed=seed)
    t0 = time.perf_counter()
    r = simulate(st, items, make(model, KINDS, COURSES), cfg)
    d, dd = pd.DataFrame(r.rows), pd.DataFrame(r.days)
    h = d[d.hard]
    run = dict(type=t, seed=seed, model=model, q_flex=q[0], q_hard=q[1], n_hard=len(h), hard_late=h.late.mean(),
               hard_late_n=int(h.late.sum()), late_h=h.late_h.sum(), soft_late=d[~d.hard].late.mean(),
               idle_h_day=dd.idle_h.mean(), planned_h_day=dd.planned_h.mean(), seconds=time.perf_counter() - t0)
    for x in r.rows:
        x.update(type=t, seed=seed, model=model, q_flex=q[0], q_hard=q[1])
    return run, r.rows


def main() -> None:
    if sys.argv[1] == "report":
        report()
        return
    rnd, k, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    RES.mkdir(exist_ok=True)
    runs, items = [], []
    for j, job in enumerate(jobs(rnd)):
        if j % n != k:
            continue
        run, rows = one(*job)
        runs.append(run)
        items += rows
        print(rnd, job, f"late {run['hard_late']:.2f} idle {run['idle_h_day']:.2f} {run['seconds']:.0f}s", flush=True)
        pd.DataFrame(runs).to_csv(RES / f"runs_{rnd}_{k}.csv", index=False)
        pd.DataFrame(items).to_csv(RES / f"items_{rnd}_{k}.csv.gz", index=False)


def report() -> None:
    d = pd.concat([pd.read_csv(f) for f in sorted(RES.glob("runs_*.csv"))])
    d["policy"] = d.model + "@p" + (d.q_flex * 100).astype(int).astype(str) + "/p" + (d.q_hard * 100).astype(int).astype(str)
    g = d.groupby("policy").agg(students=("seed", "size"), hard_late=("hard_late", "mean"), late_h=("late_h", "mean"),
                                soft_late=("soft_late", "mean"), idle_h_day=("idle_h_day", "mean"),
                                planned_h_day=("planned_h_day", "mean")).round(3)
    print(g.sort_values("hard_late").to_string())
    print(d.pivot_table(index="type", columns="policy", values="hard_late").round(3).to_string())
    g.to_csv(RES / "summary.csv")


if __name__ == "__main__":
    main()
