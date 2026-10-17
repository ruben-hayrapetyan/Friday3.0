"""E017: v3 vs v2 over simulated semesters. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

import numpy as np

from fr.core.evaluate import check, evaluate
from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.sim.user import MISSING_RULE, SimUser
from fr.sim.world import Universe, live_week, true_energy
from fr.supervisor.grammar import candidates, matches_truth
from fr.system import V2System, V3System

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(kinds=["moody"], users=1, weeks=2, v2_budget_s=5.0, v3_budget_s=0.5)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")
CANDS = candidates()
_thr = Path(__file__).parent.parent / "E014-missing-features" / "results" / "threshold.txt"
if _thr.exists():  # the threshold tuned on E014's tuning users
    cfg["threshold"] = float(_thr.read_text().strip())


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def main() -> None:
    warmup()
    rows = []
    for kind in cfg["kinds"]:
        for uid in range(cfg["users"]):
            user = SimUser.make(kind, 20000 + 100 * cfg["kinds"].index(kind) + uid)
            rng = np.random.default_rng(20000 + uid)
            names = [c["name"] for c in CANDS]
            confirm = (lambda r: matches_truth(r)) if user.kind.missing_weight else (lambda r: False)
            systems = [V3System(budget_s=cfg["v3_budget_s"], threshold=cfg["threshold"], candidates=names, confirm=confirm),
                       V3System(budget_s=cfg["v3_budget_s"], threshold=cfg["threshold"], candidates=list(names),
                                stages="tiered", name="v3_lex", confirm=confirm),
                       V2System(budget_s=cfg["v2_budget_s"])]
            for wk in range(cfg["weeks"]):
                mood = user.step_mood()
                checkin = user.checkin()
                pace = mood if (mood != "normal" and rng.random() < cfg["pace_p"]) else None
                u = Universe(cornell_semester(10000 + 100 * uid + wk + 1000 * cfg["kinds"].index(kind)),
                             [MISSING_RULE] + CANDS)
                extra_true = {"missing:fri_sat_evening": user.kind.missing_weight} if user.kind.missing_weight else {}
                x_star = u.plan(user.theta_now(), extra_true, steps=1_000_000, seed=wk)
                e_star = true_energy(u, user, x_star)
                for sysm in systems:
                    sysm.start_week(checkin, pace)
                    th = sysm.theta()
                    owner, dt, status = sysm.plan(u, seed=wk)
                    plan = u.c.plan_from_owner(owner)
                    ev = evaluate(u.p, plan)
                    viol = len(check(u.p, plan))
                    week = live_week(u, user, owner, th, wk, seed=wk * 7919 + uid, select=sysm.select())
                    sysm.end_week(week, pace, wk)
                    e = true_energy(u, user, owner)
                    t = sysm.L.theta
                    cos = float(t @ user.theta / np.linalg.norm(t) / np.linalg.norm(user.theta))
                    rows.append(dict(kind=kind, user=uid, week=wk, mood=mood, pace=pace or "", system=sysm.name,
                                     plan_s=round(dt, 2), status=status, violations=viol, late=ev.stage_values["deadlines"],
                                     misses=len(ev.deadline_misses), regret=round(e - e_star, 2),
                                     regret_rel=round((e - e_star) / max(abs(e_star), 1), 4), cos=round(cos, 4),
                                     rules=";".join(getattr(sysm, "extra_w", {}).keys()),
                                     units_on=bool(getattr(sysm, "units_on", False)),
                                     proposals_refused=sum("said no" in m for m in sysm.log),
                                     rules_correct=sum(matches_truth(r) for r in getattr(sysm, "extra_w", {}))))
                log(f"{kind}-{uid} wk{wk} mood={mood} " + " ".join(
                    f"{r['system']}:{r['regret_rel']:.3f}/{r['plan_s']}s/m{r['misses']}/v{r['violations']}" for r in rows[-len(systems):]))
                with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
