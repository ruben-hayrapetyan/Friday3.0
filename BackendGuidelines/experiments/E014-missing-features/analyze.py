"""E014 analysis: threshold from tuning users, discovery and false-rule rates on evaluation users."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
c = pd.concat([pd.read_csv(f) for f in sorted((HERE / "results").glob("checkpoints*.csv"))])
r = pd.concat([pd.read_csv(f) for f in sorted((HERE / "results").glob("regret*.csv"))])
tune = c[c.tuning]
easy_max = tune[tune.kind == "easy"].groupby("user").best_gain.max().sort_values()
n_easy = len(easy_max)
# smallest threshold that flags at most 1 tuning easy user at any checkpoint
thr = float(easy_max.iloc[-2]) if n_easy >= 2 else float(easy_max.max())
print(f"tuning easy users' max gains: {np.round(easy_max.values, 4)} -> threshold {thr:.4f}")
ev = c[~c.tuning]
for kind, x in ev.groupby("kind"):
    print(f"\n{kind} (evaluation users):")
    for wk, y in x.groupby("week"):
        flagged = y.best_gain > thr
        correct = flagged & y.best_correct
        print(f"  week {wk:2d}: proposed {flagged.mean():.2f}  correct {correct.mean():.2f}  "
              f"median rank of the true rule {y.rank_of_truth.median():.0f}")
print("\nregret at week 12 (all users), relative, median:")
print(r.groupby(["kind", "policy"]).regret_rel.median().round(3).to_string())
(HERE / "results" / "threshold.txt").write_text(f"{thr:.6f}\n")
