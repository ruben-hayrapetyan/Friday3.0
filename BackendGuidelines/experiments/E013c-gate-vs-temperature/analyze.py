"""E013 analysis."""
from pathlib import Path

import numpy as np
import pandas as pd

from fr.bench import boot_ci

HERE = Path(__file__).parent
d = pd.concat([pd.read_csv(f) for f in sorted((HERE / "results").glob("runs*.csv"))])
f = pd.concat([pd.read_csv(x) for x in sorted((HERE / "results").glob("final_inference*.csv"))])
rows = []
for (k, m), x in d.groupby(["kind", "mode"]):
    y = f[(f.kind == k) & (f["mode"] == m)]
    normal = y[y.mood == "normal"]
    nonnormal = y[y.mood != "normal"]
    rows.append(dict(kind=k, mode=m, regret_rel_med=x.regret_rel.median(),
                     regret_ci=tuple(round(v, 3) for v in boot_ci(x.regret_rel)),
                     regret_nonnormal=x[x.mood != "normal"].regret_rel.median(),
                     state_acc=(y.inferred == y.mood).mean(),
                     state_acc_nonnormal=(nonnormal.inferred == nonnormal.mood).mean() if len(nonnormal) else np.nan,
                     false_attr=(normal.inferred != "normal").mean() if len(normal) else np.nan,
                     pred_ll=x.pred_ll.mean()))
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).round(3).to_string(index=False))
# state-or-noise decision per user: cumulative predictive gain of "dial" over "none"
print("\nper-user decision (state if cumulative predictive gain of dial over none > 2 nats):")
for (k, u), x in d.groupby(["kind", "user"]):
    a = x[x["mode"] == "dial"].set_index("week").pred_ll
    b = x[x["mode"] == "none"].set_index("week").pred_ll
    gain = float((a - b).sum())
    print(f"  {k:6s} user {u}: gain {gain:+.2f} -> {'state' if gain > 2 else 'noise'}")
