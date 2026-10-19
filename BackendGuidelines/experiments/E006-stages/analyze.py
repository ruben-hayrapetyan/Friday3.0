"""E006 analysis: disagreement of weighted variants with the tiered (lexicographic) reference."""
from pathlib import Path

import numpy as np
import pandas as pd

from fr.bench import best_known

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
ref = d[d.variant == "tiered"].set_index("instance")
rows = []
for v, x in d.groupby("variant"):
    x = x.set_index("instance")
    r = ref.loc[x.index]
    worse_w = x.wellbeing > r.wellbeing
    better_p = x.preferences < r.preferences
    dw = (x.wellbeing - r.wellbeing) / r.wellbeing.clip(lower=1000)
    dp = (x.preferences - r.preferences) / r.preferences.clip(lower=1000)
    best = np.array([best_known(i) for i in x.index])
    lex_worse = [(tuple(a) > tuple(b)) for a, b in zip(x[["late", "wellbeing", "preferences"]].values, best)]
    rows.append(dict(variant=v, n=len(x), wellbeing_worse_than_tiered=worse_w.mean(), prefs_better_than_tiered=better_p.mean(),
                     dW_med=np.median(dw), dW_p90=np.percentile(dw, 90), dP_med=np.median(dp),
                     valid=(x.violations == 0).mean()))
print(pd.DataFrame(rows).round(3).to_string(index=False))
