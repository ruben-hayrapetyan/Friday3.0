"""E009 analysis: warm replans."""
from pathlib import Path

import numpy as np
import pandas as pd

from fr.bench import best_known, lex_gaps

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "runs.csv")
best = {i: best_known(i) for i in d.instance.unique()}
g = d.apply(lambda r: pd.Series(lex_gaps((r.late, r.wellbeing, r.preferences), best[r.instance])), axis=1)
d = pd.concat([d, g], axis=1)
d["label"] = d.method + "@" + d.budget_s.astype(str)
d["zero_late"] = (d.late == 0) & (d.violations == 0)
d["lexkey"] = list(zip(d.late, d.wellbeing, d.preferences))
d["rank"] = d.groupby("instance").lexkey.rank(method="average")
rows = []
for lab, x in d.groupby("label"):
    rows.append(dict(method=lab, n=len(x), zero_late=x.zero_late.mean(), mean_rank=x["rank"].mean(),
                     W_gap_med=np.nanmedian(x.wellbeing_gap), P_gap_med=np.nanmedian(x.preferences_gap),
                     churn_h_med=x.churn_h.median(), churn_h_p90=x.churn_h.quantile(0.9),
                     sec_med=x.seconds.median(), sec_p90=x.seconds.quantile(0.9),
                     identical_rerun=x.identical_rerun.mean() if "identical_rerun" in x and x.identical_rerun.notna().any() else np.nan))
pd.set_option("display.width", 220)
print(pd.DataFrame(rows).sort_values("mean_rank").round(3).to_string(index=False))
