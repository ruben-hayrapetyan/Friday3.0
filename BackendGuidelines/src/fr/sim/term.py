"""A term lived day by day (RQ11-RQ13, RQ17): every morning Friday plans the next 14 days from predicted lengths, the
student works exactly the planned blocks, tasks finish when their *true* length is reached, and recorded lengths feed
the duration model. Misses come from plans built on lengths that were too short; idle time from lengths too long.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..core.builder import spec
from ..core.generate import Scenario, _fixed_week, _Ids
from ..core.settings import Settings
from ..product.durations import Model, Obs, remaining
from ..product.planner import plan
from .durations import MONDAY0, Item, Student, at

HARD = {"pset", "essay", "lab", "exam_prep", "project"}


@dataclass
class TermConfig:
    weeks: int = 8
    q_hard: float = 0.8
    q_flex: float = 0.5
    steps: tuple[int, int] = (150_000, 100_000)
    plan_at: str = "08:00"
    seed: int = 0


@dataclass
class TermResult:
    rows: list[dict]  # one per task
    days: list[dict]  # one per planning day
    asked: list[dict] = field(default_factory=list)


def fixed_events(seed: int, weeks: int) -> list:
    rng = np.random.default_rng(seed + 7919)
    ids = _Ids()
    ids.n = 1_000_000
    days = range(MONDAY0 - 1, MONDAY0 + 7 * weeks + 15)
    specs = _fixed_week(rng, ids, days, hours_per_week=15.0)
    for s in specs:  # course names match the student's courses
        if s.area and s.area.startswith("CS") and len(s.area) == 3:
            s.area = None
    return specs


def simulate(student: Student, items: list[Item], model: Model, cfg: TermConfig, asker=None,
             ask_actual=None) -> TermResult:
    """`asker(item, model, now, week) -> bool` may ask the student for an estimate of a task without one;
    `ask_actual(item, model, week) -> bool` may ask how long a finished, unrecorded task took (policy experiment E024)."""
    fixed = fixed_events(cfg.seed, cfg.weeks)
    known_est: dict[int, float | None] = {}
    worked: dict[int, float] = {it.id: 0.0 for it in items}
    finish: dict[int, int] = {}
    by_key = {f"item:{it.id}": it for it in items}
    days, asked = [], []
    end = at(MONDAY0 + 7 * cfg.weeks, cfg.plan_at)
    for day in range(7 * cfg.weeks):
        now = at(MONDAY0 + day, cfg.plan_at)
        week = day / 7
        active = [it for it in items if it.release <= now and it.id not in finish]
        for it in active:
            if it.id not in known_est:
                known_est[it.id] = it.estimate_min
                if it.estimate_min is None and asker is not None and asker(it, model, now, week):
                    known_est[it.id] = it.answer_estimate()
                    asked.append(dict(item=it.id, day=day, kind=it.kind, what="estimate"))
        if not active:
            continue
        specs = []
        for it in active:
            if getattr(model, "oracle", False):  # reference: the true length is known
                m, s = math.log(it.true_min), 1e-3
            else:
                m, s = model.predict(it.course, it.kind, known_est[it.id], week)
            q = cfg.q_hard if it.kind in HARD else cfg.q_flex
            rem = remaining(m, s, q, worked[it.id])
            dur = int(max(15, math.ceil(rem / 15) * 15))
            specs.append(spec(it.preset, it.id, it.title, area=it.course, duration_min=dur, due=it.due,
                              release=max(it.release, now), firmness="hard" if it.kind in HARD else "soft",
                              min_chunk_min=min(60 if it.kind == "project" else 30, dur)))
        sc = Scenario(f"term-{student.seed}-d{day}", fixed + specs, [], now, Settings())
        p = sc.build()
        pr, owner, info = plan(p, cfg.steps, seed=cfg.seed * 1000 + day)
        g = p.grid
        idle = 0.0
        planned = 0.0
        for s in range(g.S):
            if g.start[s] >= now + 1440:
                break
            o = int(owner[s])
            if o < 0:
                continue
            it = by_key.get(pr.c.keys[o])
            if it is None:
                continue
            mins = float(g.end[s] - g.start[s])
            planned += mins
            if it.id in finish:
                idle += mins
                continue
            need = it.true_min - worked[it.id]
            worked[it.id] += mins
            if worked[it.id] >= it.true_min - 1e-9:
                finish[it.id] = int(g.start[s] + need)
                idle += mins - need
                rec = it.record()
                wk_f = (finish[it.id] / 1440 - MONDAY0) / 7
                if rec is None and ask_actual is not None and ask_actual(it, model, wk_f):
                    rec = it.answer_actual()
                    asked.append(dict(item=it.id, day=day, kind=it.kind, what="actual"))
                if rec is not None:
                    model.observe(Obs(it.course, it.kind, known_est[it.id], rec, wk_f))
        days.append(dict(day=day, active=len(active), planned_h=planned / 60, idle_h=idle / 60,
                         repair=info["repair"], repair_late=info["repair_late"]))
    rows = []
    for it in items:
        if it.due > end:
            continue
        f = finish.get(it.id)
        late_h = max(0.0, ((f if f is not None else end) - it.due) / 60)
        rows.append(dict(item=it.id, kind=it.kind, course=it.course, hard=it.kind in HARD, true_min=it.true_min,
                         estimate=it.estimate_min, finished=f is not None, late=late_h > 0, late_h=late_h))
    return TermResult(rows, days, asked)
