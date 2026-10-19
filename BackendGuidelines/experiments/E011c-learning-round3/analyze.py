"""E011 analysis: learning curves per user type and learner."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fr.bench import boot_ci

HERE = Path(__file__).parent
d = pd.concat([pd.read_csv(f) for f in sorted((HERE / "results").glob("runs*.csv"))])
W = d.week.max()
last = d[d.week >= W - 3]
rows = []
for (k, L), x in last.groupby(["kind", "learner"]):
    th = x.groupby(["user"]).theta.apply(lambda s: [np.array(list(map(float, t.split()))) for t in s])
    stab = np.mean([np.mean([np.abs(a - b).mean() for a, b in zip(v[1:], v[:-1])]) for v in th if len(v) > 1])
    rows.append(dict(kind=k, learner=L, acc_last4=x.heldout_acc.mean(), regret_rel_med=x.regret_rel.median(),
                     regret_rel_ci=tuple(round(v, 3) for v in boot_ci(x.regret_rel)), cos=x.cos.mean(),
                     rel_err=x.rel_err.mean(), stability=stab))
t = pd.DataFrame(rows)
pd.set_option("display.width", 220)
print(t.round(3).to_string(index=False))
# weeks to converge: first week after which held-out accuracy stays within 0.02 of its final value (per user)
conv = []
for (k, L, u), x in d.groupby(["kind", "learner", "user"]):
    a = x.sort_values("week").heldout_acc.values
    final = a[-1]
    wk = next((i for i in range(len(a)) if np.all(np.abs(a[i:] - final) <= 0.02)), len(a))
    conv.append(dict(kind=k, learner=L, user=u, weeks_to_converge=wk, final=final, first=a[0]))
c = pd.DataFrame(conv).groupby(["kind", "learner"]).agg(weeks_med=("weeks_to_converge", "median"),
                                                        gain=("final", "mean"), start=("first", "mean"))
print("\n", c.round(3).to_string())
kinds = sorted(d.kind.unique())
fig, ax = plt.subplots(1, len(kinds), figsize=(3.2 * len(kinds), 3.2), sharey=True)
for a, k in zip(np.atleast_1d(ax), kinds):
    for L, x in d[d.kind == k].groupby("learner"):
        m = x.groupby("week").heldout_acc.mean()
        a.plot(m.index, m.values, label=L)
    a.set_title(k)
    a.set_xlabel("week")
np.atleast_1d(ax)[0].set_ylabel("held-out ranking accuracy")
np.atleast_1d(ax)[-1].legend(fontsize=7)
fig.tight_layout()
fig.savefig(HERE / "figures" / "learning_curves.png", dpi=130)
