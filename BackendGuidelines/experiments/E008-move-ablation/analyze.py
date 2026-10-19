"""E008 analysis: paired comparison of each ablation against all moves."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
d["key"] = list(zip(d.late, d.wellbeing, d.preferences))
base = d[d.variant == "all"].set_index("instance")
rows = []
for v, x in d.groupby("variant"):
    x = x.set_index("instance")
    b = base.loc[x.index]
    worse = [tuple(a) > tuple(c) for a, c in zip(x.key, b.key)]
    better = [tuple(a) < tuple(c) for a, c in zip(x.key, b.key)]
    dW = (x.wellbeing - b.wellbeing) / b.wellbeing.clip(lower=1000)
    same_w = x.wellbeing == b.wellbeing
    dP = ((x.preferences - b.preferences) / b.preferences.clip(lower=1000))[same_w]
    rows.append(dict(variant=v, worse=np.mean(worse), better=np.mean(better), dW_med=np.median(dW),
                     dP_med_when_W_equal=np.median(dP) if len(dP) else np.nan, valid=(x.violations == 0).mean()))
print(pd.DataFrame(rows).sort_values("worse", ascending=False).round(3).to_string(index=False))
