"""Explanations (DESIGN §16): exact per-block costs and "why not there" by relocation.

Every number here can be recomputed from a plan: block costs sum to the evaluator's rule totals, and a
relocation's difference equals the evaluator's difference between the two plans.
"""

from dataclasses import dataclass, field

import numpy as np

from friday.engine.checker import check
from friday.engine.compile import Compiled
from friday.engine.kernel import init_state, new_state, protected_items, rule_totals
from friday.engine.moves import add_dependents, chunk_around, relocate
from friday.engine.problem import Plan, Problem, Solution
from friday.engine.pwl import Measure, measure_cost
from friday.engine.rules import BuildContext, price_row

OTHER = "other"  # cost that touches no block: overflow, and shortfalls of work that isn't placed


@dataclass(frozen=True)
class Block:
    key: str
    slots: tuple[int, ...]


def blocks_of(plan: Plan, cut_at: dict[str, set[int]] | None = None) -> list[Block]:
    """Runs of consecutive slots per item; `cut_at` names slots where a new block must start (pin edges)."""
    out = []
    for key, slots in plan.items():
        run: list[int] = []
        for s in sorted(slots):
            if run and (s != run[-1] + 1 or (cut_at and s in cut_at.get(key, set()))):
                out.append(Block(key, tuple(run)))
                run = []
            run.append(s)
        if run:
            out.append(Block(key, tuple(run)))
    return out


def per_rule(c: Compiled, owner: np.ndarray) -> dict[str, int]:
    M = c.m
    out = np.zeros(M.R, dtype=np.int64)
    work = (np.zeros(M.M, dtype=np.int64), np.zeros(max(M.G, 1), dtype=np.int64), np.zeros(M.I, dtype=np.int64))
    rule_totals(M, owner, out, *work)
    return {name: int(out[r]) for r, name in enumerate(c.rule_names)}


def block_costs(problem: Problem, plan: Plan, blocks: list[Block]) -> tuple[list[dict[str, int]], dict[str, int]]:
    """Each block's cost by rule, and the cost that falls on no block, by rule.

    Prices go to the block holding the slot. A measure's cost is split evenly among the blocks whose slots its
    expression reads, the remainder to the earliest ones, so the parts add up to the rule total exactly.
    """
    ctx = BuildContext(problem)
    solution = Solution(problem, plan, ctx.any_groups)
    at = {(b.key, s): n for n, b in enumerate(blocks) for s in b.slots}
    per_block: list[dict[str, int]] = [{} for _ in blocks]
    other: dict[str, int] = {}
    for rule in problem.rules:
        if rule.has_price:
            add_prices(problem, rule, solution, at, per_block, other)
        for m in rule.measures(ctx):
            cost = measure_cost(m, m.expr.eval(solution.value), rule.effective_weight, problem.scale, rule.name)
            if cost:
                share_out(rule.name, cost, sorted(touched_blocks(m, at, ctx)), per_block, other)
    return per_block, other


def add_prices(problem: Problem, rule, solution: Solution, at: dict, per_block: list, other: dict) -> None:  # noqa: ANN001
    for item in problem.items.values():
        if not rule.applies(item):
            continue
        row = price_row(problem, rule, item)
        for s in solution.slots[item.key]:
            if row[s]:
                n = at[(item.key, s)]
                per_block[n][rule.name] = per_block[n].get(rule.name, 0) + int(row[s])
        over = solution.over(item.key) if item.amount == "fixed" else 0
        if over and row[problem.grid.S]:
            other[rule.name] = other.get(rule.name, 0) + int(row[problem.grid.S]) * over


def touched_blocks(m: Measure, at: dict[tuple[str, int], int], ctx: BuildContext) -> set[int]:
    out = set()
    for var in m.expr.terms:
        if var[0] in ("x", "start") and (var[1], var[2]) in at:
            out.add(at[(var[1], var[2])])
        elif var[0] == "any":
            out |= {at[pair] for pair in ctx.any_groups[var[1]] if pair in at}
    return out


def share_out(rule: str, cost: int, blocks: list[int], per_block: list[dict[str, int]], other: dict[str, int]) -> None:
    if not blocks:
        other[rule] = other.get(rule, 0) + cost
        return
    each, extra = divmod(cost, len(blocks))
    for k, n in enumerate(blocks):
        per_block[n][rule] = per_block[n].get(rule, 0) + each + (1 if k < extra else 0)


@dataclass
class WhyNot:
    valid: bool
    walls: list[str] = field(default_factory=list)  # why the alternative was never an option
    delta: dict[str, int] = field(default_factory=dict)  # per rule: alternative − plan (> 0: costs more)
    start: int | None = None  # where the block was tried

    @property
    def total(self) -> int:
        return sum(self.delta.values())

    def reasons(self, k: int = 3) -> list[tuple[str, int]]:
        return sorted(((name, d) for name, d in self.delta.items() if d), key=lambda x: -abs(x[1]))[:k]


def why_not(c: Compiled, owner: np.ndarray, slot: int, new_start: int | None = None) -> WhyNot:
    """Move the chunk holding `slot` to `new_start`, or to its cheapest other valid place, in a scratch copy."""
    if new_start is not None:
        return relocation(c, owner, slot, new_start)
    i = int(owner[slot])
    st = new_state(c.m)
    init_state(c.m, st, owner)
    here, _ = chunk_around(c.m, st, slot)
    tries = [relocation(c, owner, slot, t) for t in range(c.m.first_slot[i], c.m.last_slot[i] + 1) if t != here]
    valid = [t for t in tries if t.valid and t.start is not None]
    return min(valid, key=lambda t: (t.total, t.start)) if valid else WhyNot(False, ["No other place fits"])


def relocation(c: Compiled, owner: np.ndarray, slot: int, new_start: int) -> WhyNot:
    M = c.m
    st = new_state(M)
    init_state(M, st, owner)
    i = int(owner[slot])
    a, b = chunk_around(M, st, slot)
    protected = protected_items(M, owner)
    touched = np.zeros(64, dtype=np.int64)
    st.counters[0] = 0
    if new_start == a:
        return WhyNot(True, [], {}, new_start)
    if not relocate(M, st, protected, i, a, b, new_start, touched):
        return WhyNot(False, blocked_reasons(c, owner, i, a, b, new_start), {}, new_start)
    add_dependents(M, touched, 1)
    moved = c.plan_from_owner(st.owner)
    protected_keys = [c.keys[k] for k in np.flatnonzero(protected)]
    walls = [wall_reason(c, v) for v in check(c.problem, moved, protected_keys)]
    before, after = per_rule(c, owner), per_rule(c, st.owner)
    delta = {name: after[name] - before[name] for name in before}
    return WhyNot(not walls, sorted(set(walls)), delta, new_start)


def blocked_reasons(c: Compiled, owner: np.ndarray, i: int, a: int, b: int, new_start: int) -> list[str]:
    """Why the block's units can't go at new_start: the first slot that refuses it, in words."""
    problem, M = c.problem, c.m
    item = problem.items[c.keys[i]]
    units, t = int(M.units[a : b + 1].sum()), new_start
    while units > 0:
        if t < 0 or t >= M.S:
            return ["Outside the planning horizon"]
        if not M.allowed[i, t]:
            return [slot_reason(c, i, t)]
        other = int(owner[t])
        if other >= 0 and other != i and not a <= t <= b:
            other_item = problem.items[c.keys[other]]
            return [f"Locked: {other_item.title}" if M.locked[other, t] else f"Taken by {other_item.title}"]
        if protected_items(M, owner)[i] and not M.on_time[i, t]:
            return ["Past its due"]
        units -= int(M.units[t])
        t += 1
    return [f"Doesn't fit the {item.title} block there"]


def slot_reason(c: Compiled, i: int, s: int) -> str:
    problem = c.problem
    item, grid = problem.items[c.keys[i]], problem.grid
    start = int(grid.start[s])
    if item.release_utc is not None and start < item.release_utc:
        return "Before its release"
    if item.window_is_hard and item.due_utc is not None and start >= item.due_utc:
        return "Past its due"
    if item.cutoff_utc is not None and start >= item.cutoff_utc:
        return "Past the last day it can be done late"
    if problem.core[s]:
        return "Sleep"
    if problem.blocked[s]:
        busy = [f for f in problem.fixed if f.blocks_time and f.blocked_lo < grid.end[s] and f.blocked_hi > start]
        return f"Busy: {busy[0].title}" if busy else "Busy"
    owner_key = problem.lock_owner.get(s)
    if owner_key is not None:
        return f"Locked: {problem.items[owner_key].title}"
    for rule in problem.rules:
        if rule.has_forbid and rule.applies(item) and rule.forbids(item, s):
            return rule.reason
    return "Not allowed there"


def wall_reason(c: Compiled, violation) -> str:  # noqa: ANN001
    problem = c.problem
    words = {
        "W4": "More than its amount",
        "W5": "Over the daily cap",
        "W6": "It must be done in one sitting",
        "W7": "The chunk would be too short or too long",
        "W9": "Past its due",
    }
    if violation.wall == "W8":
        item = problem.items.get(violation.key)
        sources = [problem.items[d.key].title for d in item.depends_on if d.key in problem.items] if item else []
        return f"Waits for {sources[0]}" if sources else "Waits for another item"
    return words.get(violation.wall, violation.wall)
