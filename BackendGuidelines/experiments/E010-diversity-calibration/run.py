"""E010: diversity and calibration. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

import numpy as np

from fr.core.brute import valid_plans
from fr.core.evaluate import evaluate
from fr.core.generate import cornell_semester, reference_instance, tiny
from fr.engines.api import warmup
from fr.engines.prepare import prepare
from fr.samplers.anneal import SAConfig, calibrate, protected
from fr.samplers.chains import CONSTANT, Replica, Spec, run
from fr.samplers.runner import solve_sampler
from fr.sim.user import LEARNABLE, SimUser
from fr.sim.world import Universe, live_week, move_scale

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
if "--smoke" in sys.argv:
    cfg.update(tiny_seeds=[0], tiny_T=[3.0], ref_seeds=[0], ref_T=[0.03], users_per_kind=1, weeks=2, user_kinds=["easy"])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")
W = np.array([1e6, 1.0, 1.0])


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def write(name: str, rows: list[dict]) -> None:
    if rows:
        with (HERE / "results" / f"{name}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
            w.writeheader()
            w.writerows(rows)


def part_a() -> None:
    rows = []
    for seed in cfg["tiny_seeds"]:
        p = tiny(seed, n_slots=8, n_items=3).build()
        pr = prepare(p)
        c = pr.c
        plans = list(valid_plans(p))
        keyf = lambda pl: tuple(tuple(pl[k]) for k in c.keys)  # noqa: E731
        E = np.array([float(W @ np.array(evaluate(p, pl).lex())) for pl in plans])
        index = {keyf(pl): j for j, pl in enumerate(plans)}
        prot = np.zeros(c.m.I, dtype=bool)
        med, _ = calibrate(c, pr.owner, prot, SAConfig(wts=W, t0_scale=1.0), n=800)
        for tf in cfg["tiny_T"]:
            T = tf * max(med, 1.0)
            exact = np.exp(-(E - E.min()) / T)
            exact /= exact.sum()
            counts = np.zeros(len(plans))
            for ch in range(16):
                rep = Replica.make(c, pr.owner)
                spec = Spec(W, wall=True)
                run(c, rep, prot, spec, 2000, T, T, 1000 * seed + ch, CONSTANT)
                for k in range(360):
                    run(c, rep, prot, spec, 50, T, T, 10_000 * seed + 100 * ch + k, CONSTANT)
                    counts[index[keyf(c.plan_from_owner(rep.st.owner))]] += 1
            emp = counts / counts.sum()
            tv = 0.5 * np.abs(emp - exact).sum()
            reach = float((counts > 0).mean())
            mass_unreached = float(exact[counts == 0].sum())
            rows.append(dict(seed=seed, T_over_median=tf, valid_plans=len(plans), tv=round(tv, 4), visited=round(reach, 3),
                             exact_mass_unvisited=round(mass_unreached, 4), samples=int(counts.sum())))
            log(f"A tiny-{seed} T={tf} plans={len(plans)} tv={tv:.3f} visited={reach:.2f} unvisited mass={mass_unreached:.3f}")
    write("a_tiny_exact", rows)


def day_pattern(c, owner, i):
    g = c.problem.grid
    return tuple(sorted({int(g.day[s]) for s in range(c.m.S) if owner[s] == i}))


def part_b() -> None:
    rows = []
    for seed in cfg["ref_seeds"]:
        p = reference_instance(40, seed).build()
        pr = prepare(p)
        c = pr.c
        start, _ = solve_sampler(pr, 8.0, "sa_geo", seed)
        prot = protected(c, start)
        med, _ = calibrate(c, start, prot, SAConfig(wts=W, t0_scale=1.0), n=1500)
        e0 = float(W @ np.array(evaluate(p, c.plan_from_owner(start)).lex()))
        for tf in cfg["ref_T"]:
            T = tf * med
            samples = []
            for ch in range(16):
                rep = Replica.make(c, start)
                run(c, rep, prot, Spec(W), 200_000, T, T, 100 * seed + ch, CONSTANT)
                samples.append(rep.st.owner.copy())
            occ = [s >= 0 for s in samples]
            diffs = []
            for a in range(16):
                for b in range(a + 1, 16):
                    work = (samples[a] >= 0) | (samples[b] >= 0)
                    diffs.append(float((samples[a] != samples[b])[work].mean()))
            pats = [len({day_pattern(c, o, i) for o in samples}) for i in range(c.m.I)]
            excess = [float(W @ np.array(evaluate(p, c.plan_from_owner(o)).lex())) - e0 for o in samples]
            # consistency of day marginals between two halves of the chains
            def marg(group):
                m = np.zeros((c.m.I, c.problem.grid.n_days))
                for o in group:
                    for i in range(c.m.I):
                        for d in day_pattern(c, o, i):
                            m[i, d] += 1
                return m / len(group)
            m1, m2 = marg(samples[:8]), marg(samples[8:])
            rows.append(dict(seed=seed, T_over_median=tf, pairwise_slot_diff=round(float(np.mean(diffs)), 4),
                             distinct_day_patterns_mean=round(float(np.mean(pats)), 2),
                             energy_excess_points_median=round(float(np.median(excess)) / 100, 1),
                             energy_excess_rel=round(float(np.median(excess)) / max(e0, 1), 4),
                             half_split_marginal_mae=round(float(np.abs(m1 - m2).mean()), 4)))
            log(f"B ref40-{seed} T={tf} diff={np.mean(diffs):.3f} patterns={np.mean(pats):.2f} excess={np.median(excess)/100:.0f}pts")
    write("b_diversity", rows)


def part_c() -> None:
    rows = []
    for kind in cfg["user_kinds"]:
        for uidx in range(cfg["users_per_kind"]):
            user = SimUser.make(kind, 500 + uidx)
            for wk in range(cfg["weeks"]):
                u = Universe(cornell_semester(300 + 10 * uidx + wk))
                theta = user.theta_now()
                friday = u.plan(theta, steps=300_000, seed=wk)
                week = live_week(u, user, friday, theta, wk, seed=wk * 31 + uidx)
                c_true = u.planner(theta)
                tau = user.kind.choice_tau * move_scale(u, c_true, friday, wk)
                lived_pat = [day_pattern(u.c, week.lived, i) for i in range(u.c.m.I)]
                for tf in cfg["tf_over_tau"]:
                    samples = [u.sample_c(c_true, friday, tf * tau, 4000, 1000 * wk + 7 * k + uidx) for k in range(16)]
                    for i in range(u.c.m.I):
                        pats = [set(day_pattern(u.c, o, i)) for o in samples]
                        for d in range(7):
                            pred = float(np.mean([d in pt for pt in pats]))
                            rows.append(dict(kind=kind, user=uidx, week=wk, tf_over_tau=tf, item=i, day=d, pred=pred,
                                             obs=int(d in lived_pat[i])))
                log(f"C {kind}-{uidx} week {wk} done")
    write("c_user_calibration", rows)


if __name__ == "__main__":
    warmup()
    part_a()
    part_b()
    part_c()
    log("done")
