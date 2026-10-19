"""E015 analysis."""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
d = pd.read_csv(HERE / "results" / "policy_sim.csv")
c = pd.read_csv(HERE / "results" / "week_costs.csv")
print(c.groupby("kind").cost_points.describe().round(2).to_string())
t = d.groupby(["policy", "type"]).agg(regret=("regret", "mean"), questions=("questions", "mean"),
                                       softened=("softened", "mean"), false_soften=("false_soften", "mean")).round(2)
print(t.unstack("type").to_string())
print("\nall users:", d.groupby("policy").agg(regret=("regret", "mean"), questions=("questions", "mean")).round(2).to_string())
