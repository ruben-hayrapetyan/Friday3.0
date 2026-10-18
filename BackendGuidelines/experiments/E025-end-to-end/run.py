"""E025. Usage: uv run python experiments/E025-end-to-end/run.py <round> <shard> <n_shards> | report"""
from __future__ import annotations

import json
import logging
import sys
import tomllib
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
E019 = HERE.parent / "E019-constraint-parsing"
sys.path.insert(0, str(E019))

from fr.product.constraints import Parse  # noqa: E402
from fr.sim.life import Person, System, live  # noqa: E402

from gold import CASES  # noqa: E402
from score import as_prediction  # noqa: E402

logging.getLogger("fr.core.pwl").setLevel(logging.ERROR)
CFG = tomllib.loads((HERE / "config.toml").read_text())
RES = HERE / "results"


def parsed(case_id: int) -> list:
    """What Sonnet 5.5 (guide2) returned for this text in E019 (first run), from the cache."""
    rnd = "guide2"
    f = E019 / "results" / "raw" / rnd / f"{case_id:03d}-r0.json"
    return list(Parse.model_validate(json.loads(f.read_text())["parse"]).constraints)


def people() -> list[Person]:
    out = []
    for i in range(CFG["people"]):
        prof = CFG["profiles"][i % len(CFG["profiles"])]
        truth = [c for cid in prof for c in as_prediction(CASES[cid]).constraints]
        got = [c for cid in prof for c in parsed(cid)]
        out.append(Person(CFG["pref_kinds"][i % 5], CFG["duration_kinds"][i % 6], 30000 + i, truth, got,
                          p_estimate=CFG["p_estimate"], load=CFG["load"]))
    return out


def systems(rnd: str = "r1") -> list[System]:
    full = dict(options=CFG["options"], ask=CFG["ask"], ask_actual=CFG["ask_actual"], mode=CFG["mode"],
                q_hard=CFG["q_hard"])
    return [System("v3_built", durations="as_given", ask="never", options=None, mode="pairs_only", constraints=False,
                   q_hard=0.5),
            System("full", **full),
            System("full-constraints", **full, constraints=False),
            System("full-durations", **dict(full, ask="never", ask_actual="never"), durations="as_given"),
            System("full-options", **dict(full, options=None, mode="pairs_only"))] if rnd == "r1" else \
        [System(name, **dict(full, **CFG["rounds"][rnd]["systems"][name])) for name in CFG["rounds"][rnd]["systems"]]


def main() -> None:
    if sys.argv[1] == "report":
        report()
        return
    rnd, k, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    RES.mkdir(exist_ok=True)
    rows = []
    jobs = [(p, s) for p in people() for s in systems(rnd)]
    for j, (p, s) in enumerate(jobs):
        if j % n != k:
            continue
        r = live(p, s, CFG["weeks"])
        rows.append(r)
        print({k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in r.items()}, flush=True)
        pd.DataFrame(rows).to_csv(RES / f"runs_{rnd}_{k}.csv", index=False)


def report() -> None:
    d = pd.concat([pd.read_csv(f) for f in sorted(RES.glob("runs_*.csv"))])  # rounds share people; systems differ by name
    g = d.groupby("system").agg(people=("person", "size"), hard_late=("hard_late", "mean"), late_h=("late_h", "mean"),
                                conflict_h_week=("conflict_h_week", "mean"), questions_week=("questions_week", "mean"),
                                regret_rec=("regret_rec", "mean"), regret_pick=("regret_pick", "mean"),
                                rec_picked=("rec_picked", "mean"), cos=("cos", "mean"),
                                plan_s=("plan_s_median", "median")).round(3)
    print(g.to_string())
    g.to_csv(RES / "summary.csv")


if __name__ == "__main__":
    main()
