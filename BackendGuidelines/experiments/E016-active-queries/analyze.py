"""E016 analysis: queries to reach 85% / 90% held-out accuracy."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "curves.csv")
Q = d.queries.max()
rows = []
for (k, s), x in d.groupby(["kind", "strategy"]):
    out = {}
    for target in (0.80, 0.85, 0.90):
        need = []
        for (u, rep), y in x.groupby(["user", "rep"]):
            hit = y[y.acc >= target].queries
            need.append(hit.min() if len(hit) else Q + 1)
        out[f"q{int(target * 100)}_med"] = float(np.median(need))
        out[f"q{int(target * 100)}_reached"] = float(np.mean(np.array(need) <= Q))
    out.update(kind=k, strategy=s, acc_at_20=x[x.queries == 20].acc.mean(), acc_at_Q=x[x.queries == Q].acc.mean())
    rows.append(out)
print(pd.DataFrame(rows).round(3).to_string(index=False))
fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
for a, k in zip(ax, ("easy", "noisy")):
    for s, x in d[d.kind == k].groupby("strategy"):
        m = x.groupby("queries").acc.mean()
        a.plot(m.index, m.values, label=s)
    a.set_title(k)
    a.set_xlabel("queries")
ax[0].set_ylabel("held-out accuracy")
ax[1].legend()
fig.tight_layout()
fig.savefig(HERE / "figures" / "active_queries.png", dpi=130)
