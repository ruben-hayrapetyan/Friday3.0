"""Build every figure the report uses from the experiments' results. Usage: uv run python report/make_figures.py"""
from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments"
OUT = ROOT / "report" / "figures"
OUT.mkdir(parents=True, exist_ok=True)


def copy(src: str, dst: str) -> None:
    s = EXP / src
    if s.exists():
        shutil.copy(s, OUT / dst)


def deadline_safety() -> None:
    d = pd.read_csv(EXP / "E005-deadline-guarantee" / "results" / "runs.csv")
    cert = (d.construct_late == 0) | (d.repair_late == 0) | (d.repair_cpsat_late == 0) | \
           ((d.walls_late == 0) & (d.walls_violations == 0))
    z = d[((d.truth_status == "OPTIMAL") & (d.truth_late == 0)) | cert]
    labels = ["EDF-order\nconstruction", "+ sampler\nrepair", "+ CP-SAT\nfallback", "walls\n(3 s)", "CP-SAT stage 1\nalone (15 s)"]
    vals = [np.mean(z.construct_late == 0), np.mean(z.repair_late == 0), np.mean(z.repair_cpsat_late == 0),
            np.mean(z.walls_late == 0), np.mean(z.truth_late == 0)]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.bar(range(5), vals, color=["#8aa", "#4a8", "#4a8", "#4a8", "#c66"])
    for i, v in enumerate(vals):
        ax.text(i, v + 0.02, f"{v:.0%}", ha="center", fontsize=9)
    ax.set_xticks(range(5), labels, fontsize=8)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("zero late, where zero is possible")
    ax.set_title(f"Deadline guarantee on {len(z)} instances (E005)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "deadline_guarantee.png", dpi=140)
    plt.close(fig)


def stages() -> None:
    a = pd.read_csv(EXP / "E006-stages" / "results" / "runs.csv")
    b = pd.read_csv(EXP / "E006b-stage-polish" / "results" / "runs.csv")
    b = b[b.variant == "lexpolish"]
    d = pd.concat([a, b])
    m = d.groupby("variant")[["wellbeing", "preferences"]].median()
    fig, ax = plt.subplots(figsize=(5.6, 4))
    for v, r in m.iterrows():
        c = "C3" if v == "lexpolish" else ("C0" if v.startswith("tiered") else "C7")
        ax.scatter(r.wellbeing, r.preferences, c=c, s=40)
        off = {"weighted_100": (4, -10), "weighted_30": (4, 4)}.get(v, (4, 3))
        ax.annotate(v, (r.wellbeing, r.preferences), fontsize=8, xytext=off, textcoords="offset points")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_yscale("log")
    ax.set_xlabel("median wellbeing (lower is better)")
    ax.set_ylabel("median preferences (lower is better)")
    ax.set_title("Stage handling (E006, E006b), 20 instances x 10 s", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "stages.png", dpi=140)
    plt.close(fig)


def hidden() -> None:
    rows = []
    for exp, modes in (("E013-hidden-units", ("none", "dial", "free")), ("E013c-gate-vs-temperature", ("gated2",))):
        for f in (EXP / exp / "results").glob("runs*.csv"):
            x = pd.read_csv(f)
            rows.append(x[x["mode"].isin(modes)])
    d = pd.concat(rows)
    t = d.groupby(["kind", "mode"]).regret_rel.mean().unstack()
    order = [m for m in ("none", "dial", "free", "gated2") if m in t.columns]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    w = 0.8 / len(order)
    for j, m in enumerate(order):
        ax.bar(np.arange(len(t)) + j * w, t[m].values, width=w, label=m)
    ax.set_xticks(np.arange(len(t)) + 0.4 - w / 2, t.index)
    ax.set_ylabel("mean relative regret")
    ax.set_title("Hidden units by user type (E013, E013c)", fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "hidden_units.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    copy("E003-strict-qubo/figures/feasibility_and_gap_vs_penalty.png", "qubo_feasibility_vs_penalty.png")
    copy("E004-representations/figures/engines.png", "representations.png")
    copy("E007-samplers/figures/sampler_ranks.png", "samplers.png")
    copy("E011-learning/figures/learning_curves.png", "learning_curves_E011.png")
    copy("E011b-learning-round2/figures/learning_curves.png", "learning_curves_E011b.png")
    copy("E016-active-queries/figures/active_queries.png", "active_queries.png")
    copy("E010-diversity-calibration/figures/reliability_easy.png", "calibration.png")
    copy("E017-semesters/figures/semester_regret.png", "semester_regret.png")
    copy("E001-v2-baseline/figures/total_time.png", "baseline_time.png")
    deadline_safety()
    stages()
    hidden()
    print(sorted(p.name for p in OUT.iterdir()))
