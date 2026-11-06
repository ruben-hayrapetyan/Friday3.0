"""The scheduler pipeline (DESIGN §11.6): construct → repair → fallback (ordered by size) → anneal.

Every plan it returns is valid; an item complete and on time in the start plan is never made late. The result is
evaluated independently before it is returned, and any disagreement with the kernel raises: that is a bug.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np

from friday.engine.checker import check
from friday.engine.compile import Compiled
from friday.engine.construct import construct, fewest_late_order, prepare_start
from friday.engine.cpsat_deadlines import DeadlineModel, FallbackResult
from friday.engine.evaluate import Evaluation, evaluate
from friday.engine.gaps import closed_gaps
from friday.engine.kernel import init_state, new_state, protected_items, total_violations
from friday.engine.problem import STAGES, Problem
from friday.engine.repair import deadline_value, repair
from friday.engine.sampler import ChainOutcome, SamplerConfig, anneal

CANCEL_POLL_S = 0.05


class EngineBug(RuntimeError):
    """The kernel and the evaluator disagree, or a returned plan breaks a wall."""


@dataclass(frozen=True)
class StepBudget:
    max_items: int
    cold: int
    warm: int


@dataclass(frozen=True)
class SchedulerConfig:
    sampler: SamplerConfig
    step_budgets: tuple[StepBudget, ...]
    warm_t0: float = 0.01
    repair_steps: int = 400_000
    fallback_threshold: int = 60
    fallback_s: float = 5.0
    fallback_overload_s: float = 15.0
    fallback_overload_warm_s: float = 5.0
    fallback_warm_s: float = 1.0
    fallback_workers: int = 8
    use_fallback: bool = True


@dataclass
class Schedule:
    plan: dict[str, tuple[int, ...]]
    owner: np.ndarray
    evaluation: Evaluation
    protected: list[str]
    demoted_locks: list[str]
    chains: int
    steps_per_chain: int
    fallback: str  # none | first | after (and whether it helped: cpsat-better, cpsat-same, timeout…)
    seconds: dict[str, float] = field(default_factory=dict)
    deadlines_after: dict[str, int] = field(default_factory=dict)  # the deadlines value after each step
    cancelled: bool = False

    @property
    def stage_values(self) -> dict[str, int]:
        return self.evaluation.stage_values


def step_budget(config: SchedulerConfig, n_items: int, warm: bool) -> int:
    for budget in config.step_budgets:
        if n_items <= budget.max_items:
            return budget.warm if warm else budget.cold
    last = config.step_budgets[-1]
    return last.warm if warm else last.cold


def items_late(c: Compiled, owner: np.ndarray) -> int:
    plan = c.plan_from_owner(owner)
    return len(evaluate(c.problem, plan).deadline_misses)


def schedule(
    problem: Problem,
    config: SchedulerConfig,
    warm: bool = False,
    cancel: np.ndarray | None = None,
    overloaded: bool = False,
    keep: bool = True,
) -> Schedule:
    """Plan `problem`. A warm replan starts from the items' current slots and anneals from a low temperature.

    `overloaded` is the executor's verdict that the hard deadlines can't all be met; it gives the fallback longer.
    `keep`: the plan you have stands unless the new one is better (not when you picked another way on purpose).
    """
    seconds: dict[str, float] = {}
    began = clock = time.perf_counter()
    cancel = np.zeros(1, dtype=np.int64) if cancel is None else cancel
    start = prepare_start(problem, current_owner(problem) if warm else None)
    c, owner = start.c, start.owner
    trace = {"construct": deadline_value(c, owner)}
    seconds["construct"], clock = time.perf_counter() - clock, time.perf_counter()
    owner = repair(c, owner, config.repair_steps, config.sampler.seed, config.sampler.move_weights, cancel)
    trace["repair"] = deadline_value(c, owner)
    if warm and trace["repair"] > 0 and (reordered := due_order(c, owner, config, cancel)) is not None:
        owner = reordered
        trace["due_order"] = deadline_value(c, owner)
    if deadline_value(c, owner) > 0 and (fed := meals_first(c, owner, config, cancel)) is not None:
        owner = fed
        trace["meals_first"] = deadline_value(c, owner)
    if not warm and trace["repair"] > 0:
        # personal's overload start (COMBINED.md 54): as many tasks on time as can be, kept only if it ends less late.
        other = construct(c, order=fewest_late_order(c))
        other = repair(c, other, config.repair_steps, config.sampler.seed, config.sampler.move_weights, cancel)
        if valid(c, other) and deadline_value(c, other) < trace["repair"]:
            owner = other
            trace["fewest_late"] = deadline_value(c, owner)
    seconds["repair"], clock = time.perf_counter() - clock, time.perf_counter()
    steps = step_budget(config, len(problem.items), warm)
    small = len(problem.items) <= config.fallback_threshold
    fallback = "none"
    if small and deadline_value(c, owner) > 0:
        owner, fallback = deadline_fallback(c, owner, config, cancel, "first", warm, overloaded)
        trace["fallback"] = deadline_value(c, owner)
    seconds["fallback"] = time.perf_counter() - clock
    clock = time.perf_counter()
    outcomes, protected = sample_from(c, owner, config, steps, warm, cancel)
    owner = outcomes[0].owner
    trace["anneal"] = deadline_value(c, owner)
    seconds["anneal"] = time.perf_counter() - clock
    if not small and deadline_value(c, owner) > 0:
        clock = time.perf_counter()
        candidate, fallback = deadline_fallback(c, owner, config, cancel, "after", warm, overloaded)
        trace["fallback"] = deadline_value(c, candidate)
        if deadline_value(c, candidate) < deadline_value(c, owner):
            warm_steps = step_budget(config, len(problem.items), True)
            outcomes, protected = sample_from(c, candidate, config, warm_steps, True, cancel)
            owner = outcomes[0].owner
        seconds["fallback"] += time.perf_counter() - clock
    if keep and (kept := better_kept(c, owner)) is not None:  # warm or the nightly cold one: yours stands
        owner, protected = kept, []
    owner = dated_first(c, owner, cancel)
    owner = closed_gaps(c, owner, cancel)
    result = verified(c, owner, protected, fallback, start.demoted, seconds, config, steps)
    result.cancelled = bool(cancel[0])
    result.deadlines_after = trace | {"final": result.stage_values["deadlines"]}
    seconds["total"] = time.perf_counter() - began
    return result


def due_order(c: Compiled, owner: np.ndarray, config: SchedulerConfig, cancel: np.ndarray) -> np.ndarray | None:
    """A warm plan with work late, its deadline work placed again by due: the hard items due by the last late one's due
    taken out and put back in `fewest_late_order` (earliest due first, as many on time as can be), the rest of the
    plan kept; returned only when it's less late. A warm start keeps where things were and the anneal moves a few
    slots at a time, so it couldn't trade two mornings: work due tonight kept the morning while work due at noon went
    19 hours late (CS 2091's pre-lab and CUAI's papers, 26 Oct). Locks stay where they are."""
    misses = set(evaluate(c.problem, c.plan_from_owner(owner)).deadline_misses)
    M, items = c.m, c.problem.items
    dues = [items[k].due_utc for k in misses if items[k].due_utc is not None]
    if not dues:
        return None
    latest = max(dues)
    index = {k: i for i, k in enumerate(c.keys)}
    moving = {
        k for k, item in items.items() if M.hard_due[index[k]] and item.due_utc is not None and item.due_utc <= latest
    }
    base = owner.copy()
    for s in range(M.S):
        if base[s] >= 0 and c.keys[base[s]] in moving and not M.locked[base[s], s]:
            base[s] = -1
    other = construct(c, base, only=moving, order=fewest_late_order(c))
    other = repair(c, other, config.repair_steps, config.sampler.seed, config.sampler.move_weights, cancel)
    if not valid(c, other) or deadline_value(c, other) >= deadline_value(c, owner):
        return None
    return other


def meals_first(c: Compiled, owner: np.ndarray, config: SchedulerConfig, cancel: np.ndarray) -> np.ndarray | None:
    """Meals a rule keeps from work (the deadlines stage) short of their minimum placed first: each in the free run
    nearest its own window (inside it first), what work sat there and in its travel taken out and placed again after;
    returned when it scores better. A plan with work where dinner could go couldn't trade the two a slot at a time, so
    lunch and dinner stayed off the plan."""
    M, problem = c.m, c.problem
    index = {k: i for i, k in enumerate(c.keys)}
    kept = [r for r in problem.rules if r.stage == "deadlines" and r.type == "elastic_shortfall"]
    meals = [
        k for k, item in problem.items.items() if item.meal_window is not None and any(r.applies(item) for r in kept)
    ]
    held = {k: int(sum(M.units[s] for s in range(M.S) if owner[s] == index[k])) for k in meals}
    short = [k for k in meals if held[k] < problem.items[k].min]
    if not short:
        return None
    base, moved = owner.copy(), set()

    def clear(s: int) -> bool:
        i = int(base[s])
        if i < 0:
            return True
        if M.locked[i, s] or problem.items[c.keys[i]].meal_window is not None:
            return False
        moved.add(c.keys[i])
        base[s] = -1
        return True

    for k in short:
        i, item = index[k], problem.items[k]
        lo, hi = item.meal_window  # type: ignore[misc]
        for s in range(M.S):
            if base[s] == i and not M.locked[i, s]:
                base[s] = -1
        starts = sorted(
            item.allowed, key=lambda s: (max(0, lo - int(c.problem.grid.start[s]), int(c.problem.grid.end[s]) - hi), s)
        )
        for start in starts:
            run, units = [], 0
            for s in range(start, M.S):
                if s not in item.allowed_set or (base[s] >= 0 and not can_clear(problem, c, base, s)):
                    break
                run.append(s)
                units += int(M.units[s])
                if units >= item.min:
                    break
            if units < item.min:
                continue
            travel = [
                *range(max(0, run[0] - item.travel_before), run[0]),
                *range(run[-1] + 1, min(M.S, run[-1] + 1 + item.travel_after)),
            ]
            for s in run + [t for t in travel if not problem.blocked[t]]:
                clear(s)
            for s in run:
                base[s] = i
            break
    for s in range(M.S):
        if base[s] >= 0 and c.keys[base[s]] in moved and not M.locked[base[s], s]:
            base[s] = -1
    other = construct(c, base, only=moved, order=fewest_late_order(c))
    other = repair(c, other, config.repair_steps, config.sampler.seed, config.sampler.move_weights, cancel)
    if not valid(c, other) or stage_values(c, other) >= stage_values(c, owner):
        return None
    return other


def can_clear(problem: Problem, c: Compiled, base: np.ndarray, s: int) -> bool:
    """Whether the work in slot s may make way for a meal: not locked there, and not a meal itself."""
    i = int(base[s])
    return not c.m.locked[i, s] and problem.items[c.keys[i]].meal_window is None


def valid(c: Compiled, owner: np.ndarray) -> bool:
    """No wall broken (the repair's 1e9 penalties can leave one when nothing better was found)."""
    st = new_state(c.m)
    init_state(c.m, st, owner)
    return int(total_violations(c.m, st)) == 0


def stage_values(c: Compiled, owner: np.ndarray) -> tuple[int, ...]:
    st = new_state(c.m)
    init_state(c.m, st, owner)
    return tuple(int(v) for v in st.stage_value)


def better_kept(c: Compiled, owner: np.ndarray) -> np.ndarray | None:
    """The plan you have, scored now (kept where it still may be, nothing added), when the new one isn't better.
    A warm start adds back what the plan left out (a meal with no room, say) and anneals from there, so with nothing
    changed it could end elsewhere, even somewhere worse, and every tick moved blocks; now a replan moves the plan
    only for one that is better, deadlines first, then wellbeing, then preferences (where moving costs). The nightly
    cold plan too: it searches afresh, but replaces yours only when what it finds is better, so the morning's first
    replan doesn't reshuffle a third of the week from a fresh plan that wasn't."""
    have = {k: tuple(item.current) for k, item in c.problem.items.items() if item.current}
    if not have:
        return None
    kept = construct(c, c.owner_from_plan(have), only=set())
    if not valid(c, kept) or check(c.problem, c.plan_from_owner(kept)):
        return None
    return kept if stage_values(c, kept) <= stage_values(c, owner) and (kept != owner).any() else None


def dated_first(c: Compiled, owner: np.ndarray, cancel: np.ndarray | None = None) -> np.ndarray:
    """Time the plan gave undated work, given instead to work due inside the horizon that has too little, wherever the
    plan is better for it in the stages' order and no wall breaks (29 Oct: "why is friday scheduling 'Email professors
    for research opportunities' that doesn't have a deadline over something that has one but that hasn't been
    scheduled"). The annealer moves and fills work but never takes one item's time for another it left out, so a
    reading due Sunday sat unplanned beside an evening given to an undated task, though the swap was cheaper by every
    count. Pinned, locked and timed time stays its own."""
    problem, grid = c.problem, c.problem.grid
    items = list(problem.items.values())
    units = grid.units
    has = lambda i: int(units[np.flatnonzero(owner == i)].sum())  # noqa: E731
    due = [i for i, it in enumerate(items) if it.amount == "fixed" and it.due_utc is not None]
    short = sorted((i for i in due if items[i].due_utc <= grid.horizon_end and has(i) < items[i].need),
                   key=lambda i: items[i].due_utc)  # fmt: skip
    if not short:
        return owner
    best = stage_values(c, owner)
    for u, item in enumerate(items):
        if item.due_utc is not None:
            continue
        kept = set(item.locked) | set(item.preferred) | set(item.held)
        for d in short:
            if cancel is not None and cancel[0]:
                return owner
            slots = [int(s) for s in np.flatnonzero(owner == u) if s not in kept and c.m.allowed[d, s]]
            missing = items[d].need - has(d)
            take, got = [], 0
            for s in slots:
                if got >= missing:
                    break
                take.append(s)
                got += int(units[s])
            if not take:
                continue
            trial = owner.copy()
            trial[take] = d
            if not valid(c, trial):
                continue
            values = stage_values(c, trial)
            if values < best:
                owner, best = trial, values
    return owner


def current_owner(problem: Problem) -> np.ndarray | None:
    if not any(item.current for item in problem.items.values()):
        return None
    owner = np.full(problem.grid.S, -1, dtype=np.int16)
    for i, item in enumerate(problem.items.values()):
        for s in item.current:
            owner[s] = i
    return owner


def sample_from(
    c: Compiled, owner: np.ndarray, config: SchedulerConfig, steps: int, warm: bool, cancel: np.ndarray
) -> tuple[list[ChainOutcome], list[str]]:
    """Anneal with W9 protecting every item that is complete and on time where annealing starts."""
    protected = protected_items(c.m, owner)
    outcomes = anneal(c, owner, protected, config.sampler, steps, warm, config.warm_t0, cancel)
    return outcomes, [c.keys[i] for i in np.flatnonzero(protected)]


def deadline_fallback(
    c: Compiled,
    owner: np.ndarray,
    config: SchedulerConfig,
    cancel: np.ndarray,
    when: str,
    warm: bool,
    overloaded: bool = False,
) -> tuple[np.ndarray, str]:
    """CP-SAT on the deadlines stage, hinted with `owner`; only a valid, less late plan replaces it."""
    if not config.use_fallback or cancel[0]:
        return owner, "none"
    overloaded = overloaded or items_late(c, owner) > 2
    # A warm start keeps the previous plan, which already had its full fallback; a short one finds what changed.
    if overloaded:
        seconds = config.fallback_overload_warm_s if warm else config.fallback_overload_s
    else:
        seconds = config.fallback_warm_s if warm else config.fallback_s
    results = deadline_portfolio(c, owner, seconds, config, cancel)
    found = [r for r in results if r.plan is not None and not check(c.problem, r.plan)]
    if not found:
        return owner, f"{when}:cpsat-{results[0].status.lower()}"
    candidate = min((c.owner_from_plan(r.plan) for r in found), key=lambda o: deadline_value(c, o))
    if deadline_value(c, candidate) < deadline_value(c, owner):
        return candidate, f"{when}:cpsat-better"
    return owner, f"{when}:cpsat-same"


def deadline_portfolio(
    c: Compiled, owner: np.ndarray, seconds: float, config: SchedulerConfig, cancel: np.ndarray
) -> list[FallbackResult]:
    """Two CP-SAT solves side by side, one hinted with the plan so far and one free, sharing the workers.

    A hint can hold the search near a poor plan, and no hint can leave it far from a good one; which wins
    varies by instance, so both run and the less late result is kept. A set cancel flag stops both.
    """
    workers = max(1, config.fallback_workers // 2)
    models = [DeadlineModel(c.problem), DeadlineModel(c.problem)]
    hints = [c.plan_from_owner(owner), None]
    finished = threading.Event()

    def stop_on_cancel() -> None:
        while not finished.wait(CANCEL_POLL_S):
            if cancel[0]:
                for model in models:
                    model.stop()
                return

    watcher = threading.Thread(target=stop_on_cancel, daemon=True)
    watcher.start()
    try:
        with ThreadPoolExecutor(2) as pool:
            solves = pool.map(lambda pair: pair[0].solve(pair[1], seconds, workers, config.sampler.seed),
                              zip(models, hints, strict=True))  # fmt: skip
            return list(solves)
    finally:
        finished.set()


def verified(
    c: Compiled,
    owner: np.ndarray,
    protected: list[str],
    fallback: str,
    demoted: list[str],
    seconds: dict[str, float],
    config: SchedulerConfig,
    steps: int,
) -> Schedule:
    plan = c.plan_from_owner(owner)
    evaluation = evaluate(c.problem, plan)
    st = new_state(c.m)
    init_state(c.m, st, owner)
    kernel_values = [int(v) for v in st.stage_value]
    if kernel_values != [evaluation.stage_values[s] for s in STAGES]:
        raise EngineBug(f"kernel {kernel_values} != evaluator {evaluation.stage_values}")
    violations = check(c.problem, plan, protected)
    if violations:
        raise EngineBug(f"the plan breaks walls: {[str(v) for v in violations[:5]]}")
    return Schedule(plan, owner, evaluation, protected, demoted, config.sampler.chains, steps, fallback, seconds)
