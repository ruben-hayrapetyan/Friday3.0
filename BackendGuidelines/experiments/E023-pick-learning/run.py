"""E023. Usage: uv run python experiments/E023-pick-learning/run.py <shard> <n_shards> | report"""
from __future__ import annotations

import logging
import sys
import tomllib
from pathlib import Path

import pandas as pd

from fr.sim.picks import run_user

logging.getLogger("fr.core.pwl").setLevel(logging.ERROR)
HERE = Path(__file__).parent
CFG = tomllib.loads((HERE / "config.toml").read_text())
RES = HERE / "results"


def jobs():
    return [(k, 100 * CFG["kinds"].index(k) + uid, tuple(c)) for k in CFG["kinds"] for uid in range(CFG["users"])
            for c in CFG["conditions"]]


def main() -> None:
    if sys.argv[1] == "report":
        report()
        return
    k, n = int(sys.argv[1]), int(sys.argv[2])
    RES.mkdir(exist_ok=True)
    rows = []
    for j, (kind, seed, (mode, fb, pd_)) in enumerate(jobs()):
        if j % n != k:
            continue
        out = run_user(kind, seed, CFG["method"], mode=mode, weeks=CFG["weeks"], feedback=fb, p_default=pd_,
                       steps=CFG["steps"], star_steps=CFG["star_steps"], alt_frac=CFG["alt_frac"],
                       lam_scale=CFG["lam_scale"])
        rows += out
        d = pd.DataFrame(out)
        print(kind, seed, mode, fb, pd_, f"recpick {d.rec_picked.mean():.2f} late {d[d.week >= 8].rec_picked.mean():.2f} "
              f"rec {d.regret_rec.mean():.3f} cos {d.cos.iloc[-1]:.3f}", flush=True)
        pd.DataFrame(rows).to_csv(RES / f"weeks_{k}.csv", index=False)


def report() -> None:
    d = pd.concat([pd.read_csv(f) for f in sorted(RES.glob("weeks_*.csv"))])
    d["cond"] = d["mode"] + d.feedback.map({True: "+feedback", False: ""}) + d.p_default.map(lambda x: f" lean{x}" if x else "")
    late = d[d.week >= 8]
    g = d.groupby("cond").agg(rec_picked=("rec_picked", "mean"), regret_rec=("regret_rec", "mean"),
                              step=("step", "mean"))
    g["rec_picked_wk8plus"] = late.groupby("cond").rec_picked.mean()
    g["regret_rec_wk8plus"] = late.groupby("cond").regret_rec.mean()
    g["cos_end"] = d[d.week == d.week.max()].groupby("cond").cos.mean()
    print(g.round(3).sort_values("rec_picked_wk8plus", ascending=False).to_string())
    print(late.pivot_table(index="kind", columns="cond", values="rec_picked").round(2).to_string())
    g.round(4).to_csv(RES / "summary.csv")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for cond, x in d[d.p_default == 0].groupby("cond"):
        c = x.groupby("week").regret_rec.mean().rolling(3, min_periods=1).mean()
        ax.plot(c.index, c.values, "o-", ms=3, label=cond)
    ax.set_xlabel("week")
    ax.set_ylabel("regret of the recommended plan (3-week mean)")
    ax.legend(fontsize=7)
    ax.set_title("Learning from the pick (E023, 15 tuning users)", fontsize=9)
    fig.tight_layout()
    (HERE / "figures").mkdir(exist_ok=True)
    fig.savefig(HERE / "figures" / "regret_by_week.png", dpi=130)


if __name__ == "__main__":
    main()
