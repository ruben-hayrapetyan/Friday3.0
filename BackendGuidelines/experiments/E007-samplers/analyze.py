"""E007 analysis: per method x budget, gaps to best known (lexicographic reading), success rate."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fr.bench import best_known, boot_ci, lex_gaps

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
best = {i: best_known(i) for i in d.instance.unique()}
g = d.apply(lambda r: pd.Series(lex_gaps((r.late, r.wellbeing, r.preferences), best[r.instance])), axis=1)
d = pd.concat([d, g], axis=1)
d["success"] = (d.violations == 0) & (d.late == [best[i][0] for i in d.instance])
# a single scalar per run for ranking methods: rank of its lexicographic value among all runs on the instance x budget
d["lexkey"] = list(zip(d.late, d.wellbeing, d.preferences))
d["rank"] = d.groupby(["instance", "budget_s"]).lexkey.rank(method="average")
rows = []
for (b, m), x in d.groupby(["budget_s", "method"]):
    wg, pg = x.wellbeing_gap.dropna(), x.preferences_gap.dropna()
    rows.append(dict(budget=b, method=m, n=len(x), success=x.success.mean(), mean_rank=x["rank"].mean(),
                     W_gap_med=np.median(wg) if len(wg) else np.nan, W_at_best=(x.wellbeing_gap.fillna(np.inf) <= 0).mean(),
                     P_gap_med=np.median(pg) if len(pg) else np.nan, P_comparable=len(pg),
                     sec_med=x.seconds.median()))
t = pd.DataFrame(rows).sort_values(["budget", "mean_rank"])
pd.set_option("display.width", 200)
print(t.round(3).to_string(index=False))
print("cold JIT seconds:", d.jit_cold_s.iloc[0], " steps/s median:", d.steps_per_s.median())
fig, ax = plt.subplots(figsize=(8, 3.8))
for b, c in zip(sorted(d.budget_s.unique()), ("C0", "C1")):
    x = t[t.budget == b]
    ax.bar(np.arange(len(x)) + (0.4 if c == "C1" else 0), x.mean_rank, width=0.4, label=f"{b:g} s", color=c)
    ax.set_xticks(np.arange(len(x)) + 0.2, x.method, rotation=30, ha="right")
ax.set_ylabel("mean lexicographic rank (lower is better)")
ax.legend()
fig.tight_layout()
fig.savefig(HERE / "figures" / "sampler_ranks.png", dpi=130)
