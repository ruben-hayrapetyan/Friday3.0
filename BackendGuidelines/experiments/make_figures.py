"""Figures for experiments whose analysis printed tables only. Usage: uv run python experiments/make_figures.py"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fr.bench import best_known

EXP = Path(__file__).parent


def save(fig, exp: str, name: str) -> None:
    out = EXP / exp / "figures"
    out.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(out / name, dpi=130)
    plt.close(fig)


def bars(ax, labels, values, ylabel, title, fmt="{:.0%}"):
    ax.bar(range(len(values)), values, color="#4a8")
    for i, v in enumerate(values):
        ax.text(i, v, fmt.format(v), ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(values)), labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9)


def e002():
    d = pd.read_csv(EXP / "E002-baseline-tuning/results/runs.csv")
    d["fail"] = d.statuses.str.startswith("FAIL")
    g = d.groupby("variant").fail.mean()
    fig, ax = plt.subplots(figsize=(5, 3))
    bars(ax, [f"{v}" for v in g.index], g.values, "share of runs with no plan", "v2 at 10 s: time-outs per variant (E002)")
    save(fig, "E002-baseline-tuning", "timeouts.png")


def e004b():
    d = pd.read_csv(EXP / "E004b-penalty-scale/results/runs.csv")
    d["best_late"] = [best_known(i)[0] for i in d.instance]
    d["safe"] = (d.violations == 0) & ((d.late == 0) | (d.best_late > 0))
    t = d.groupby(["variant", "start"]).safe.mean().unstack()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    x = np.arange(len(t))
    for k, (col, c) in enumerate(zip(t.columns, ("C0", "C1"))):
        ax.bar(x + 0.4 * k, t[col].values, width=0.4, label=f"start: {col}", color=c)
    ax.set_xticks(x + 0.2, t.index, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("deadline-safe share")
    ax.legend(fontsize=8)
    ax.set_title("Walls vs penalty scales (E004b)", fontsize=9)
    save(fig, "E004b-penalty-scale", "deadline_safe.png")


def e005():
    d = pd.read_csv(EXP / "E005-deadline-guarantee/results/runs.csv")
    o = d[(d.truth_status == "OPTIMAL") & (d.truth_late > 0)]
    fig, ax = plt.subplots(figsize=(5, 3))
    cols = ["construct_late", "repair_late", "repair_cpsat_late", "walls_late"]
    ratios = [float(np.median(o[c] / o.truth_late)) for c in cols]
    bars(ax, ["construct", "repair", "repair+CP-SAT", "walls"], ratios, "lateness / proven optimum (median)",
         "Proven overload instances (E005)", "{:.2f}")
    save(fig, "E005-deadline-guarantee", "overload_ratio.png")
    src = EXP.parent / "report/figures/deadline_guarantee.png"
    if src.exists():
        (EXP / "E005-deadline-guarantee/figures/deadline_guarantee.png").write_bytes(src.read_bytes())


def stages(exp):
    src = EXP.parent / "report/figures/stages.png"
    (EXP / exp / "figures").mkdir(exist_ok=True)
    (EXP / exp / "figures/stages.png").write_bytes(src.read_bytes())


def e008():
    d = pd.read_csv(EXP / "E008-move-ablation/results/runs.csv")
    d["key"] = list(zip(d.late, d.wellbeing, d.preferences))
    base = d[d.variant == "all"].set_index("instance").key
    w = {v: np.mean([tuple(k) > tuple(base[i]) for i, k in x.set_index("instance").key.items()])
         for v, x in d[d.variant != "all"].groupby("variant")}
    w = dict(sorted(w.items(), key=lambda kv: -kv[1]))
    fig, ax = plt.subplots(figsize=(6, 3.2))
    bars(ax, list(w), list(w.values()), "share of instances worse than all moves", "Move ablation (E008)")
    save(fig, "E008-move-ablation", "ablation.png")


def warm(exp, label_col="method"):
    d = pd.read_csv(EXP / exp / "results/runs.csv")
    d["lab"] = d[label_col] + "@" + d.budget_s.astype(str)
    g = d.groupby("lab").agg(t=("seconds", "median"), churn=("churn_h", "median"))
    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    ax.scatter(g.t, g.churn)
    for lab, r in g.iterrows():
        ax.annotate(lab, (r.t, r.churn), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xscale("log")
    ax.set_xlabel("seconds per replan (median)")
    ax.set_ylabel("hours of work moved (median)")
    ax.set_title(f"Warm replans: time vs churn ({exp.split('-')[0]})", fontsize=9)
    save(fig, exp, "time_vs_churn.png")


def e012():
    d = pd.read_csv(EXP / "E012-rbm-from-data/results/pairs.csv")
    fig, ax = plt.subplots(figsize=(4.4, 3))
    x = np.arange(len(d))
    ax.bar(x - 0.2, d.acc_rbm, width=0.4, label="RBM free energy")
    ax.bar(x + 0.2, d.acc_rules, width=0.4, label="rules, theta = 1")
    ax.axhline(0.5, ls=":", c="gray")
    ax.set_xticks(x, [f"user {u}" for u in d.user])
    ax.set_ylabel("held-out pairwise accuracy")
    ax.legend(fontsize=8)
    ax.set_title("RBM from lived weeks vs rule energy (E012)", fontsize=9)
    save(fig, "E012-rbm-from-data", "ranking_accuracy.png")


def hidden(exp):
    d = pd.concat([pd.read_csv(f) for f in sorted((EXP / exp / "results").glob("runs*.csv"))])
    t = d.groupby(["kind", "mode"]).regret_rel.mean().unstack()
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    w = 0.8 / len(t.columns)
    for j, m in enumerate(t.columns):
        ax.bar(np.arange(len(t)) + j * w, t[m].values, width=w, label=m)
    ax.set_xticks(np.arange(len(t)) + 0.4 - w / 2, t.index)
    ax.set_ylabel("mean relative regret")
    ax.legend(fontsize=8)
    ax.set_title(f"Hidden units by user type ({exp.split('-')[0]})", fontsize=9)
    save(fig, exp, "regret_by_mode.png")


def e014():
    c = pd.concat([pd.read_csv(f) for f in sorted((EXP / "E014-missing-features/results").glob("checkpoints*.csv"))])
    thr = float((EXP / "E014-missing-features/results/threshold.txt").read_text())
    ev = c[~c.tuning]
    fig, ax = plt.subplots(figsize=(5, 3))
    for kind, x in ev.groupby("kind"):
        r = x.groupby("week").apply(lambda y: ((y.best_gain > thr) & (y.best_correct if kind == "missing" else True)).mean(),
                                    include_groups=False)
        ax.plot(r.index, r.values, "o-", label="right rule proposed (missing-feature users)" if kind == "missing"
                else "a rule proposed (users without one: false)")
    ax.set_xlabel("week")
    ax.set_ylabel("share of evaluation users")
    ax.legend(fontsize=7)
    ax.set_title("Missing-feature detection (E014)", fontsize=9)
    save(fig, "E014-missing-features", "proposals.png")


def e015():
    d = pd.read_csv(EXP / "E015-soften-walls/results/policy_sim.csv")
    g = d.groupby("policy").regret.mean().sort_values()
    fig, ax = plt.subplots(figsize=(4.8, 3))
    bars(ax, list(g.index), g.values, "mean regret over 12 weeks (points)", "Softening policies (E015)", "{:.0f}")
    save(fig, "E015-soften-walls", "policies.png")


def e018():
    runs = []
    for exp in ("E018-weakness-hunt", "E018b-weakness-fix", "E018c-size-rule", "E018d-fallback-time"):
        f = EXP / exp / "results/runs.csv"
        if f.exists():
            runs.append(pd.read_csv(f))
    d = pd.concat(runs)
    d["at_best"] = (d.violations == 0) & (d.late == [best_known(i)[0] for i in d.instance])
    t = d.pivot_table(index="family", columns="engine", values="at_best")
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    w = 0.8 / len(t.columns)
    for j, e in enumerate(t.columns):
        ax.bar(np.arange(len(t)) + j * w, t[e].values, width=w, label=e)
    ax.set_xticks(np.arange(len(t)) + 0.4 - w / 2, t.index, rotation=20, fontsize=8)
    ax.set_ylabel("share at the best known lateness")
    ax.legend(fontsize=7, ncol=3)
    ax.set_title("Weakness hunt (E018-E018d)", fontsize=9)
    fig.tight_layout()
    for exp in ("E018-weakness-hunt", "E018b-weakness-fix", "E018c-size-rule", "E018d-fallback-time"):
        (EXP / exp / "figures").mkdir(exist_ok=True)
        fig.savefig(EXP / exp / "figures/at_best_lateness.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    e002()
    e004b()
    e005()
    stages("E006-stages")
    stages("E006b-stage-polish")
    e008()
    warm("E009-warm-determinism")
    warm("E009b-warm-churn")
    e012()
    for exp in ("E013-hidden-units", "E013b-gated-units", "E013c-gate-vs-temperature"):
        hidden(exp)
    e014()
    e015()
    e018()
    print("ok")
