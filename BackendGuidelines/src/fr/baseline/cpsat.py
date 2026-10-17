"""v2 baseline: the staged CP-SAT grid model (ENGINE_REFERENCE 6A).

Variables x, over, start, cum and any; constraints C1-C8; one objective per stage built from the same price
rows and `Measure`s the evaluator uses, so stage objectives can be recomputed from the plan. After each
stage the stage value is frozen (plus `stage_slack`) and the next stage optimises on top of it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from ..core.context import BuildContext
from ..core.evaluate import Evaluation, check, evaluate, lag_slot
from ..core.problem import EngineItem, Problem
from ..core.pwl import Lin, Measure, hinge_coeff
from ..core.rules import price_row
from ..core.settings import STAGES


class SolveTimeout(RuntimeError):
    pass


class ModelInfeasible(RuntimeError):
    """The hard constraints contradict each other; with overflow this can only come from locks."""


@dataclass
class StageResult:
    stage: str
    status: str
    cp_objective: int | None
    true_value: int  # recomputed by the shared evaluator from the plan
    bound: float | None
    wall_s: float
    det_time: float
    trace: list[tuple[float, int]] = field(default_factory=list)  # (seconds since solve start, objective)


@dataclass
class SolveResult:
    plan: dict[str, tuple[int, ...]]
    evaluation: Evaluation
    stages: list[StageResult]
    build_s: float
    total_s: float
    demoted_locks: list[str] = field(default_factory=list)  # items whose locks were relaxed to preferred pins

    @property
    def stage_values(self) -> dict[str, int]:
        return self.evaluation.stage_values


class _Trace(cp_model.CpSolverSolutionCallback):
    def __init__(self, t0: float):
        super().__init__()
        self.t0 = t0
        self.points: list[tuple[float, int]] = []

    def on_solution_callback(self) -> None:
        self.points.append((time.perf_counter() - self.t0, int(self.ObjectiveValue())))


class GridModel:
    """Builds the model once; `solve` runs the stages."""

    def __init__(self, problem: Problem, assume_locks: bool = False):
        t0 = time.perf_counter()
        self.assume_locks = assume_locks
        self.lock_lits: dict[str, cp_model.IntVar] = {}
        self.p = problem
        self.g = problem.grid
        self.m = cp_model.CpModel()
        self.x: dict[tuple[str, int], cp_model.IntVar] = {}
        self.over: dict[str, cp_model.IntVar] = {}
        self.start: dict[tuple[str, int], cp_model.IntVar] = {}
        self.cum: dict[tuple[str, int], cp_model.IntVar] = {}
        self.anyv: dict[str, cp_model.IntVar] = {}
        self.stage_terms: dict[str, list] = {s: [] for s in STAGES}
        self.rule_terms: dict[str, list] = {}
        self._build()
        self.build_s = time.perf_counter() - t0

    # ------------------------------------------------------------ variables and hard constraints

    def _build(self) -> None:
        p, g, m = self.p, self.g, self.m
        for it in p.items.values():
            for s in it.allowed:
                self.x[it.key, s] = m.NewBoolVar(f"x_{it.key}_{s}")
            if it.locked and self.assume_locks:
                lit = self.lock_lits[it.key] = m.NewBoolVar(f"lock_{it.key}")
            for s in it.locked:  # C4
                if self.assume_locks:
                    m.Add(self.x[it.key, s] == 1).OnlyEnforceIf(self.lock_lits[it.key])
                else:
                    m.Add(self.x[it.key, s] == 1)
            if it.amount == "fixed":
                self.over[it.key] = m.NewIntVar(0, it.need, f"over_{it.key}")

        # C1 one thing at a time
        by_slot: dict[int, list] = {}
        for (k, s), v in self.x.items():
            by_slot.setdefault(s, []).append(v)
        for vs in by_slot.values():
            if len(vs) > 1:
                m.AddAtMostOne(vs)

        # C5 daily cap
        day_terms: dict[int, list] = {}
        for (k, s), v in self.x.items():
            day_terms.setdefault(g.slots[s].day, []).append(int(g.units[s]) * v)
        for d, terms in day_terms.items():
            m.Add(sum(terms) <= p.day_caps[d])

        ctx = BuildContext(p)
        self.measures = [(rule, list(rule.measures(ctx))) for rule in p.rules]  # also records start/any requests
        self._amounts()
        self._chunks(ctx)
        self._dependencies()
        self._objectives(ctx)
        if self.assume_locks:
            m.AddAssumptions(list(self.lock_lits.values()))

    def lock_core(self) -> list[str]:
        """Items whose locks together make the model infeasible (empty if it is feasible)."""
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.max_time_in_seconds = 30
        if solver.Solve(self.m) != cp_model.INFEASIBLE:
            return []
        idx = set(solver.SufficientAssumptionsForInfeasibility())
        return [k for k, lit in self.lock_lits.items() if lit.Index() in idx]

    def _placed(self, it: EngineItem, slots=None):
        slots = it.allowed if slots is None else slots
        return sum(int(self.g.units[s]) * self.x[it.key, s] for s in slots if (it.key, s) in self.x)

    def _amounts(self) -> None:
        m, g = self.m, self.g
        for it in self.p.items.values():
            placed = self._placed(it)
            if it.amount == "fixed":
                over = self.over[it.key]
                m.Add(placed + over >= it.need)  # C2
                # The reference allows need + 1 so a 30-minute slot can hold a 15-minute remainder. On
                # fine slots that extra unit is free, which makes replans churn between equal-cost plans,
                # so it is allowed only when a coarse slot is actually used (deviation, see RESEARCH_LOG).
                coarse = [self.x[it.key, s] for s in it.allowed if g.units[s] > 1]
                if coarse:
                    lee = m.NewBoolVar(f"lee_{it.key}")
                    m.Add(lee <= sum(coarse))
                    m.Add(placed <= it.need + lee)
                else:
                    m.Add(placed <= it.need)
                if it.shape == "one_sitting":  # C6: over in {0, need}, and never partly placed
                    b = m.NewBoolVar(f"gone_{it.key}")
                    m.Add(over == it.need * b)
                    m.Add(placed <= (it.need + 1) * (1 - b))
            elif it.amount == "elastic":
                m.Add(placed <= it.max)
            elif it.amount == "target":
                m.Add(placed <= it.cap)
            else:
                for d in range(g.n_days):
                    ceil = it.daily_ceiling - (it.progress_today if d == 0 else 0)
                    slots = [s for s in g.day_slots[d] if s in it.allowed_set]
                    if slots:
                        m.Add(self._placed(it, slots) <= max(0, ceil))

    def _needs_starts(self, it: EngineItem, ctx_requested: set[str]) -> bool:
        return it.shape == "one_sitting" or it.min_chunk > 1 or it.key in ctx_requested

    def _chunks(self, ctx: BuildContext) -> None:
        """C3 start definitions, C6 one sitting, C7 minimum chunk, maximum chunk."""
        m, g = self.m, self.g
        wanted = ctx.starts_requested  # items a rule (chunk_cost) wants start variables for
        for it in self.p.items.values():
            if self._needs_starts(it, wanted):
                for s in it.allowed:
                    st = self.start[it.key, s] = m.NewBoolVar(f"st_{it.key}_{s}")
                    xs = self.x[it.key, s]
                    prev = self.x.get((it.key, s - 1)) if s > 0 else None
                    m.Add(st <= xs)
                    if prev is None:
                        m.Add(st == xs)
                    else:
                        m.Add(st >= xs - prev)
                        m.Add(st <= 1 - prev)
                if it.shape == "one_sitting":
                    m.Add(sum(self.start[it.key, s] for s in it.allowed) <= 1)
                if it.min_chunk > 1:  # C7
                    for s in it.allowed:
                        units, j = 0, s
                        run = []
                        while units < it.min_chunk and j < g.S and (it.key, j) in self.x:
                            units += int(g.units[j])
                            run.append(j)
                            j += 1
                        if units < it.min_chunk:
                            m.Add(self.start[it.key, s] == 0)
                        else:
                            for j in run[1:]:
                                m.Add(self.x[it.key, j] >= self.start[it.key, s])
            if it.max_chunk is not None:
                for a in range(g.S):
                    units, b = 0, a
                    while b < g.S and units < it.max_chunk + 1:
                        units += int(g.units[b])
                        b += 1
                    if units < it.max_chunk + 1:
                        break
                    slots = [s for s in range(a, b) if (it.key, s) in self.x]
                    if sum(int(g.units[s]) for s in slots) >= it.max_chunk + 1:
                        m.Add(self._placed(it, slots) <= it.max_chunk)

    def _dependencies(self) -> None:
        """C8: (N_A - P_A) x[B,s] <= cum[A, slot containing start(s) - lag]."""
        m, g = self.m, self.g
        for it in self.p.items.values():
            for dep in it.depends_on:
                need = dep.required
                if need == 0 or dep.key not in self.p.items:
                    continue
                other = self.p.items[dep.key]
                self._ensure_cum(other)
                for s in it.allowed:
                    if s in it.locked:
                        continue  # a lock overrides ordering (contradiction not covered by reference 8.1)
                    t = lag_slot(self.p, s, dep.lag_min)
                    if t <= 0:
                        m.Add(self.x[it.key, s] == 0)
                    else:
                        m.Add(need * self.x[it.key, s] <= self.cum[other.key, t])

    def _ensure_cum(self, it: EngineItem) -> None:
        if (it.key, 1) in self.cum:
            return
        m, g = self.m, self.g
        top = max(it.total_units, it.need) + 1
        prev = None
        for t in range(1, g.S + 1):
            v = self.cum[it.key, t] = m.NewIntVar(0, top, f"cum_{it.key}_{t}")
            step = int(g.units[t - 1]) * self.x[it.key, t - 1] if (it.key, t - 1) in self.x else 0
            m.Add(v == (prev if prev is not None else 0) + step)
            prev = v

    # ------------------------------------------------------------ objectives

    def _var(self, key):
        kind = key[0]
        if kind == "x":
            return self.x[key[1], key[2]]
        if kind == "over":
            return self.over[key[1]]
        if kind == "start":
            return self.start[key[1], key[2]]
        if kind == "cum":
            self._ensure_cum(self.p.items[key[1]])
            return self.cum[key[1], key[2]]
        if kind == "any":
            return self.anyv[key[1]]
        raise KeyError(key)

    def _bounds(self, key):
        kind = key[0]
        if kind == "over":
            return 0, self.p.items[key[1]].need
        if kind == "cum":
            it = self.p.items[key[1]]
            return 0, max(it.total_units, it.need) + 1
        return 0, 1

    def _expr(self, lin: Lin):
        return sum(c * self._var(v) for v, c in lin.terms.items()) + lin.const

    def _objectives(self, ctx: BuildContext) -> None:  # noqa: D401
        p, m, g, scale = self.p, self.m, self.g, self.p.settings.scale
        for rule, measures in self.measures:
            terms: list = []
            if rule.has_price:
                for it in p.items.values():
                    if not rule.applies(it):
                        continue
                    row = price_row(p, rule, it)
                    for s in it.allowed:
                        if row[s]:
                            terms.append(int(row[s]) * self.x[it.key, s])
                    if it.amount == "fixed" and row[g.S]:
                        terms.append(int(row[g.S]) * self.over[it.key])
            for ms in measures:
                for name, pairs in ctx.any_defs.items():
                    if name not in self.anyv:
                        a = self.anyv[name] = m.NewBoolVar(f"any_{name}")
                        xs = [self.x[k, s] for k, s in pairs]
                        for xv in xs:
                            m.Add(a >= xv)
                        m.Add(a <= sum(xs))
                g_expr = self._expr(ms.expr)
                lo, hi = ms.expr.bounds(self._bounds)
                for h in ms.curve:
                    coeff = hinge_coeff(rule.weight, ms.mult, h.slope, ms.unit, scale, f"{rule.name}/{ms.name}")
                    if coeff == 0:
                        continue
                    th = h.whole_theta
                    top = max(0, hi - th) if h.direction == "above" else max(0, th - lo)
                    if top == 0:
                        continue
                    z = m.NewIntVar(0, top, f"z_{rule.name}_{ms.name}")
                    m.Add(z >= (g_expr - th if h.direction == "above" else th - g_expr))
                    terms.append(coeff * z)
            self.rule_terms.setdefault(rule.name, []).extend(terms)
            self.stage_terms[rule.stage].extend(terms)

    # ------------------------------------------------------------ solving

    def _hint(self, plan) -> None:
        self.m.ClearHints()
        chosen = {(k, s) for k, sl in plan.items() for s in sl}
        for (k, s), v in self.x.items():
            self.m.AddHint(v, int((k, s) in chosen))

    def _plan(self, solver) -> dict[str, tuple[int, ...]]:
        out: dict[str, list[int]] = {k: [] for k in self.p.items}
        for (k, s), v in self.x.items():
            if solver.Value(v):
                out[k].append(s)
        return {k: tuple(sorted(v)) for k, v in out.items()}

    def solve(self, hint=None, stages=None, time_limit_s: float | None = None, workers: int | None = None,
              trace: bool = False, seed: int = 0) -> SolveResult:
        st = self.p.settings
        stages = list(stages or st.stages)
        workers = st.workers if workers is None else workers
        total_limit = st.time_limit_s if time_limit_s is None else time_limit_s
        t_start = time.perf_counter()
        if hint is None:  # the locks-only plan: overflow absorbs everything else, so it is always a valid start
            hint = {k: tuple(sorted(it.locked)) for k, it in self.p.items.items()}
        plan = hint
        self._hint(hint)
        results: list[StageResult] = []
        for k in stages:
            idx = STAGES.index(k)
            self.m.Minimize(sum(self.stage_terms[k]))
            res, plan = self._solve_stage(k, idx, total_limit, workers, trace, seed, t_start)
            results.append(res)
            ev = evaluate(self.p, plan)
            res.true_value = ev.stage_values[k]
            # freeze: Obj_k <= v_k + slack (v_k is the evaluator's exact value of this plan)
            bound = ev.stage_values[k] + round(st.stage_slack[idx] * st.scale)
            self.m.Add(sum(self.stage_terms[k]) <= bound)
            self._hint(plan)
        evaluation = evaluate(self.p, plan)
        return SolveResult(plan, evaluation, results, self.build_s, time.perf_counter() - t_start)

    def _solve_stage(self, name, idx, total_limit, workers, trace, seed, t_start):
        st = self.p.settings
        for attempt in (1, 2):
            solver = cp_model.CpSolver()
            solver.parameters.num_workers = workers
            solver.parameters.random_seed = seed
            solver.parameters.max_deterministic_time = st.det_time[idx] * attempt
            solver.parameters.max_time_in_seconds = max(1.0, total_limit * st.time_share[idx]) * attempt
            if workers == 1:
                solver.parameters.linearization_level = 2
            cb = _Trace(t_start) if trace else None
            t0 = time.perf_counter()
            status = solver.Solve(self.m, cb) if cb else solver.Solve(self.m)
            wall = time.perf_counter() - t0
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                res = StageResult(name, solver.StatusName(status), int(solver.ObjectiveValue()), 0,
                                  float(solver.BestObjectiveBound()), wall, solver.UserTime(),
                                  cb.points if cb else [])
                return res, self._plan(solver)
            if status == cp_model.INFEASIBLE:
                raise ModelInfeasible(f"stage {name} reported INFEASIBLE")
        raise SolveTimeout(f"stage {name}: no solution within doubled limits")


def demote_locks(problem: Problem, keys: list[str]) -> None:
    """Turn the locks of `keys` into preferred pins and reopen their slots to other items."""
    from ..core.builder import prune

    for k in keys:
        it = problem.items[k]
        it.preferred = frozenset(it.preferred | it.locked)
        it.locked = frozenset()
    problem.lock_owner = {s: it.key for it in problem.items.values() for s in it.locked}
    problem._price_cache.clear()
    prune(problem)


def solve(problem: Problem, hint=None, max_repairs: int = 8, **kw) -> SolveResult:
    """Solve; if locks contradict the other hard rules, relax the smallest core of them and retry."""
    demoted: list[str] = []
    for _ in range(max_repairs + 1):
        try:
            res = GridModel(problem).solve(hint=hint, **kw)
            res.demoted_locks = demoted
            return res
        except ModelInfeasible:
            core = GridModel(problem, assume_locks=True).lock_core()
            if not core:
                raise
            demote_locks(problem, core)
            demoted += core
    raise ModelInfeasible("locks still contradictory after repairs")
