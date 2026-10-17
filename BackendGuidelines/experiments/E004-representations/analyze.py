"""E004 analysis: per-engine summary (stdout) and figures."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fr.bench import best_known, boot_ci, lex_gaps

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
d["label"] = d.engine + "@" + d.budget_s.astype(int).astype(str) + "s"
best = {i: best_known(i) for i in d.instance.unique()}
g = d.apply(lambda r: pd.Series(lex_gaps((r.late, r.wellbeing, r.preferences), best[r.instance])), axis=1)
d = pd.concat([d.drop(columns=[c for c in g.columns if c in d.columns]), g], axis=1)
d["valid"] = d.violations == 0
# deadline-safe: valid, and zero late whenever zero late is possible (best known late == 0)
d["best_late"] = [best[i][0] for i in d.instance]
d["deadline_safe"] = d.valid & ((d.late == 0) | (d.best_late > 0))
d["lex_best"] = (d.late == d.best_late) & (d.wellbeing == [best[i][1] for i in d.instance])
rows = []
for (lab, kind_n), x in d.groupby(["label", d.kind + d.n.astype(str)]):
    rows.append(dict(engine=lab, suite=kind_n, n=len(x), valid=x.valid.mean(), deadline_safe=x.deadline_safe.mean(),
                     W_gap_med=np.nanmedian(x.wellbeing_gap), P_gap_med=np.nanmedian(x.preferences_gap),
                     W_at_best=(x.wellbeing_gap.fillna(np.inf) <= 0).mean(), seconds_med=x.seconds.median()))
t = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print(t.round(3).to_string(index=False))
print("\nall suites:")
for lab, x in d.groupby("label"):
    wg = x.wellbeing_gap.dropna()
    pg = x.preferences_gap.dropna()
    print(f"{lab:22s} n={len(x):3d} valid={x.valid.mean():.2f} deadline_safe={x.deadline_safe.mean():.2f} "
          f"W-comparable={len(wg)} W_gap_med={np.median(wg) if len(wg) else np.nan:.3f} "
          f"P-comparable={len(pg)} P_gap_med={np.median(pg) if len(pg) else np.nan:.3f} "
          f"P_gap_CI={boot_ci(pg) if len(pg) else ''} t_med={x.seconds.median():.1f}")
fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
labs = sorted(d.label.unique())
ax[0].bar(range(len(labs)), [d[d.label == l].deadline_safe.mean() for l in labs])
ax[0].set_xticks(range(len(labs)), labs, rotation=45, ha="right", fontsize=8)
ax[0].set_ylabel("deadline-safe share")
data = [np.clip(d[d.label == l].preferences_gap.dropna().values, -1, 10) for l in labs]
ax[1].boxplot([x if len(x) else [np.nan] for x in data], tick_labels=labs)
ax[1].set_yscale("symlog", linthresh=0.1)
ax[1].tick_params(axis="x", rotation=45, labelsize=8)
ax[1].set_ylabel("preferences gap to best known\n(only where late and wellbeing tie the best)")
fig.tight_layout()
fig.savefig(HERE / "figures" / "engines.png", dpi=130)
d.to_csv(HERE / "results" / "runs_scored.csv", index=False)
