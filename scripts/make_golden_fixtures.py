"""Write tests/fixtures/golden/ from the research code, once (REUSE.md rule 3).

This is the only file in the repo that may import the research package. Run it inside the research environment:

    uv run --project reference/research python scripts/make_golden_fixtures.py

Each fixture is one built research problem (items with their allowed slots, fixed items, nights, dials, rules)
and five plans with the stage values, per-rule totals and violations the research evaluator gives them.
Times stay in the research's minutes, whose day 0 is a Monday; the loader maps them onto a UTC grid.
"""

import gzip
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from fr.core.defaults import REFERENCE_RULES
from fr.core.evaluate import check, evaluate
from fr.core.generate import ADVERSARIAL, cornell_semester, reference_instance, tiny
from fr.core.plans import random_plan
from fr.core.problem import EASY, PUSH, DayScales
from fr.engines.prepare import prepare
from fr.samplers.anneal import SAConfig, anneal, protected

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden"

EXTRA_RULES = [
    dict(type="time_preference", name="sunday_rest", weight=3, params=dict(days=["sun"], price=4)),
    dict(type="time_preference", name="no_mornings", weight=1, params=dict(start="04:00", end="07:00", price="forbid")),
    dict(type="time_preference", name="late_wrap", weight=1, params=dict(start="22:00", end="02:00", price=2)),
    dict(type="finish_early", name="finish_early", weight=1, params=dict(days=2)),
    dict(
        type="after_event",
        name="after_class",
        weight=1,
        params=dict(events=dict(event_kind="class"), measure_from="last", slope=1, cap=3),
        scope=dict(preset="habit"),
    ),
    dict(
        type="after_event",
        name="after_any",
        weight=1,
        params=dict(events=dict(event_kind="class"), measure_from="any", slope=2, cap=4, on_days_without="cap"),
        scope=dict(preset="chore"),
    ),
    dict(
        type="batch_by_day",
        name="batch_chores",
        weight=2,
        params=dict(by="preset"),
        scope=dict(preset=["chore", "errand"]),
    ),
    dict(type="batch_by_day", name="batch_area", weight=2, params=dict(by="area"), scope=dict(firmness="hard")),
]
MIXED = DayScales(0.8, 1.5, 2.0, 0.5)


def instances():
    """40 scenarios across sizes, adversarial families, dials and every rule type."""
    out = []
    for n, seeds in ((20, range(4)), (40, range(3)), (60, range(3)), (150, range(2))):
        out += [(f"ref{n}-s{s}", reference_instance(n, s), {}) for s in seeds]
    out += [(f"cornell-s{s}", cornell_semester(s), {}) for s in range(2)]
    for s in range(3):
        sc = cornell_semester(10 + s)
        sc.extra_rules = EXTRA_RULES
        out.append((f"cornell-extra-s{s}", sc, {"quotas": True}))
    for name, scales in (("easy", EASY), ("push", PUSH), ("mixed", MIXED)):
        sc = cornell_semester(20)
        sc.scales = [scales] * 7 + [DayScales()] * 7
        out.append((f"cornell-{name}", sc, {"debt": True}))
    for family, make in ADVERSARIAL.items():
        out += [(f"{family}-s{s}", make(s), {}) for s in range(2)]
    out += [(f"tiny-s{s}", tiny(s, 8, 3), {}) for s in range(7)]
    sc = reference_instance(30, 7)
    sc.extra_rules = EXTRA_RULES
    out.append(("ref30-extra-current", sc, {"current": True, "quotas": True}))
    return out


def build(sc, options):
    problem = sc.build()
    if options.get("current"):
        problem = sc.build(current=random_plan(problem, np.random.default_rng(99), 0.3))
    if options.get("quotas"):
        for n, item in enumerate(problem.items.values()):
            if n % 3 == 0 and item.amount == "fixed":
                item.quotas = {1: 4, 2: 8}
                item.progress_by_week = {1: 1}
    if options.get("debt"):
        problem.nights = {d: replace(night, debt_hours=float(d % 3)) for d, night in problem.nights.items()}
        problem._price_cache.clear()
    return problem


def ranges(slots):
    out = []
    for s in sorted(int(x) for x in slots):
        if out and out[-1][1] == s - 1:
            out[-1][1] = s
        else:
            out.append([s, s])
    return out


def item_json(it):
    return {
        "key": it.key, "title": it.title, "area": it.area, "tags": list(it.tags), "preset": it.preset,
        "energy": it.energy, "importance": it.importance, "firmness": it.firmness, "amount": it.amount,
        "daily_ceiling": it.daily_ceiling, "progress_today": it.progress_today, "need": it.need, "min": it.min,
        "ideal": it.ideal, "max": it.max, "target": it.target, "cap": it.cap, "progress": it.progress,
        "progress_by_week": {str(k): v for k, v in it.progress_by_week.items()}, "release": it.release,
        "due": it.due, "window_is_hard": it.window_is_hard, "shape": it.shape, "min_chunk": it.min_chunk,
        "max_chunk": it.max_chunk, "chunk_cost": it.chunk_cost, "spread": it.spread, "size_hours": it.size_hours,
        "tentative": it.tentative, "allowed": ranges(it.allowed), "locked": ranges(it.locked),
        "preferred": ranges(it.preferred), "current": ranges(it.current),
        "depends_on": [{"key": d.key, "fraction": d.fraction, "lag_min": d.lag_min, "total": d.total,
                        "progress": d.progress} for d in it.depends_on],
        "quotas": {str(k): v for k, v in it.quotas.items()},
    }  # fmt: skip


def problem_json(name, sc, problem):
    g = problem.grid
    return {
        "name": name,
        "grid": {"now": g.now, "end": sc.end, "horizon_days": sc.settings.horizon_days,
                 "fine_days": sc.settings.fine_days, "day_start": sc.settings.day_start,
                 "week_start": sc.settings.week_start, "slots": g.S, "horizon_end": g.horizon_end},
        "scale": sc.settings.scale,
        "minimize_changes_scale": sc.settings.minimize_changes_scale,
        "items": [item_json(it) for it in problem.items.values()],
        "fixed": [{"title": f.title, "kind": f.kind, "start": f.start, "end": f.end, "tags": list(f.tags),
                   "buf_before": f.buf_before, "buf_after": f.buf_after, "blocks_time": f.blocks_time}
                  for f in problem.fixed],
        "nights": {str(d): {"bedtime": n.bedtime, "wake": n.wake, "margin": n.margin, "debt_hours": n.debt_hours}
                   for d, n in problem.nights.items()},
        "day_caps": list(problem.day_caps),
        "dials": [[s.capacity, s.rest, s.spread, s.growth] for s in problem.scales],
        "energy_map": {str(wd): list(row) for wd, row in problem.energy_map.items()},
        "rules": [dict(r) for r in (sc.rule_specs if sc.rule_specs is not None else REFERENCE_RULES)]
        + [dict(r) for r in sc.extra_rules],
        "blocked": ranges(np.flatnonzero(problem.blocked)),
        "core": ranges(np.flatnonzero(problem.core)),
    }  # fmt: skip


def plans(prepared, seed):
    c, start = prepared.c, prepared.owner
    out = [("constructed", start)]
    annealed = anneal(c, start, SAConfig(steps=60_000, seed=seed, t0_scale=0.1, t1_scale=0.003))
    out.append(("annealed", annealed.owner))
    prot = protected(c, start)
    for k in range(3):
        # A hot chain behind the walls wanders to a different valid plan from the same start.
        hot = anneal(c, start, SAConfig(steps=4000 * (k + 1), seed=seed + 100 + k, t0=1e9, t1=1e9), prot)
        out.append((f"random{k}", hot.final))
    return [(label, c.plan_from_owner(owner)) for label, owner in out]


def scored(problem, label, plan):
    ev = evaluate(problem, plan)
    return {
        "label": label,
        "plan": {k: ranges(v) for k, v in plan.items() if v},
        "stage_values": ev.stage_values,
        "rule_totals": ev.rule_totals,
        "violations": sorted(f"{v.code}:{v.key}" for v in check(problem, plan)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (name, sc, options) in enumerate(instances()):
        problem = build(sc, options)
        prepared = prepare(problem)  # demotes contradictory locks, so the problem is saved after it
        fixture = problem_json(name, sc, problem)
        fixture["plans"] = [scored(problem, label, plan) for label, plan in plans(prepared, n)]
        with gzip.open(OUT / f"{name}.json.gz", "wt") as f:
            json.dump(fixture, f, separators=(",", ":"))
        valid = sum(not p["violations"] for p in fixture["plans"])
        print(f"{name}: {len(fixture['items'])} items, {fixture['grid']['slots']} slots, {valid}/5 plans valid")


if __name__ == "__main__":
    main()
