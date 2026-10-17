"""E002: baseline variants at a 10 s budget. Usage: uv run python run.py (from this folder)."""
from __future__ import annotations

import csv
import tomllib
from pathlib import Path

from fr.baseline.cpsat import ModelInfeasible, SolveTimeout, solve
from fr.core.evaluate import check, evaluate
from fr.core.generate import reference_instance
from fr.core.remap import remap_plan
from fr.engines.prepare import prepare

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
LOG = (HERE / "progress.txt").open("a")


def log(msg: str) -> None:
    print(msg, flush=True)
    LOG.write(msg + "\n")
    LOG.flush()


VARIANTS = {
    "A": dict(),
    "B": dict(fine_days=3),
    "C": dict(horizon_days=10),
    "D": dict(workers=1),
    "E": dict(hint="construct"),
    "F": dict(time_share=(0.2, 0.3, 0.5)),
}


def main() -> None:
    rows = []
    for seed in cfg["seeds"]:
        base_sc = reference_instance(cfg["n"], seed)
        base = base_sc.build()
        for vid, v in VARIANTS.items():
            sc = reference_instance(cfg["n"], seed)
            st = sc.settings
            st.time_limit_s = cfg["time_limit_s"]
            st.workers = v.get("workers", cfg["workers"])
            st.det_time = (cfg["time_limit_s"] * 3,) * 3  # wall clock decides
            for k in ("fine_days", "horizon_days", "time_share"):
                if k in v:
                    setattr(st, k, v[k])
            p = sc.build()
            hint = None
            if v.get("hint") == "construct":
                pr = prepare(sc.build())  # a separate copy: preparing may relax locks
                hint = pr.c.plan_from_owner(pr.owner)
            try:
                res = solve(p, hint=hint)
            except (SolveTimeout, ModelInfeasible) as exc:  # no plan within the doubled stage limits: a baseline failure
                row = dict(seed=seed, variant=vid, total_s=-1, late=-1, wellbeing=-1, preferences=-1, violations=-1,
                           late_h=-1, misses=-1, statuses=f"FAIL:{type(exc).__name__}")
                rows.append(row)
                log(str(row))
                continue
            plan = remap_plan(res.plan, p, base) if (p.grid.S != base.grid.S) else res.plan
            ev = evaluate(base, plan)
            viol = len(check(base, plan))
            row = dict(seed=seed, variant=vid, total_s=round(res.total_s, 2), late=ev.stage_values["deadlines"],
                       wellbeing=ev.stage_values["wellbeing"], preferences=ev.stage_values["preferences"],
                       violations=viol, late_h=round(ev.late_hours, 1), misses=len(ev.deadline_misses),
                       statuses="/".join(s.status for s in res.stages))
            rows.append(row)
            log(str(row))
    with (HERE / "results" / "runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
