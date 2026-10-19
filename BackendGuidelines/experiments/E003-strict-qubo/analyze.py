"""E003 analysis: tables to stdout, figures to figures/."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
sa = d[d["mode"] == "sa"].copy()
sa["feasible"] = sa.violations == 0
sa["deadline_ok"] = sa.feasible & (sa.misses <= sa.opt_misses)
sa["gap"] = (sa.total - sa.opt_total) / sa.opt_total.clip(lower=1000)
best = sa.sort_values(["deadline_ok", "feasible", "total"], ascending=[False, False, True]).drop_duplicates(["n", "seed", "alpha"])
tab = best.groupby("alpha").agg(feasible=("feasible", "mean"), deadline_ok=("deadline_ok", "mean"),
                                gap_median=("gap", "median"), hard_misses=("misses", "mean"))
print(tab.round(3).to_string())
fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
for n, c in ((6, "C0"), (10, "C1")):
    b = best[best.n == n].groupby("alpha")
    ax[0].plot(b.feasible.mean().index, b.feasible.mean().values, "o-", c=c, label=f"{n} items: no double booking / over-placing")
    ax[0].plot(b.deadline_ok.mean().index, b.deadline_ok.mean().values, "s--", c=c, label=f"{n} items: also no hard deadline missed")
    med = b.gap.median()
    ax[1].plot(med.index, med.values, "o-", c=c, label=f"{n} items")
for a in ax:
    a.set_xscale("log")
    a.set_xlabel("penalty scale alpha (x largest single price)")
ax[0].set_ylabel("share of instances (best T per instance)")
ax[0].legend(fontsize=7)
ax[1].set_yscale("symlog", linthresh=1)
ax[1].set_ylabel("(total - optimum) / optimum, median")
ax[1].legend(fontsize=8)
fig.tight_layout()
fig.savefig(HERE / "figures" / "feasibility_and_gap_vs_penalty.png", dpi=130)
