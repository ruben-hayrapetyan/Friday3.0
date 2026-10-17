"""E015: softening walls. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import sys
import tomllib
from pathlib import Path

import numpy as np

from fr.core.generate import cornell_semester
from fr.engines.api import warmup
from fr.sim.user import LEARNABLE, SimUser
from fr.sim.world import Universe, true_energy

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(instances=[0], users_per_type=20)
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")
WALL = dict(type="time_preference", name="never:sun_morning", weight=1.0,
            params=dict(days=["sun"], start="08:00", end="13:00", price="forbid"))
SUN_PRICE = dict(type="time_preference", name="true:sun_morning", weight=1.0,
                 params=dict(days=["sun"], start="08:00", end="13:00", price=6.0))
POLICIES = ("never", "auto1", "ask1", "ask3", "auto3")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


A_DISLIKE = dict(type="time_preference", name="trueA:weekend_afternoons", weight=1.0,
                 params=dict(days=["sat", "sun"], start="13:00", end="23:59", price=3.0))


def best_plan(u: Universe, theta, extra_w, energy) -> np.ndarray:
    """Best of three seeds under `energy` (sampler noise would otherwise swamp a five-hour window)."""
    xs = [u.plan(theta, extra_w, steps=1_000_000, seed=s) for s in range(3)]
    return min(xs, key=energy)


def week_costs() -> dict:
    """Per-week regret of the wrong wall state, measured on real plans."""
    out = {"A": [], "BC": []}
    base = SimUser.make("easy", 4242)
    thA = base.theta.copy()
    thA[LEARNABLE.index("weekday_evenings")] *= 3
    for inst in cfg["instances"]:
        uA = Universe(cornell_semester(4000 + inst), [SUN_PRICE, A_DISLIKE])
        sc_wall = cornell_semester(4000 + inst)
        sc_wall.extra_rules = [WALL]
        uW = Universe(sc_wall, [SUN_PRICE, A_DISLIKE])
        # A knows their own dislike; Friday is assumed to have learned it (A's cost is only the wall)
        eA = lambda u, x: float(thA @ u.phi(x) + u.phi_extra(x, "trueA:weekend_afternoons"))  # noqa: E731
        x_wall = best_plan(uW, thA, {"trueA:weekend_afternoons": 1.0}, lambda x: eA(uW, x))
        x_free = best_plan(uA, thA, {"trueA:weekend_afternoons": 1.0}, lambda x: eA(uA, x))
        out["A"].append(eA(uW, x_wall) - eA(uA, x_free))
        # B/C: true energy has the Sunday price, which Friday does not know once the wall is gone
        eB = lambda u, x: float(base.theta @ u.phi(x) + u.phi_extra(x, "true:sun_morning"))  # noqa: E731
        x_free_b = best_plan(uA, base.theta, {}, lambda x: float(base.theta @ uA.phi(x)))
        x_wall_b = best_plan(uW, base.theta, {}, lambda x: float(base.theta @ uW.phi(x)))
        out["BC"].append(eB(uA, x_free_b) - eB(uW, x_wall_b))
        log(f"instance {inst}: A wall cost {out['A'][-1]:.1f}, B/C softening cost {out['BC'][-1]:.1f}")
    return {k: float(np.mean(v)) for k, v in out.items()} | {f"{k}_all": v for k, v in out.items()}


def simulate(costs: dict) -> list[dict]:
    rng = np.random.default_rng(0)
    rows = []
    for typ in ("A", "B", "C"):
        for uid in range(cfg["users_per_type"]):
            events = np.zeros(cfg["weeks"], dtype=bool)
            if typ == "A":
                events = rng.random(cfg["weeks"]) < cfg["p_event_A"]
            elif typ == "B":
                events[cfg["crunch_week_B"]] = True
            for pol in POLICIES:
                soft, asked, regret, soft_week = False, 0, 0.0, None
                hist: list[int] = []
                for wk in range(cfg["weeks"]):
                    # the plan for this week uses the current wall state
                    if typ == "A" and not soft:
                        regret += costs["A"]
                    if typ != "A" and soft:
                        regret += costs["BC"]
                    if events[wk]:
                        hist.append(wk)
                    recent = [w for w in hist if w > wk - 6]
                    if soft or not events[wk]:
                        continue
                    if pol == "auto1":
                        soft = True
                    elif pol == "ask1":
                        asked += 1
                        soft = typ == "A"
                    elif pol in ("ask3", "auto3") and len(set(recent)) >= 3:
                        if pol == "ask3":
                            asked += 1
                            soft = typ == "A"
                        else:
                            soft = True
                    if soft and soft_week is None:
                        soft_week = wk
                rows.append(dict(type=typ, user=uid, policy=pol, regret=round(regret, 2), questions=asked,
                                 softened=soft, false_soften=soft and typ != "A",
                                 softened_week=-1 if soft_week is None else soft_week, events=int(events.sum())))
    return rows


def main() -> None:
    warmup()
    costs = week_costs()
    rows = simulate(costs)
    with (HERE / "results" / "policy_sim.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (HERE / "results" / "week_costs.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "instance", "cost_points"])
        for k in ("A", "BC"):
            for i, v in enumerate(costs[f"{k}_all"]):
                w.writerow([k, cfg["instances"][i], round(v, 2)])
    log(f"costs: A={costs['A']:.1f} BC={costs['BC']:.1f}")
    log("done")


if __name__ == "__main__":
    main()
