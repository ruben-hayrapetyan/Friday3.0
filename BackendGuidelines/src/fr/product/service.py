"""What the Friday app calls (Q0; protocol in PROTOCOL.md). State lives in one JSON file in Friday's own folder, never
in todos.json (Todo List drops unknown keys). Every operation is deterministic given the stored state and the snapshot,
except `parse_constraints`, which asks Claude and only stores a *pending* parse until the user confirms it.
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.stats import norm

from ..core.evaluate import check
from ..engines.repair import ensure_deadlines
from ..sim.user import LEARNABLE
from ..sim.world import Universe
from . import adapter, clock
from . import constraints as C
from .durations import POPULATION, Obs, make, quantile
from .options import three
from .picks import Choice, ChoiceLearner

logging.getLogger("fr.core.pwl").setLevel(logging.ERROR)

DEFAULT_DIR = Path.home() / "Library/Application Support/Friday/engine"
DURATION_MODEL = "hier_fused_drift_fa3_recal"  # E020 round 3
OPTION_METHOD = "thompson+post"  # E022 round 2: Thompson alternatives, ranked so option 0 is the likeliest pick
Q_HARD, Q_FLEX = 0.95, 0.5  # E021 round 2: p80 -> p95 cut hard misses 15% -> 4% for ~23 min/day of slack
ASK_SAVING = 60.0  # minutes of padding an estimate must save (E024: voi60 is neutral on misses, frees ~20 min/day)
ACTUALS_PER_WEEK = 2  # "how long did it take?" questions (E024 round 2: hard misses 2.9% -> 0.2% at p95)
Z_HARD = float(norm.ppf(Q_HARD))
# The p95 cushion is at most this many times the expected length (decision 37). E021 measured p95 with a spread the
# model had learned; with no recorded lengths the spread is the prior's, and p95 came to 3.3x the user's own estimate
# (2 h -> 6 h 35 m), more than fit before the deadlines, so plans went late. Until TRUSTED lengths of that kind of task
# are recorded: your estimate + 25%, or Friday's guess + 50%; after that the learned p95, at most double.
CUSHION_ESTIMATE, CUSHION_GUESS, CUSHION_MAX, TRUSTED = 1.25, 1.5, 2.0, 3


def cushion(has_estimate: bool, recorded: int) -> float:
    """The most the plan reserves for a hard-deadline task, as a multiple of its expected length."""
    if recorded >= TRUSTED:
        return CUSHION_MAX
    return CUSHION_ESTIMATE if has_estimate else CUSHION_GUESS
# how an option differs, rule by rule: (when the option is better on it, when it is worse)
PHRASES = {
    "late_night": ("less late-night work", "more late-night work"),
    "deep_run": ("shorter focus runs", "longer unbroken focus runs"),
    "weekday_evenings": ("freer weekday evenings", "busier weekday evenings"),
    "weekends": ("freer weekends", "busier weekends"),
    "daily_load": ("no very heavy days", "heavier days"),
    "even_load": ("more even days", "less even days"),
    "energy": ("hard work at better hours", "hard work at low-energy hours"),
    "soft_late": ("soft deadlines met sooner", "soft deadlines met later"),
    "unscheduled": ("more tasks scheduled", "some tasks left unscheduled"),
    "chunk_cost": ("fewer, longer sessions", "more short sessions"),
    "spread": ("less cramming", "more cramming"),
    "cluster": ("project time grouped", "project time scattered"),
    "target_shortfall": ("weekly goals closer to done", "weekly goals further behind"),
    "elastic_shortfall": ("routines kept whole", "routines cut short"),
    "open_value": ("more side-project time", "less side-project time"),
}


def _now(params: dict) -> datetime:
    return adapter.local(params["now"]) if params.get("now") else datetime.now().replace(second=0, microsecond=0)


def overload(p) -> str | None:
    """When the work due by some deadline needs more time than is free before it, say so, for the first such deadline.
    Free time is every slot some of that work may use (no events, sleep or forbidden windows), at most the daily cap."""
    g = p.grid
    hard = sorted((it for it in p.items.values() if it.firmness == "hard" and it.due is not None
                   and it.amount == "fixed" and it.need > 0), key=lambda it: it.due)
    for i, it in enumerate(hard):
        if i + 1 < len(hard) and hard[i + 1].due == it.due:
            continue
        group = hard[:i + 1]
        need = sum(x.need for x in group)
        per_day: dict[int, int] = {}
        for sl in set().union(*(x.allowed_set for x in group)):
            if sl < g.S and g.end[sl] <= it.due:
                per_day[int(g.day[sl])] = per_day.get(int(g.day[sl]), 0) + int(g.units[sl])
        free = sum(min(v, p.day_caps[d]) for d, v in per_day.items())
        if need > free:
            when = datetime.fromisoformat(clock.iso(it.due)).strftime("%a %-d %b %H:%M")
            return (f"More is due than fits: {len(group)} tasks due by {when} need {need / 4:.0f} h with Friday's margin, and your rules "
                    f"and calendar leave {free / 4:.0f} h before then. Some work will be late; Friday keeps it as little "
                    f"as it can.")
    return None


class Engine:
    def __init__(self, data_dir: str | Path | None = None, steps: int = 300_000, parser=None):
        self.dir = Path(data_dir or os.environ.get("FRIDAY_ENGINE_DIR") or DEFAULT_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "engine.json"
        self.steps = steps
        self.parser = parser  # callable(text, context) -> fr.product.parse.Result; None = the Claude CLI
        self.s = json.loads(self.path.read_text()) if self.path.exists() else dict(
            version=1, estimates={}, actuals={}, constraints=[], pending={}, choices=[], plans={}, asked={})

    # ---------------------------------------------------------------- storage
    def save(self) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(self.s, f, indent=1)
        os.replace(tmp, self.path)

    # ---------------------------------------------------------------- durations
    def _model(self, courses: set[str]):
        seen = {a.get("course") for a in self.s["actuals"].values()} | courses
        mdl = make(DURATION_MODEL, list(POPULATION), sorted(c for c in seen if c))
        for a in sorted(self.s["actuals"].values(), key=lambda a: a["at"]):
            mdl.observe(Obs(a.get("course"), a["kind"], a.get("estimate"), a["minutes"], clock.parse(a["at"]) / 10080))
        return mdl

    def set_estimate(self, task_id: str, minutes: float, at: str | None = None) -> dict:
        self.s["estimates"][task_id] = dict(minutes=float(minutes), at=at or clock.iso(clock.to_minutes(datetime.now())))
        self.save()
        return dict(ok=True)

    def record_actual(self, task: dict, minutes: float, at: str | None = None) -> dict:
        t = adapter.tasks_from([dict(task, isDone=False)])[0]
        est = self.s["estimates"].get(t.id, {}).get("minutes")
        self.s["actuals"][t.id] = dict(minutes=float(minutes), kind=t.kind, course=t.course, estimate=est,
                                       at=at or clock.iso(clock.to_minutes(datetime.now())))
        self.save()
        return dict(ok=True, recorded=len(self.s["actuals"]))

    def predict(self, todos: list[dict], now: datetime) -> dict[str, dict]:
        tasks = adapter.tasks_from(todos)
        mdl = self._model({t.course for t in tasks if t.course})
        week = clock.to_minutes(now) / 10080
        n_same = {}
        for a in self.s["actuals"].values():
            n_same[(a.get("course"), a["kind"])] = n_same.get((a.get("course"), a["kind"]), 0) + 1
        out = {}
        for t in tasks:
            est = self.s["estimates"].get(t.id, {}).get("minutes")
            m, s = mdl.predict(t.course, t.kind, est, week)
            q = Q_HARD if t.hard else Q_FLEX
            n = n_same.get((t.course, t.kind), 0)
            plan_min = min(quantile(m, s, q), cushion(est is not None, n) * quantile(m, s, 0.5)) * (1 - t.progress)
            out[t.id] = dict(p50=round(quantile(m, s, 0.5)), p80=round(quantile(m, s, 0.8)), plan_minutes=round(plan_min),
                             quantile=q, estimate=est, similar_recorded=n_same.get((t.course, t.kind), 0),
                             kind=t.kind, course=t.course, spread=round(s, 3))
        return out

    def questions(self, todos: list[dict], now: datetime, max_estimates: int = 2, max_actuals: int = ACTUALS_PER_WEEK,
                  min_saving: float = ASK_SAVING) -> dict:
        """What Friday would like to ask (E024): an estimate for an open hard-deadline task without one, only when an
        answer would cut the time the plan reserves for it by at least `min_saving` minutes (largest saving first);
        and lengths of finished tasks nobody recorded, at most `max_actuals` asked in any 7 days."""
        tasks = adapter.tasks_from(todos)
        mdl = self._model({t.course for t in tasks if t.course})
        week = clock.to_minutes(now) / 10080
        recorded: dict = {}
        for a in self.s["actuals"].values():
            recorded[(a.get("course"), a["kind"])] = recorded.get((a.get("course"), a["kind"]), 0) + 1
        cands = []
        for t in tasks:
            if not t.hard or t.id in self.s["estimates"] or t.id in self.s["asked"]:
                continue
            m, s0 = mdl.predict(t.course, t.kind, None, week)
            _, s1 = mdl.predict(t.course, t.kind, math.exp(m), week)  # the spread an answer would leave
            n = recorded.get((t.course, t.kind), 0)
            pad0 = min(math.exp(Z_HARD * s0), cushion(False, n))
            pad1 = min(math.exp(Z_HARD * s1), cushion(True, n))
            saving = math.exp(m) * (pad0 - pad1) * (1 - t.progress)
            if saving >= min_saving:
                cands.append((saving, t, round(math.exp(m))))
        cands.sort(key=lambda x: -x[0])
        done_ids = {str(t["id"]) for t in todos if t.get("isDone")}
        week_ago = clock.to_minutes(now) - 7 * 1440
        asked_lately = sum(1 for tid, at in self.s["asked"].items() if tid in done_ids and clock.parse(at) >= week_ago)
        done = [t for t in todos if t.get("isDone") and str(t["id"]) not in self.s["actuals"]
                and str(t["id"]) not in self.s["asked"]][:max(0, max_actuals - asked_lately)]
        return dict(estimates=[dict(task_id=t.id, title=t.title, guess_minutes=g, saves_minutes=round(sv))
                               for sv, t, g in cands[:max_estimates]],
                    actuals=[dict(task_id=str(t["id"]), title=t["title"]) for t in done])

    def mark_asked(self, task_id: str) -> dict:
        self.s["asked"][task_id] = clock.iso(clock.to_minutes(datetime.now()))
        self.save()
        return dict(ok=True)

    # ---------------------------------------------------------------- constraints
    def context(self, todos: list[dict], events: list[dict], now: datetime) -> dict:
        tasks = adapter.tasks_from(todos)
        return dict(today=now.strftime("%Y-%m-%d (%A)"), courses=sorted({t.course for t in tasks if t.course}),
                    tasks=[dict(title=t.title, course=t.course, kind=adapter.PRESET[t.kind] if t.kind not in
                                ("pset", "essay", "lab") else "assignment", type=t.type, energy=None) for t in tasks],
                    events=sorted({e.get("title", "") for e in events})[:40])

    def parse_constraints(self, text: str, todos: list[dict], events: list[dict], now: datetime) -> dict:
        from .parse import DEFAULT, parse_text

        ctx = self.context(todos, events, now)
        r = self.parser(text, ctx) if self.parser else parse_text(text, ctx, DEFAULT)
        if r.parse is None:
            return dict(ok=False, error=r.error)
        pid = uuid.uuid4().hex[:12]
        self.s["pending"][pid] = dict(text=text, parse=r.parse.model_dump(mode="json"), at=clock.iso(clock.to_minutes(now)))
        self.save()
        p = r.parse
        return dict(ok=True, pending_id=pid,
                    constraints=[dict(index=i, kind=c.kind, paraphrase=c.paraphrase,
                                      hard=getattr(c, "strength", "hard") == "hard") for i, c in enumerate(p.constraints)],
                    questions=p.questions, unsupported=[u.model_dump() for u in p.unsupported])

    def confirm_constraints(self, pending_id: str, accept: list[int]) -> dict:
        pend = self.s["pending"].pop(pending_id)
        parse = C.Parse.model_validate(pend["parse"])
        added = []
        for i in accept:
            cid = uuid.uuid4().hex[:12]
            self.s["constraints"].append(dict(id=cid, text=pend["text"], constraint=parse.constraints[i].model_dump(mode="json"),
                                              added=pend["at"]))
            added.append(cid)
        self.save()
        return dict(ok=True, added=added)

    def list_constraints(self) -> list[dict]:
        out = []
        for c in self.s["constraints"]:
            con = C.Parse.model_validate(dict(constraints=[c["constraint"]])).constraints[0]
            out.append(dict(id=c["id"], paraphrase=con.paraphrase, kind=con.kind, text=c["text"]))
        return out

    def remove_constraint(self, cid: str) -> dict:
        self.s["constraints"] = [c for c in self.s["constraints"] if c["id"] != cid]
        self.save()
        return dict(ok=True)

    def _constraints(self) -> list:
        return list(C.Parse.model_validate(dict(constraints=[c["constraint"] for c in self.s["constraints"]])).constraints)

    # ---------------------------------------------------------------- plans and picks
    def _learner(self) -> ChoiceLearner:
        L = ChoiceLearner(len(LEARNABLE))
        if self.s["choices"]:
            L.add([Choice(np.array(c["phis"]), c["chosen"], i) for i, c in enumerate(self.s["choices"])])
        return L

    def plan(self, todos: list[dict], events: list[dict], now: datetime, method: str = OPTION_METHOD) -> dict:
        tasks = adapter.tasks_from(todos)
        pred = self.predict(todos, now)
        sc, ids = adapter.scenario(now, tasks, {k: v["plan_minutes"] for k, v in pred.items()}, events)
        sc, notes = C.apply(sc, self._constraints())
        u = Universe(sc)
        over = overload(u.p)
        if over:
            notes = [over] + notes
        # every option starts from (and its deadline walls protect) the repaired zero-late start, not raw construction
        rep = ensure_deadlines(u.pr, seed=0, use_cpsat=len(u.p.items) <= 60, cpsat_s=2.0)
        u.pr = replace(u.pr, owner=rep.owner)
        L = self._learner()
        opts = three(u, L, method, steps=self.steps, seed=0)
        phis = [u.phi(x) for x in opts.plans]
        out = []
        for k, owner in enumerate(opts.plans):
            plan = u.c.plan_from_owner(owner)
            late = [ids.get(int(key.split(":")[1])) for key, it in u.p.items.items()
                    if it.due is not None and any(u.p.grid.end[s] > it.due for s in plan.get(key, ()) if s < u.p.grid.S)]
            unplaced = [ids.get(int(key.split(":")[1])) for key, it in u.p.items.items()
                        if it.amount == "fixed" and sum(int(u.p.grid.units[s]) for s in plan.get(key, ())) < it.need]
            out.append(dict(option=k, label=opts.labels[k], summary=self._summary(phis[0], phis[k], L.theta) if k else
                            "Friday's recommendation", blocks=adapter.blocks(u.c, owner, ids),
                            late_tasks=[t for t in late if t], unplaced_tasks=[t for t in unplaced if t],
                            valid=not check(u.p, plan)))
        pid = uuid.uuid4().hex[:12]
        self.s["plans"][pid] = dict(at=clock.iso(clock.to_minutes(now)), phis=[p.tolist() for p in phis])
        if len(self.s["plans"]) > 10:
            for old in sorted(self.s["plans"], key=lambda k: self.s["plans"][k]["at"])[:-10]:
                del self.s["plans"][old]
        self.save()
        return dict(plan_id=pid, options=out, notes=notes, minutes={k: v["plan_minutes"] for k, v in pred.items()})

    def _summary(self, phi0: np.ndarray, phik: np.ndarray, theta: np.ndarray) -> str:
        """'Freer weekday evenings and less late-night work; busier weekends.' (weighted by the learned weights)"""
        d = (phik - phi0) * theta
        better = [PHRASES[LEARNABLE[i]][0] for i in np.argsort(d)[:2] if d[i] < -0.05]
        worse = [PHRASES[LEARNABLE[i]][1] for i in np.argsort(-d)[:1] if d[i] > 0.05]
        text = " and ".join(better)
        if worse:
            text = f"{text}; {worse[0]}" if text else worse[0]
        return (text[0].upper() + text[1:] + ".") if text else "A different arrangement of similar quality."

    def pick(self, plan_id: str, option: int) -> dict:
        p = self.s["plans"][plan_id]
        self.s["choices"].append(dict(phis=p["phis"], chosen=int(option), at=p["at"]))
        self.save()
        L = self._learner()
        return dict(ok=True, picks=len(self.s["choices"]),
                    weights={r: round(float(w), 3) for r, w in zip(LEARNABLE, L.theta)})

