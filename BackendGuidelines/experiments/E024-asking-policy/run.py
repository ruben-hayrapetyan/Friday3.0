"""E024. Usage: uv run python experiments/E024-asking-policy/run.py <shard> <n_shards> | report"""
from __future__ import annotations

import math
import sys
import time
import tomllib
from dataclasses import replace
from pathlib import Path

import pandas as pd

from fr.product.durations import make
from fr.sim.durations import COURSES, KINDS, STUDENT_TYPES, Student, term
from fr.sim.term import HARD, TermConfig, simulate

HERE = Path(__file__).parent
CFG = tomllib.loads((HERE / "config.toml").read_text())
RES = HERE / "results"
Z80 = 0.8416


def estimate_policy(name: str):
    if name == "never":
        return None
    if name == "always":
        return lambda it, model, now, week: True
    if name == "spread":
        return lambda it, model, now, week: model.predict(it.course, it.kind, None, week)[1] >= 0.45
    if name.startswith("voi"):
        need = float(name[3:])

        def voi(it, model, now, week):
            if it.kind not in HARD:
                return False
            m, s0 = model.predict(it.course, it.kind, None, week)
            _, s1 = model.predict(it.course, it.kind, math.exp(m), week)  # the spread an estimate would leave
            return math.exp(m) * (math.exp(Z80 * s0) - math.exp(Z80 * s1)) >= need
        return voi
    raise KeyError(name)


def actual_policy(name: str):
    if name == "never":
        return None
    if name == "always":
        return lambda it, model, week: True
    if name == "budget2":
        used: dict[int, int] = {}

        def budget(it, model, week):
            w = int(week)
            if used.get(w, 0) >= 2:
                return False
            used[w] = used.get(w, 0) + 1
            return True
        return budget
    raise KeyError(name)


def jobs():
    return [(t, s, tuple(c)) for t in CFG["types"] for s in CFG["seeds"] for c in CFG["conditions"]]


def main() -> None:
    if sys.argv[1] == "report":
        report()
        return
    k, n = int(sys.argv[1]), int(sys.argv[2])
    RES.mkdir(exist_ok=True)
    runs = []
    for j, (t, seed, (pe, pa)) in enumerate(jobs()):
        if j % n != k:
            continue
        kind = replace(STUDENT_TYPES[t], p_estimate=CFG["p_estimate"], p_record=CFG["p_record"])
        st = Student.make(kind, seed, load=CFG["load"])
        items = term(st, CFG["weeks"] + 2)
        cfg = TermConfig(weeks=CFG["weeks"], steps=tuple(CFG["steps"]), seed=seed)
        t0 = time.perf_counter()
        r = simulate(st, items, make(CFG["model"], KINDS, COURSES), cfg, estimate_policy(pe), actual_policy(pa))
        d, dd = pd.DataFrame(r.rows), pd.DataFrame(r.days)
        h = d[d.hard]
        asked = pd.DataFrame(r.asked) if r.asked else pd.DataFrame(columns=["what"])
        runs.append(dict(type=t, seed=seed, ask_estimate=pe, ask_actual=pa, hard_late=h.late.mean(), late_h=h.late_h.sum(),
                         idle_h_day=dd.idle_h.mean(), q_estimates=int((asked.what == "estimate").sum()),
                         q_actuals=int((asked.what == "actual").sum()), weeks=CFG["weeks"],
                         seconds=time.perf_counter() - t0))
        print(runs[-1], flush=True)
        pd.DataFrame(runs).to_csv(RES / f"runs_{k}.csv", index=False)


def report() -> None:
    d = pd.concat([pd.read_csv(f) for f in sorted(RES.glob("runs_*.csv"))])
    d["questions_per_week"] = (d.q_estimates + d.q_actuals) / d.weeks
    g = d.groupby(["ask_estimate", "ask_actual"]).agg(students=("seed", "size"), hard_late=("hard_late", "mean"),
                                                       late_h=("late_h", "mean"), idle_h_day=("idle_h_day", "mean"),
                                                       questions_per_week=("questions_per_week", "mean")).round(3)
    print(g.to_string())
    g.to_csv(RES / "summary.csv")


if __name__ == "__main__":
    main()
