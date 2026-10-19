"""E012 analysis."""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
for name in ("rbm_fit", "pairs", "samples"):
    print(f"\n{name}:\n", pd.read_csv(HERE / "results" / f"{name}.csv").round(3).to_string(index=False))
r = pd.read_csv(HERE / "results" / "rerank.csv")
print("\nre-ranking regret (points; picking 1 of 16 samples), median:")
print(r[["regret_rbm", "regret_rules", "regret_random"]].median().round(2).to_string())
