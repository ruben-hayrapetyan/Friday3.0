"""E010 analysis."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
a = pd.read_csv(HERE / "results" / "a_tiny_exact.csv")
print("A: tiny exact (TV distance to the Boltzmann distribution, share of valid plans visited)")
print(a.groupby("T_over_median")[["tv", "visited", "exact_mass_unvisited", "valid_plans"]].median().round(3).to_string())
b = pd.read_csv(HERE / "results" / "b_diversity.csv")
print("\nB: diversity at T > 0 (median over instances)")
print(b.groupby("T_over_median").median(numeric_only=True).drop(columns="seed").round(4).to_string())
c = pd.read_csv(HERE / "results" / "c_user_calibration.csv")
print("\nC: calibration against the user's lived week")
fig, ax = plt.subplots(figsize=(4.6, 4.2))
for (kind, tf), x in c.groupby(["kind", "tf_over_tau"]):
    brier = float(((x.pred - x.obs) ** 2).mean())
    base = float(((x.obs.mean() - x.obs) ** 2).mean())
    bins = np.clip((x.pred * 10).astype(int), 0, 9)
    rel = x.groupby(bins).agg(p=("pred", "mean"), o=("obs", "mean"), n=("obs", "size"))
    ece = float((rel.n * (rel.p - rel.o).abs()).sum() / rel.n.sum())
    print(f"  {kind:6s} T_f/tau={tf:<4} brier={brier:.4f} (climatology {base:.4f})  ECE={ece:.4f}  n={len(x)}")
    if kind == "easy":
        ax.plot(rel.p, rel.o, "o-", label=f"T_f = {tf:g} x tau")
ax.plot([0, 1], [0, 1], "k:", lw=0.8)
ax.set_xlabel("predicted p(item works on day d)")
ax.set_ylabel("observed frequency in lived weeks")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(HERE / "figures" / "reliability_easy.png", dpi=130)
