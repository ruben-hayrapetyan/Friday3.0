"""E013: hidden units and mood vs taste. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

import numpy as np

from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.shard import mine, suffix
from fr.learn.hidden import HiddenLearner, WeekEvidence, _norm_diff
from fr.sim.user import SimUser
from fr.sim.world import Universe, live_week, true_energy

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(kinds=["moody"], users=1, weeks=3, plan_steps=50000, ref_steps=50000)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / f"progress{suffix()}.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def main() -> None:
    warmup()
    rows = []
    for kind in cfg["kinds"]:
        for uid in range(cfg["users"]):
            if not mine(cfg["kinds"].index(kind) * cfg["users"] + uid):
                continue
            user = SimUser.make(kind, 5000 + 100 * cfg["kinds"].index(kind) + uid)
            rng = np.random.default_rng(uid)
            learners = {m: HiddenLearner("dial" if m == "gated" else m) for m in cfg["modes"]}
            gain = 0.0  # cumulative predictive gain of the dial units over taste only (for "gated")
            moods: list[str] = []
            for wk in range(cfg["weeks"]):
                mood = user.step_mood()
                moods.append(mood)
                checkin = user.checkin()
                pace = mood if (mood != "normal" and rng.random() < cfg["pace_p"]) else None
                u = Universe(cornell_semester(600 + 17 * uid + wk + 300 * cfg["kinds"].index(kind)))
                x_star = u.plan(user.theta_now(), steps=cfg["ref_steps"], seed=wk)
                e_star = true_energy(u, user, x_star)
                for mode, L in learners.items():
                    h = L.predict_h(checkin, pace, true_mood=mood)
                    th = L.theta_eff(h)
                    if mode == "gated" and not (gain > 2.0 or pace is not None):
                        th = learners["none"].theta_eff(np.zeros(0))
                    x_f = u.plan(th, steps=cfg["plan_steps"], seed=wk)
                    week = live_week(u, user, x_f, th, wk, seed=wk * 7919 + uid)
                    # predictive log-likelihood of this week's rankings under the units chosen before the week
                    diffs = np.array([_norm_diff(r) for r in week.rankings]) if week.rankings else np.zeros((0, len(th)))
                    pred_ll = L.week_ll(L.theta, h, WeekEvidence(diffs, 0, 0, None, None)) if len(diffs) else 0.0
                    week.checkin = checkin
                    if mode == "gated" and len(diffs):  # the gate's own predictive test, before learning from the week
                        ev = WeekEvidence(diffs, 0, 0, None, None)
                        gain += L.week_ll(L.theta, h, ev) - learners["none"].week_ll(learners["none"].theta, np.zeros(0), ev)
                    L.add_week(week, pace=pace)
                    if mode == "oracle":
                        L.fit(true_moods=moods)
                    e_f = true_energy(u, user, x_f)
                    post = L.h[-1] if L.K else np.zeros(0)
                    rows.append(dict(kind=kind, user=uid, week=wk, mood=mood, pace=pace or "", checkin=checkin, mode=mode,
                                     regret=round(e_f - e_star, 2), regret_rel=round((e_f - e_star) / max(abs(e_star), 1), 4),
                                     pred_ll=round(pred_ll, 4), inferred=L.mood_of(post),
                                     h_norm=round(float(np.linalg.norm(post)), 3) if L.K else 0.0,
                                     h=" ".join(f"{v:.2f}" for v in post)))
                # retro-inference of all past weeks' moods with the final fit (state accuracy)
                log(f"{kind}-{uid} wk{wk} mood={mood} pace={pace} " + " ".join(
                    f"{r['mode']}:{r['regret_rel']:.3f}/{r['inferred'][0]}" for r in rows[-len(learners):]))
                with (HERE / "results" / f"runs{suffix()}.csv").open("w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
            for mode, L in learners.items():
                for w, h in enumerate(L.h):
                    rows_post.append(dict(kind=kind, user=uid, week=w, mode=mode, mood=moods[w], inferred=L.mood_of(h),
                                          h=" ".join(f"{v:.2f}" for v in h)))
            with (HERE / "results" / f"final_inference{suffix()}.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows_post[0]))
                w.writeheader()
                w.writerows(rows_post)
    log("done")


rows_post: list[dict] = []

if __name__ == "__main__":
    main()
