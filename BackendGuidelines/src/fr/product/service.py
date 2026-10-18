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
from ..engines.repair import ensure_deadlines, late_value
from ..sim.user import LEARNABLE
from ..sim.world import Universe
from . import adapter, clock
from . import constraints as C
from .durations import POPULATION, Obs, make, quantile
from .events import key as ev_key
from .events import rate as rate_events
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


def edf_start(p, keys: tuple, how: str = "mdd") -> np.ndarray:
    """A start for an overloaded week: dated work by modified due date from now, then work with no due date
    (decision 39): nothing due today is left for Friday, and short tasks aren't left far behind long ones. `how`:
    modified due date ("mdd") or plain earliest deadline first ("edf"). Built from whole sessions (never shorter than the task's minimum, one sitting where asked), within
    the daily caps, each task after what it depends on; locked slots stay."""
    g = p.grid
    ix = {k: i for i, k in enumerate(keys)}
    owner = np.full(g.S + 1, -1, dtype=np.int64)
    left = {k: it.need for k, it in p.items.items() if it.amount == "fixed" and it.need > 0}
    used: dict[int, int] = {}
    done_at: dict[str, int] = {}
    for k, it in p.items.items():
        for sl in it.locked:
            if sl < g.S:
                owner[sl] = ix[k]
                left[k] = left.get(k, 0) - int(g.units[sl])
                used[int(g.day[sl])] = used.get(int(g.day[sl]), 0) + int(g.units[sl])
                done_at[k] = max(done_at.get(k, -1), sl)

    def runs(k: str, first: int) -> list[list[int]]:
        out, cur = [], []
        for sl in range(first, g.S):
            ok = owner[sl] < 0 and sl in p.items[k].allowed_set
            if ok and cur and sl == cur[-1] + 1 and g.day[sl] == g.day[cur[-1]]:
                cur.append(sl)
            else:
                if cur:
                    out.append(cur)
                cur = [sl] if ok else []
        if cur:
            out.append(cur)
        return out

    pos = {k: n for n, k in enumerate(keys)}
    dated = [k for k in left if left[k] > 0 and p.items[k].due is not None]
    undated = sorted((k for k in left if left[k] > 0 and p.items[k].due is None), key=lambda k: pos[k])

    def place(k: str) -> None:
        it = p.items[k]
        least = it.need if it.shape == "one_sitting" else max(1, it.min_chunk)
        most = it.max_chunk or 10 ** 9
        if any(left.get(dp.key, 0) > 0 for dp in it.depends_on):
            return  # what it waits for didn't fit in the horizon, so neither does it
        after = max((done_at.get(dp.key, -1) for dp in it.depends_on), default=-1)
        for run in runs(k, after + 1):
            if left[k] <= 0:
                break
            d = int(g.day[run[0]])
            take = min(left[k], sum(int(g.units[sl]) for sl in run), p.day_caps[d] - used.get(d, 0), most)
            if 0 < left[k] - take < least:  # never strand a remainder shorter than a session
                take = left[k] - least
            piece, units = [], 0
            for sl in run:  # slots are 15 min in the first week and longer after; count units, not slots
                if units + int(g.units[sl]) > take:
                    break
                piece.append(sl)
                units += int(g.units[sl])
            if units < least:
                continue
            for sl in piece:
                owner[sl] = ix[k]
                used[d] = used.get(d, 0) + int(g.units[sl])
                left[k] -= int(g.units[sl])
                done_at[k] = max(done_at.get(k, -1), sl)

    order = (sorted(dated, key=lambda k: (p.items[k].due, pos[k])) if how == "edf"
             else mdd_order(p, dated, left, owner, pos))
    for k in order:
        place(k)
    for k in undated:
        place(k)
    owner[g.S] = -1
    return owner


def mdd_order(p, dated: list[str], left: dict, owner: np.ndarray, pos: dict) -> list[str]:
    """Modified due date, prerequisites first: next, the task with the smallest max(due, now + its length). Earliest
    deadline first while there is time; once work will be late, short tasks before long ones (decision 39)."""
    deps = {k: {dp.key for dp in p.items[k].depends_on} & set(dated) for k in dated}
    free = np.flatnonzero(owner[:p.grid.S] < 0)
    t = int(p.grid.start[free[0]]) if len(free) else p.grid.now
    order, rest = [], list(dated)
    while rest:
        ready = [k for k in rest if not deps[k] & set(rest)] or rest
        k = min(ready, key=lambda k: (max(p.items[k].due, t + left[k] * 15), p.items[k].due, pos[k]))
        rest.remove(k)
        order.append(k)
        t += left[k] * 15
    return order


def shortfall(p) -> dict | None:
    """The deadline where the work due by it most exceeds the free time before it: {due (wall clock), tasks, need_h,
    free_h}, or None when everything fits. Free time is every slot some of that work may use (no events, sleep or
    forbidden windows), at most the daily cap."""
    g = p.grid
    hard = sorted((it for it in p.items.values() if it.firmness == "hard" and it.due is not None
                   and it.amount == "fixed" and it.need > 0 and "break" not in it.tags), key=lambda it: it.due)
    worst = None
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
        if need > free and (worst is None or need - free > worst[0]):
            worst = (need - free, it.due, len(group), need, free)
    if worst is None:
        return None
    _, due, n, need, free = worst
    return dict(due=clock.iso(due)[:16], tasks=n, need_h=round(need / 4, 1), free_h=round(free / 4, 1))


def overload(p) -> str | None:
    """The shortfall, in words."""
    s = shortfall(p)
    if s is None:
        return None
    when = datetime.fromisoformat(s["due"]).strftime("%a %-d %b %H:%M")
    return (f"More is due than fits: {s['tasks']} tasks due by {when} need {s['need_h']:.0f} h with Friday's margin, "
            f"and your rules and calendar leave {s['free_h']:.0f} h before then. Some work will be late; Friday keeps "
            f"it as little as it can.")


class Engine:
    def __init__(self, data_dir: str | Path | None = None, steps: int = 300_000, parser=None, rater=None):
        self.dir = Path(data_dir or os.environ.get("FRIDAY_ENGINE_DIR") or DEFAULT_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "engine.json"
        self.steps = steps
        self.parser = parser  # callable(text, context) -> fr.product.parse.Result; None = the Claude CLI
        self.rater = rater  # callable(titles) -> {key: {level, reason}}; None = events.rate (the Claude CLI)
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
        skipped = {(ev_key(x["title"]), x["start"][:16]) for x in self.s.get("skipped", [])}
        events = [e for e in events if (ev_key(e.get("title", "")), str(e.get("start", ""))[:16]) not in skipped]
        tasks = adapter.tasks_from(todos)
        pred = self.predict(todos, now)
        sc, ids = adapter.scenario(now, tasks, {k: v["plan_minutes"] for k, v in pred.items()}, events)
        sc, notes = C.apply(sc, self._constraints())
        u = Universe(sc)
        over = overload(u.p)
        self.s["shortfall"] = shortfall(u.p)  # for suggest_skips
        if over:
            notes = [over] + notes
        # every option starts from (and its deadline walls protect) the repaired zero-late start, not raw construction
        rep = ensure_deadlines(u.pr, seed=0, use_cpsat=len(u.p.items) <= 60, cpsat_s=2.0)
        if over:  # also from ordered starts (decision 39); keep the least late that breaks no rule
            for how in ("mdd", "edf"):
                start = edf_start(u.p, u.pr.c.keys, how)
                if not check(u.p, u.pr.c.plan_from_owner(start)):
                    late = late_value(u.pr, start)
                    if late < rep.late:
                        rep = replace(rep, owner=start, late=int(late))
        u.pr = replace(u.pr, owner=rep.owner)
        breaks = adapter.break_blocks(sc)
        L = self._learner()
        opts = three(u, L, method, steps=self.steps, seed=0)
        phis = [u.phi(x) for x in opts.plans]
        out = []
        for k, owner in enumerate(opts.plans):
            plan = u.c.plan_from_owner(owner)
            late = [ids.get(int(key.split(":")[1])) for key, it in u.p.items.items()
                    if it.due is not None and any(u.p.grid.end[s] > it.due for s in plan.get(key, ()) if s < u.p.grid.S)]
            # "doesn't fit": due within the planning window and not all of it scheduled; work due later, or never, isn't
            # a problem when it waits
            unplaced = [ids.get(int(key.split(":")[1])) for key, it in u.p.items.items()
                        if it.amount == "fixed" and it.due is not None and it.due <= u.p.grid.horizon_end
                        and sum(int(u.p.grid.units[s]) for s in plan.get(key, ())) < it.need]
            finish = {ids.get(int(key.split(":")[1])): max((int(u.p.grid.end[s]) for s in plan.get(key, ())
                                                             if s < u.p.grid.S), default=None)
                      for key, it in u.p.items.items() if it.due is not None}
            due_of = {ids.get(int(key.split(":")[1])): it.due for key, it in u.p.items.items() if it.due is not None}
            out.append(dict(option=k, label=opts.labels[k], summary=self._summary(phis[0], phis[k], L.theta) if k else
                            "Friday's recommendation", blocks=sorted(adapter.blocks(u.c, owner, ids) + breaks, key=lambda b: b["start"]),
                            late_tasks=[t for t in late if t], unplaced_tasks=[t for t in unplaced if t],
                            late_detail=[dict(task_id=t, due=clock.iso(due_of[t]),
                                              finish=clock.iso(finish[t]) if finish.get(t) else None,
                                              hours_late=round((finish[t] - due_of[t]) / 60, 1) if finish.get(t) else None)
                                         for t in dict.fromkeys([x for x in late + unplaced if x])],
                            valid=not check(u.p, plan)))
        # whenever an option runs late, skips are worth proposing until the late work is done: an event the day after a
        # missed deadline still holds back work that is late (decision 42)
        late = [d for o in out for d in o["late_detail"]]
        if late:
            short = self.s["shortfall"] or dict(due=max(d["due"] for d in late)[:16])
            ends = [d["finish"] or clock.iso(u.p.grid.horizon_end) for d in late]
            short["until"] = max(ends)[:16]
            self.s["shortfall"] = short
        pid = uuid.uuid4().hex[:12]
        self.s["plans"][pid] = dict(at=clock.iso(clock.to_minutes(now)), phis=[p.tolist() for p in phis])
        if len(self.s["plans"]) > 10:
            for old in sorted(self.s["plans"], key=lambda k: self.s["plans"][k]["at"])[:-10]:
                del self.s["plans"][old]
        self.save()
        return dict(plan_id=pid, options=out, notes=notes, minutes={k: v["plan_minutes"] for k, v in pred.items()})

    # ---------------------------------------------------------------- events you might skip
    def suggest_skips(self, events: list[dict], now: datetime, limit: int = 6) -> dict:
        """When the last plan ran late (more due than fits, or any task late), the events that matter least between now
        and when the late work is done, each with the time skipping it frees: {deadline, until, suggestions: [{title,
        start, end, level, reason, frees_minutes}], skipped: [{title, start}], kept: [titles]}. Claude rates new titles once; "keep" answers are never asked again."""
        kept = set(self.s.get("kept_events", []))
        named = {ev_key(t): t for t in self.s.get("kept_titles", [])}
        named.update({ev_key(e["title"]): e["title"] for e in events if ev_key(e["title"]) in kept})
        out = dict(deadline=None, suggestions=[], skipped=self.s.get("skipped", []),
                   kept=sorted(named.get(k, k) for k in kept))  # answers from before kept_titles: names from events
        short = self.s.get("shortfall")
        if not short:
            return out
        out["deadline"] = short["due"]
        until = short.get("until") or short["due"]
        out["until"] = until
        skipped = {(ev_key(x["title"]), x["start"][:16]) for x in self.s.get("skipped", [])}
        start_s = now.strftime("%Y-%m-%dT%H:%M")
        cands = [e for e in events if not e.get("isAllDay") and str(e["start"])[:16] >= start_s
                 and str(e["end"])[:16] <= until and ev_key(e["title"]) not in kept
                 and (ev_key(e["title"]), str(e["start"])[:16]) not in skipped]
        ratings = self.s.setdefault("event_ratings", {})
        new = sorted({e["title"] for e in cands if ev_key(e["title"]) not in ratings})
        if new:
            ratings.update((self.rater or rate_events)(new))
            self.save()
        after = {c.event_kind: c.before_min + c.after_min for c in self._constraints() if isinstance(c, C.Buffer)}
        rows = []
        for e in cands:
            r = ratings.get(ev_key(e["title"]), {"level": "likely", "reason": ""})
            if r["level"] == "required":
                continue
            kind = "class" if adapter.COURSE.search(e["title"]) else "other"
            mins = (datetime.fromisoformat(str(e["end"])[:16]) - datetime.fromisoformat(str(e["start"])[:16])).seconds / 60
            rows.append(dict(title=e["title"], start=str(e["start"])[:16], end=str(e["end"])[:16], level=r["level"],
                             reason=r["reason"], frees_minutes=round(mins + after.get(kind, 0))))
        rows.sort(key=lambda x: (x["level"] != "optional", -x["frees_minutes"], x["start"]))
        out["suggestions"] = rows[:limit]
        return out

    def decide_event(self, title: str, start: str, decision: str) -> dict:
        """skip: this occurrence stops blocking time in plans; unskip: undo; keep: never suggest this title again;
        unkeep: undo keep."""
        sk = self.s.setdefault("skipped", [])
        if decision == "skip":
            if not any(ev_key(x["title"]) == ev_key(title) and x["start"][:16] == start[:16] for x in sk):
                sk.append(dict(title=title, start=start[:16]))
        elif decision == "unskip":
            self.s["skipped"] = [x for x in sk if not (ev_key(x["title"]) == ev_key(title) and x["start"][:16] == start[:16])]
        elif decision == "keep":
            kept = self.s.setdefault("kept_events", [])
            if ev_key(title) not in kept:
                kept.append(ev_key(title))
                self.s.setdefault("kept_titles", []).append(title)
            self.s.setdefault("event_ratings", {})[ev_key(title)] = dict(level="required", reason="you go to these")
        elif decision == "unkeep":  # suggest it again: forget the answer, and Claude rates it afresh
            self.s["kept_events"] = [k for k in self.s.get("kept_events", []) if k != ev_key(title)]
            self.s["kept_titles"] = [t for t in self.s.get("kept_titles", []) if ev_key(t) != ev_key(title)]
            self.s.get("event_ratings", {}).pop(ev_key(title), None)
        else:
            raise ValueError(f"unknown decision {decision!r}")
        self.save()
        return dict(ok=True, skipped=len(self.s.get("skipped", [])))

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

