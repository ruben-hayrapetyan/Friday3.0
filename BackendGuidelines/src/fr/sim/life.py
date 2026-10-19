"""End to end (RQ17): a student with true task lengths (sim.durations), true rule weights and moods (sim.user) and true
habits written as text (constraints), living several weeks with one of the Friday systems.

Every morning Friday plans the next 14 days. On Mondays a system with options shows three and the user picks one by
true energy; on other days (and in single-plan systems) the recommended plan is used. The user works the day's planned
blocks except where a block breaks one of their real habits (work during their gym slot, after their real bedtime, past
their own daily limit): those blocks are lost. Tasks finish when their true length is reached. Friday learns lengths
from recordings (and questions, if the system asks), weights from picks and the usual pairs and drags.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace

import numpy as np
from scipy.stats import norm

from ..core.builder import spec
from ..core.generate import Scenario
from ..core.settings import Settings
from ..engines.repair import ensure_deadlines
from ..product import constraints as C
from ..product.durations import Obs, make, remaining
from ..product.options import three
from ..product.picks import Choice, ChoiceLearner
from .durations import MONDAY0, Student, at, term
from .picks import pick
from .term import HARD, fixed_events
from .user import LEARNABLE, MISSING_RULE, SimUser
from .world import Universe, live_week, move_scale, true_energy


@dataclass
class System:
    name: str
    durations: str = "hier_fused_drift_fa3_recal"
    ask: str = "never"  # never | voi60 | always (estimate questions)
    ask_actual: str = "never"  # never | always | budgetN (lengths of finished tasks nobody recorded, at most N a week)
    q_hard: float = 0.95  # planning quantile for hard deadlines (E021); flexible tasks at the median
    options: str | None = "thompson"  # None = one plan
    mode: str = "mnl"  # mnl | pairs_only | none
    pairs: bool = True  # also learn from the usual pairs and drags (the app as built collects picks only)
    constraints: bool = True  # are the user's parsed constraints applied?
    steps: tuple[int, int] = (150_000, 100_000)


@dataclass
class Person:
    pref_kind: str
    duration_kind: str
    seed: int
    truth: list  # constraints the person really holds (gold readings)
    parsed: list  # what Friday stored after parsing their text (and the user confirming it)
    p_estimate: float = 0.6
    load: float = 1.3


def _asker(name: str, q_hard: float):
    if name == "never":
        return None
    if name == "always":
        return lambda it, model, week: True
    need = float(name[3:])
    z = float(norm.ppf(q_hard))

    def voi(it, model, week):
        if it.kind not in HARD:
            return False
        m, s0 = model.predict(it.course, it.kind, None, week)
        _, s1 = model.predict(it.course, it.kind, math.exp(m), week)
        return math.exp(m) * (math.exp(z * s0) - math.exp(z * s1)) >= need
    return voi


def live(person: Person, sysm: System, weeks: int = 6) -> dict:
    st = Student.make(replace(_dtype(person.duration_kind), p_estimate=person.p_estimate), person.seed, load=person.load)
    items = term(st, weeks + 2)
    user = SimUser.make(person.pref_kind, person.seed)
    rng = np.random.default_rng(person.seed + 99)
    model = make(sysm.durations, ["pset", "reading", "essay", "lab", "exam_prep", "project"],
                 ["CS 2110", "MATH 2940", "PHYS 2213", "ENGL 1170"])
    L = ChoiceLearner(len(LEARNABLE), mode="mnl" if sysm.mode == "pairs_only" else sysm.mode, use_pairs=sysm.pairs)
    asker = _asker(sysm.ask, sysm.q_hard)
    cap_actual = None if sysm.ask_actual == "never" else 10 ** 6 if sysm.ask_actual == "always" else \
        int(sysm.ask_actual[6:])
    asked_actual: dict[int, int] = {}
    fixed = fixed_events(person.seed, weeks)
    extra = [MISSING_RULE] if user.kind.missing_weight else []
    extra_true = {"missing:fri_sat_evening": user.kind.missing_weight} if user.kind.missing_weight else {}
    known_est: dict[int, float | None] = {}
    worked = {it.id: 0.0 for it in items}
    finish: dict[int, int] = {}
    by_key = {f"item:{it.id}": it for it in items}
    end = at(MONDAY0 + 7 * weeks, "08:00")
    log = dict(conflict_h=0.0, lost_h=0.0, questions=0, plan_s=[], rec_picked=[], regret_rec=[], regret_pick=[],
               planned_h=0.0)
    for day in range(7 * weeks):
        now = at(MONDAY0 + day, "08:00")
        week = day / 7
        if day % 7 == 0:
            user.step_mood()
        active = [it for it in items if it.release <= now and it.id not in finish]
        for it in active:
            if it.id not in known_est:
                known_est[it.id] = it.estimate_min
                if it.estimate_min is None and asker is not None and asker(it, model, week):
                    known_est[it.id] = it.answer_estimate()
                    log["questions"] += 1
        if not active:
            continue
        specs = []
        for it in active:
            m, s = model.predict(it.course, it.kind, known_est[it.id], week)
            rem = remaining(m, s, sysm.q_hard if it.kind in HARD else 0.5, worked[it.id])
            dur = int(max(15, math.ceil(rem / 15) * 15))
            specs.append(spec(it.preset, it.id, it.title, area=it.course, duration_min=dur, due=it.due,
                              release=max(it.release, now), firmness="hard" if it.kind in HARD else "soft",
                              min_chunk_min=min(60 if it.kind == "project" else 30, dur)))
        base = Scenario(f"life-{person.seed}-{day}", fixed + specs, [], now, Settings())
        true_sc, _ = C.apply(base, person.truth)
        fr_sc, _ = C.apply(base, person.parsed) if sysm.constraints else (base, [])
        t0 = time.perf_counter()
        u = Universe(fr_sc, extra)
        rep = ensure_deadlines(u.pr, seed=day, steps=200_000, use_cpsat=False)
        u.pr = replace(u.pr, owner=rep.owner)
        monday = day % 7 == 0
        if monday and sysm.options:
            opts = three(u, L, sysm.options, steps=sum(sysm.steps), seed=day)
            plans = opts.plans
        else:
            plans = [u.plan(L.theta, steps=sum(sysm.steps), seed=day)]
        log["plan_s"].append(time.perf_counter() - t0)
        k = 0
        if monday:
            E = np.array([true_energy(u, user, x) for x in plans])
            x_star = u.plan(user.theta_now(), extra_true, steps=400_000, seed=day)
            e_star = true_energy(u, user, x_star)
            scale = move_scale(u, u.planner(user.theta_now(), extra_true), x_star, day)
            if len(plans) > 1:
                k = pick(user, E, scale, rng)
            rel = max(abs(e_star), 1.0)
            log["rec_picked"].append(k == 0)
            log["regret_rec"].append((E[0] - e_star) / rel)
            log["regret_pick"].append((E[k] - e_star) / rel)
            rankings = live_week(u, user, plans[k], L.theta, int(week), seed=day * 31 + person.seed).rankings \
                if sysm.mode != "none" and sysm.pairs else []
            choices = [Choice(np.stack([u.phi(x) for x in plans]), k, int(week))] \
                if len(plans) > 1 and sysm.mode not in ("none", "pairs_only") else []
            L.add(choices, rankings)
        owner = plans[k]
        # live the day: blocks that break the person's real habits are lost
        pt = true_sc.build()
        g = u.p.grid
        day_used: dict[int, float] = {}
        cap = true_sc.settings.day_cap_units * 15
        for s in range(g.S):
            if g.start[s] >= now + 1440:
                break
            o = int(owner[s])
            if o < 0:
                continue
            key = u.c.keys[o]
            it = by_key.get(key)
            if it is None:
                continue
            mins = float(g.end[s] - g.start[s])
            log["planned_h"] += mins / 60
            ti = pt.items.get(key)
            d = int(g.day[s])
            if ti is None or s not in ti.allowed_set or day_used.get(d, 0.0) + mins > cap:
                log["conflict_h"] += mins / 60
                continue
            day_used[d] = day_used.get(d, 0.0) + mins
            if it.id in finish:
                continue
            need = it.true_min - worked[it.id]
            worked[it.id] += mins
            if worked[it.id] >= it.true_min - 1e-9:
                finish[it.id] = int(g.start[s] + need)
                rec = it.record()
                if rec is None and cap_actual is not None and asked_actual.get(int(week), 0) < cap_actual:
                    rec = it.answer_actual()  # "how long did it take?", answered from memory
                    asked_actual[int(week)] = asked_actual.get(int(week), 0) + 1
                    log["questions"] += 1
                if rec is not None:
                    model.observe(Obs(it.course, it.kind, known_est[it.id], rec, (finish[it.id] / 1440 - MONDAY0) / 7))
    hard = [it for it in items if it.kind in HARD and it.due <= end]
    late = [it for it in hard if finish.get(it.id, end + 1) > it.due]
    return dict(person=person.seed, pref_kind=person.pref_kind, duration_kind=person.duration_kind, system=sysm.name,
                hard_tasks=len(hard), hard_late=len(late) / max(len(hard), 1),
                late_h=sum(max(0, (finish.get(it.id, end) - it.due) / 60) for it in hard),
                conflict_h_week=log["conflict_h"] / weeks, questions_week=log["questions"] / weeks,
                rec_picked=float(np.mean(log["rec_picked"][1:])) if len(log["rec_picked"]) > 1 else float("nan"),
                regret_rec=float(np.mean(log["regret_rec"])), regret_pick=float(np.mean(log["regret_pick"])),
                cos=float(L.theta @ user.theta / np.linalg.norm(L.theta) / np.linalg.norm(user.theta)),
                plan_s_median=float(np.median(log["plan_s"])))


def _dtype(name: str):
    from .durations import STUDENT_TYPES
    return STUDENT_TYPES[name]
