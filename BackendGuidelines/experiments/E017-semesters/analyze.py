"""E017 analysis: v3 vs v3_lex vs v2 over semesters."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fr.bench import boot_ci

HERE = Path(__file__).parent
d = pd.concat([pd.read_csv(f) for f in sorted((HERE / "results").glob("runs*.csv"))])
rows = []
for (k, s), x in d.groupby(["kind", "system"]):
    rows.append(dict(kind=k, system=s, weeks=len(x), regret_rel_med=x.regret_rel.median(),
                     regret_ci=tuple(round(v, 3) for v in boot_ci(x.regret_rel)),
                     regret_last4=x[x.week >= x.week.max() - 3].regret_rel.median(),
                     invalid=(x.violations > 0).mean(), weeks_with_misses=(x.misses > 0).mean(),
                     plan_s_med=x.plan_s.median(), plan_s_p90=x.plan_s.quantile(0.9), cos_last=x[x.week == x.week.max()].cos.mean(),
                     rules_added=x[x.week == x.week.max()].rules.fillna("").str.count("cand:").mean(),
                     rules_correct=x[x.week == x.week.max()].rules_correct.mean()))
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).round(3).to_string(index=False))
print("\nall users:")
print(d.groupby("system").agg(regret_rel_med=("regret_rel", "median"), misses=("misses", "sum"),
                              invalid=("violations", lambda v: int((v > 0).sum())), plan_s_med=("plan_s", "median")).round(3))
fig, ax = plt.subplots(figsize=(6.5, 3.6))
for s, x in d.groupby("system"):
    m = x.groupby("week").regret_rel.median()
    ax.plot(m.index, m.values, "o-", label=s)
ax.set_yscale("symlog", linthresh=0.05)
ax.set_xlabel("week")
ax.set_ylabel("median relative regret (all users)")
ax.legend()
fig.tight_layout()
fig.savefig(HERE / "figures" / "semester_regret.png", dpi=130)
