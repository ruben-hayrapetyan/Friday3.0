"""E001 analysis: summary table (stdout), figures into figures/. Usage: uv run python analyze.py"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
runs = pd.read_csv(HERE / "results" / "runs.csv")
traces = pd.read_csv(HERE / "results" / "traces.csv")
STAGES = ["deadlines", "wellbeing", "preferences"]


def boot_ci(x, stat=np.median, n=2000, seed=0):
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    s = [stat(rng.choice(x, size=len(x))) for _ in range(n)]
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


def summarize() -> pd.DataFrame:
    rows = []
    for (n, mode), g in runs[runs["mode"].isin(["cold", "warm"])].groupby(["n", "mode"]):
        row = dict(n=n, mode=mode, runs=len(g), total_med=g.total_s.median(), total_p90=g.total_s.quantile(0.9),
                   total_ci=boot_ci(g.total_s))
        for s in STAGES:
            row[f"{s}_wall_med"] = g[f"{s}_wall_s"].median()
            row[f"{s}_optimal"] = float((g[f"{s}_status"] == "OPTIMAL").mean())
            row[f"{s}_gap_med"] = g[f"{s}_gap"].median()
        row["guarantee_rate"] = float(g.guarantee_ok.mean())
        row["edf_feasible"] = float(g.edf_feasible.mean())
        row["overflow_h_med"] = g.overflow_h.median()
        rows.append(row)
    return pd.DataFrame(rows)


def figures() -> None:
    cw = runs[runs["mode"].isin(["cold", "warm"])]
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    for a, s in zip(ax, STAGES):
        data, labels = [], []
        for n in sorted(cw.n.unique()):
            for mode in ("cold", "warm"):
                data.append(cw[(cw.n == n) & (cw["mode"] == mode)][f"{s}_wall_s"].values)
                labels.append(f"{n}\n{mode}")
        a.boxplot(data, tick_labels=labels)
        a.set_title(f"{s}: wall seconds")
        a.set_ylabel("s")
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "stage_wall_time.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.6))
    for mode, c in (("cold", "C0"), ("warm", "C1")):
        g = cw[cw["mode"] == mode].groupby("n").total_s
        ax.errorbar(g.median().index, g.median().values, yerr=[g.median() - g.min(), g.max() - g.median()],
                    marker="o", color=c, label=mode, capsize=3)
    ax.axhline(10, ls="--", c="gray", lw=0.8)
    ax.text(cw.n.min(), 10.3, "cold p90 target 10 s", fontsize=8, color="gray")
    ax.axhline(3, ls=":", c="gray", lw=0.8)
    ax.text(cw.n.min(), 3.2, "warm p90 target 3 s", fontsize=8, color="gray")
    ax.set_xlabel("flexible items")
    ax.set_ylabel("total solve seconds (median, min-max)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "total_time.png", dpi=130)
    plt.close(fig)

    # quality vs time for the preferences stage on one instance per size (objective relative to final)
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    tp = traces[(traces.stage == "preferences") & (traces["mode"] == "cold")]
    for n, c in zip(sorted(cw.n.unique()), ("C0", "C1", "C2")):
        for inst in [i for i in tp.instance.unique() if i.startswith(f"ref-n{n}-")][:5]:
            t = tp[tp.instance == inst].sort_values("t")
            final = t.obj.iloc[-1]
            ax.step(t.t - t.t.iloc[0], (t.obj - final) / max(1, final), color=c, alpha=0.6, lw=1,
                    label=f"n={n}" if inst.endswith("s0") else None)
    ax.set_xlabel("seconds since first preferences solution")
    ax.set_ylabel("(objective - final) / final")
    ax.set_yscale("symlog", linthresh=0.01)
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / "figures" / "preferences_quality_vs_time.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    pd.set_option("display.width", 200, "display.max_columns", 30)
    s = summarize()
    print(s.round(3).to_string())
    rep = runs[runs["mode"] == "cold-repeat"]
    if len(rep):
        v = rep.groupby("seed").total_s.agg(["min", "median", "max"])
        print("\ntiming repeats (n=60, cold): total_s per seed\n", v.round(2).to_string())
    print("\nguarantee violations:", int((~runs.guarantee_ok).sum()), "of", len(runs))
    cold = runs[runs["mode"] == "cold"]
    print("deterministic check (repeat vs first cold, preferences value):")
    for seed in rep.seed.unique() if len(rep) else []:
        base = cold[(cold.n == cold.n.max()) & (cold.seed == seed)].preferences.iloc[0]
        print(seed, base, rep[rep.seed == seed].preferences.tolist())
    figures()
    ex = HERE / "results" / "executor_allocator.json"
    if ex.exists():
        print(ex.read_text())
