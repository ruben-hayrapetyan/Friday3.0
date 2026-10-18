"""E020: duration models, prediction quality only. Usage: uv run python experiments/E020-duration-models/run.py"""
from __future__ import annotations

import math
import sys
import tomllib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

from fr.product.durations import Obs, make
from fr.sim.durations import COURSES, KINDS, Student, term

HERE = Path(__file__).parent
CFG_NAME = sys.argv[1] if len(sys.argv) > 1 else "config.toml"
CFG = tomllib.loads((HERE / CFG_NAME).read_text())
TAG = "" if CFG_NAME == "config.toml" else "_" + CFG_NAME.split("_")[1].split(".")[0]


def crps_normal(y: float, m: float, s: float) -> float:
    z = (y - m) / s
    return s * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / math.sqrt(math.pi))


def run_student(kind: str, seed: int, models: list[str], weeks: int) -> list[dict]:
    st = Student.make(kind, seed)
    items = term(st, weeks)
    events = sorted([(it.release, 0, it) for it in items] + [(it.due, 1, it) for it in items], key=lambda e: (e[0], e[1], e[2].id))
    zoo = {m: make(m, KINDS, COURSES) for m in models}
    out = []
    for t, typ, it in events:
        week = (t / 1440 - 7) / 7
        if typ == 0:
            y = math.log(it.true_min)
            for name, mdl in zoo.items():
                m, s = mdl.predict(it.course, it.kind, it.estimate_min, week)
                out.append(dict(type=kind, seed=seed, model=name, item=it.id, kind=it.kind, week=int(week),
                                has_est=it.estimate_min is not None, abs_log_err=abs(m - y), crps=crps_normal(y, m, s),
                                cover50=y <= m, cover80=y <= m + 0.8416 * s, sigma=s, bias=m - y))
        else:
            rec = it.record()
            if rec is not None:
                for mdl in zoo.values():
                    mdl.observe(Obs(it.course, it.kind, it.estimate_min, rec, week))
    return out


def main() -> None:
    rows = []
    for kind in CFG["types"]:
        for seed in CFG["seeds"]:
            rows += run_student(kind, seed, CFG["models"], CFG["weeks"])
    df = pd.DataFrame(rows)
    (HERE / "results").mkdir(exist_ok=True)
    df.to_csv(HERE / "results" / f"predictions{TAG}.csv.gz", index=False)
    late = df[df.week >= 2]
    t = late.groupby(["type", "model"]).agg(mae=("abs_log_err", "median"), crps=("crps", "mean"),
                                           cov50=("cover50", "mean"), cov80=("cover80", "mean")).round(3)
    t.to_csv(HERE / "results" / f"by_type{TAG}.csv")
    overall = late.groupby("model").agg(mae=("abs_log_err", "median"), crps=("crps", "mean"), cov50=("cover50", "mean"),
                                        cov80=("cover80", "mean")).round(3).sort_values("crps")
    overall.to_csv(HERE / "results" / f"overall{TAG}.csv")
    print(overall.to_string())
    print(t.unstack("model")["crps"].round(3).to_string())
    # figures
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for name, d in df.groupby("model"):
        c = d.groupby("week").crps.mean()
        ax.plot(c.index, c.values, "o-", ms=3, label=name)
    ax.set_xlabel("week of term")
    ax.set_ylabel("CRPS (log minutes), lower is better")
    ax.legend(fontsize=7, ncol=2)
    ax.set_title("Duration prediction learning curves (E020)", fontsize=9)
    (HERE / "figures").mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / f"learning_curves{TAG}.png", dpi=130)
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    piv = t["crps"].unstack("model")
    piv.plot.bar(ax=ax, width=0.85)
    ax.set_ylabel("CRPS, weeks 2-9")
    ax.legend(fontsize=6, ncol=4)
    ax.set_title("Duration models by student type (E020)", fontsize=9)
    fig.tight_layout()
    fig.savefig(HERE / "figures" / f"by_type{TAG}.png", dpi=130)


if __name__ == "__main__":
    main()
