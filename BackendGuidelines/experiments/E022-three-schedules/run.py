"""E022. Usage: uv run python experiments/E022-three-schedules/run.py <round> <shard> <n_shards> | report"""
from __future__ import annotations

import logging
import sys
import tomllib
from pathlib import Path

import pandas as pd

from fr.sim.picks import run_user

logging.getLogger("fr.core.pwl").setLevel(logging.ERROR)  # "coefficient rounds to 0" notices
HERE = Path(__file__).parent
CFG = tomllib.loads((HERE / "config.toml").read_text())
RES = HERE / "results"


def jobs(rnd: str) -> list[tuple]:
    r = CFG["rounds"][rnd]
    return [(k, 100 * CFG["kinds"].index(k) + uid, m) for k in CFG["kinds"] for uid in range(CFG["users"])
            for m in r["methods"]]


def main() -> None:
    if sys.argv[1] == "report":
        report(sys.argv[2] if len(sys.argv) > 2 else None)
        return
    rnd, k, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    r = CFG["rounds"][rnd]
    RES.mkdir(exist_ok=True)
    rows = []
    for j, (kind, seed, method) in enumerate(jobs(rnd)):
        if j % n != k:
            continue
        out = run_user(kind, seed, method, mode=r["mode"], weeks=CFG["weeks"], feedback=r["feedback"],
                       steps=CFG["steps"], star_steps=CFG["star_steps"], alt_frac=r["alt_frac"],
                       lam_scale=r["lam_scale"], p_default=r.get("p_default", 0.0))
        for x in out:
            x["round"] = rnd
        rows += out
        d = pd.DataFrame(out)
        print(rnd, kind, seed, method, f"rec {d.regret_rec.mean():.3f} pick {d.regret_pick.mean():.3f} "
              f"recpick {d.rec_picked.mean():.2f} dist {d.distinct_min.mean():.2f} cos {d.cos.iloc[-1]:.3f}", flush=True)
        pd.DataFrame(rows).to_csv(RES / f"weeks_{rnd}_{k}.csv", index=False)


def report(rnd: str | None) -> None:
    d = pd.concat([pd.read_csv(f) for f in sorted(RES.glob("weeks_*.csv"))])
    if rnd:
        d = d[d["round"] == rnd]
    last = d[d.week == d.week.max()]
    g = d.groupby(["round", "method"]).agg(regret_rec=("regret_rec", "mean"), regret_pick=("regret_pick", "mean"),
                                           regret_best=("regret_best", "mean"), rec_picked=("rec_picked", "mean"),
                                           distinct=("distinct_min", "mean"), safe=("safe", "mean"),
                                           seconds=("seconds", "median"))
    g["cos_end"] = last.groupby(["round", "method"]).cos.mean()
    print(g.round(3).to_string())
    print(d.pivot_table(index="kind", columns="method", values="regret_pick").round(3).to_string())
    print(d.pivot_table(index="kind", columns="method", values="cos", aggfunc="last").round(3).to_string())
    g.round(4).to_csv(RES / "summary.csv")


if __name__ == "__main__":
    main()
