"""Problem + rules → the flat arrays the kernel runs on (DESIGN §11.5).

Everything comes from the same sources the evaluator uses (`price_row`, `rule.measures`, the checker's walls),
so the compiled energy equals `evaluate()` to the integer. The kernel exactness tests prove it.

A measure's value is a linear function of: x(item, slot) × units, start(item, slot), over(item) and
any(group). The kernel keeps every value up to date as slots change owner.
"""

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from friday.engine.checker import lag_slot
from friday.engine.problem import STAGES, Plan, Problem
from friday.engine.pwl import hinge_coefficient
from friday.engine.rules import BuildContext, price_row

AMOUNT_KIND = {"fixed": 0, "elastic": 1, "target": 2, "open": 3}
NO_LIMIT = 10**6


class Model(NamedTuple):
    I: int  # items
    S: int  # slots; index S is the overflow slot
    D: int  # planning days
    M: int  # measures
    G: int  # any-of groups
    units: np.ndarray  # [S+1]
    day: np.ndarray  # [S+1]
    day_cap: np.ndarray  # [D]
    amount_kind: np.ndarray  # [I] 0 fixed, 1 elastic, 2 target, 3 open
    need: np.ndarray  # [I] fixed: need; elastic: max; target: cap; open: 0
    amount_cap: np.ndarray  # [I] most units the item may hold (W4)
    one_sitting: np.ndarray  # [I] bool
    insert_units: np.ndarray  # [I] units a new chunk gets from the insert move
    min_chunk: np.ndarray  # [I]
    max_chunk: np.ndarray  # [I] −1 is no maximum
    ceiling_day0: np.ndarray  # [I] open: today's ceiling, after today's progress
    ceiling: np.ndarray  # [I] open: other days' ceiling
    first_slot: np.ndarray  # [I] first allowed slot
    last_slot: np.ndarray  # [I] last allowed slot
    allowed: np.ndarray  # [I, S+1] bool (W2)
    locked: np.ndarray  # [I, S+1] bool (W3)
    on_time: np.ndarray  # [I, S+1] bool: allowed and, for hard items due in the horizon, ending by the due (W9)
    hard_due: np.ndarray  # [I] bool: a hard fixed-amount item due inside the horizon
    dep_ptr: np.ndarray  # [I+1] CSR over the waiting item
    dep_source: np.ndarray
    dep_required: np.ndarray
    dep_lag: np.ndarray  # [deps, S+1] the slot each start reads its source's progress before (W8)
    dependents_ptr: np.ndarray  # [I+1] CSR: the items waiting on each item
    dependents: np.ndarray
    price: np.ndarray  # [3, I, S+1] per stage
    over_cost: np.ndarray  # [3, I] per unplaced unit
    m_stage: np.ndarray  # [M]
    m_const: np.ndarray  # [M]
    h_ptr: np.ndarray  # [M+1] hinges per measure
    h_dir: np.ndarray  # 0 above, 1 below
    h_theta: np.ndarray
    h_coef: np.ndarray
    x_ptr: np.ndarray  # [I*(S+1)+1] measures each x(item, slot) appears in
    x_m: np.ndarray
    x_c: np.ndarray
    st_ptr: np.ndarray  # the same for start(item, slot)
    st_m: np.ndarray
    st_c: np.ndarray
    ov_ptr: np.ndarray  # [I+1] the same for over(item)
    ov_m: np.ndarray
    ov_c: np.ndarray
    ag_ptr: np.ndarray  # [I*(S+1)+1] the any-of groups each (item, slot) belongs to
    ag_g: np.ndarray
    any_ptr: np.ndarray  # [G+1] measures each group appears in
    any_m: np.ndarray
    any_c: np.ndarray
    R: int  # rules, for per-rule totals
    rule_price: np.ndarray  # [R, I, S+1]
    rule_over: np.ndarray  # [R, I]
    m_rule: np.ndarray  # [M]


def csr(n: int, entries: list[tuple[int, int, int]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(row, column, coefficient) entries → compressed rows (ptr, columns, coefficients), keeping entry order."""
    table = np.array(entries, dtype=np.int64).reshape(-1, 3)
    order = np.argsort(table[:, 0], kind="stable")
    ptr = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.bincount(table[:, 0], minlength=n), out=ptr[1:])
    return ptr, table[order, 1].copy(), table[order, 2].copy()


@dataclass
class Compiled:
    problem: Problem
    m: Model
    keys: tuple[str, ...]
    rule_names: tuple[str, ...]

    def owner_from_plan(self, plan: Plan) -> np.ndarray:
        owner = np.full(self.m.S, -1, dtype=np.int16)
        index = {k: i for i, k in enumerate(self.keys)}
        for key, slots in plan.items():
            for s in slots:
                owner[s] = index[key]
        return owner

    def plan_from_owner(self, owner: np.ndarray) -> dict[str, tuple[int, ...]]:
        out: dict[str, list[int]] = {k: [] for k in self.keys}
        for s in range(self.m.S):
            if owner[s] >= 0:
                out[self.keys[owner[s]]].append(s)
        return {k: tuple(v) for k, v in out.items()}


def compile_problem(problem: Problem) -> Compiled:
    keys = tuple(problem.items)
    index = {k: i for i, k in enumerate(keys)}
    items = item_arrays(problem, keys)
    deps = dependency_arrays(problem, keys, index)
    rule_names = tuple(dict.fromkeys(r.name for r in problem.rules))
    prices = price_arrays(problem, keys, index, rule_names)
    measures = measure_arrays(problem, index, rule_names)
    grid = problem.grid
    model = Model(
        len(keys), grid.S, grid.n_days, measures["M"], measures["G"],
        grid.units.astype(np.int64), grid.day.astype(np.int64), np.array(problem.day_caps, dtype=np.int64),
        *items, *deps, prices["price"], prices["over_cost"],
        *(measures[k] for k in ("m_stage", "m_const", "h_ptr", "h_dir", "h_theta", "h_coef", "x_ptr", "x_m",
                                "x_c", "st_ptr", "st_m", "st_c", "ov_ptr", "ov_m", "ov_c", "ag_ptr", "ag_g",
                                "any_ptr", "any_m", "any_c")),
        len(rule_names), prices["rule_price"], prices["rule_over"], measures["m_rule"],
    )  # fmt: skip
    return Compiled(problem, model, keys, rule_names)


def item_arrays(problem: Problem, keys: tuple[str, ...]) -> tuple[np.ndarray, ...]:
    grid = problem.grid
    n, width = len(keys), grid.S + 1
    kind = np.zeros(n, dtype=np.int64)
    need = np.zeros(n, dtype=np.int64)
    amount_cap = np.zeros(n, dtype=np.int64)
    one_sitting = np.zeros(n, dtype=bool)
    insert_units = np.ones(n, dtype=np.int64)
    min_chunk = np.ones(n, dtype=np.int64)
    max_chunk = np.full(n, -1, dtype=np.int64)
    ceiling_day0 = np.zeros(n, dtype=np.int64)
    ceiling = np.zeros(n, dtype=np.int64)
    first_slot = np.zeros(n, dtype=np.int64)
    last_slot = np.zeros(n, dtype=np.int64)
    allowed = np.zeros((n, width), dtype=bool)
    locked = np.zeros((n, width), dtype=bool)
    on_time = np.zeros((n, width), dtype=bool)
    hard_due = np.zeros(n, dtype=bool)
    for i, key in enumerate(keys):
        it = problem.items[key]
        kind[i] = AMOUNT_KIND[it.amount]
        need[i] = {"fixed": it.need, "elastic": it.max, "target": it.cap, "open": 0}[it.amount]
        amount_cap[i] = {"fixed": it.need, "elastic": it.max, "target": it.cap, "open": NO_LIMIT}[it.amount]
        one_sitting[i] = it.shape == "one_sitting"
        insert_units[i] = first_chunk_units(it)
        min_chunk[i] = it.min_chunk
        max_chunk[i] = -1 if it.max_chunk is None else it.max_chunk
        ceiling_day0[i] = it.daily_ceiling - it.progress_today
        ceiling[i] = it.daily_ceiling
        allowed[i, list(it.allowed)] = True
        locked[i, list(it.locked)] = True
        if it.allowed:
            first_slot[i], last_slot[i] = min(it.allowed), max(it.allowed)
        due_inside = it.due_utc is not None and it.due_utc <= grid.horizon_end
        hard_due[i] = it.firmness == "hard" and it.amount == "fixed" and due_inside
        on_time[i] = allowed[i]
        if hard_due[i]:
            for s in it.allowed:
                if int(grid.end[s]) > it.due_utc and s not in it.locked:  # a lock is never moved
                    on_time[i, s] = False
    return (kind, need, amount_cap, one_sitting, insert_units, min_chunk, max_chunk, ceiling_day0, ceiling,
            first_slot, last_slot, allowed, locked, on_time, hard_due)  # fmt: skip


def first_chunk_units(it) -> int:  # noqa: ANN001
    if it.shape == "one_sitting":
        if it.amount == "fixed":
            return max(1, it.need)
        if it.amount == "elastic":
            return max(it.min_chunk, it.ideal)
    if it.amount == "target":
        # A new sitting pays its chunk cost at once and its shortfall back an hour at a time: opened at the
        # minimum it was uphill, so a weekly goal stayed at one sitting with the week half empty (M15).
        return max(it.min_chunk, min(it.target, 8))
    return it.min_chunk


def dependency_arrays(problem: Problem, keys: tuple[str, ...], index: dict[str, int]) -> tuple[np.ndarray, ...]:
    grid = problem.grid
    rows: list[tuple[int, int, int, np.ndarray]] = []
    for key in keys:
        it = problem.items[key]
        for dep in it.depends_on:
            if dep.required == 0 or dep.key not in index:
                continue
            lag = np.zeros(grid.S + 1, dtype=np.int64)
            for s in it.allowed:
                lag[s] = lag_slot(problem, s, dep.lag_min)
            rows.append((index[key], index[dep.key], dep.required, lag))
    rows.sort(key=lambda r: r[0])  # stable, so dependencies of one item keep their order
    ptr, sources, required = csr(len(keys), [(r[0], r[1], r[2]) for r in rows])
    lags = np.stack([r[3] for r in rows]) if rows else np.zeros((0, grid.S + 1), dtype=np.int64)
    dependents_ptr, dependents, _ = csr(len(keys), [(r[1], r[0], 1) for r in rows])
    return ptr, sources, required, lags, dependents_ptr, dependents


def price_arrays(problem: Problem, keys: tuple[str, ...], index: dict[str, int],
                 rule_names: tuple[str, ...]) -> dict[str, np.ndarray]:  # fmt: skip
    S, n, n_rules = problem.grid.S, len(keys), len(rule_names)
    price = np.zeros((3, n, S + 1), dtype=np.int64)
    over_cost = np.zeros((3, n), dtype=np.int64)
    rule_price = np.zeros((n_rules, n, S + 1), dtype=np.int64)
    rule_over = np.zeros((n_rules, n), dtype=np.int64)
    rule_index = {name: r for r, name in enumerate(rule_names)}
    for rule in problem.rules:
        if not rule.has_price:
            continue
        stage = STAGES.index(rule.stage)
        for it in problem.items.values():
            if not rule.applies(it):
                continue
            row, i = price_row(problem, rule, it), index[it.key]
            price[stage, i] += row
            rule_price[rule_index[rule.name], i, :S] += row[:S]
            if it.amount == "fixed":
                over_cost[stage, i] += row[S]
                rule_over[rule_index[rule.name], i] += row[S]
    price[:, :, S] = 0  # the overflow price lives in over_cost
    return {"price": price, "over_cost": over_cost, "rule_price": rule_price, "rule_over": rule_over}


def measure_arrays(problem: Problem, index: dict[str, int], rule_names: tuple[str, ...]) -> dict[str, object]:
    ctx = BuildContext(problem)
    width = problem.grid.S + 1
    rule_index = {name: r for r, name in enumerate(rule_names)}
    stage, const, rule_of = [], [], []
    h_ptr, h_dir, h_theta, h_coef = [0], [], [], []
    xs, starts, overs, any_entries = [], [], [], []
    group_index: dict[str, int] = {}
    pending = [(rule, m) for rule in problem.rules for m in rule.measures(ctx)]
    for n, (rule, m) in enumerate(pending):
        for var, c in m.expr.terms.items():
            kind = var[0]
            if kind == "x":
                xs.append((index[var[1]] * width + var[2], n, c))
            elif kind == "start":
                starts.append((index[var[1]] * width + var[2], n, c))
            elif kind == "over":
                overs.append((index[var[1]], n, c))
            elif kind == "any":
                any_entries.append((group_index.setdefault(var[1], len(group_index)), n, c))
            else:
                raise NotImplementedError(f"the kernel has no {kind} variable ({rule.name})")
        stage.append(STAGES.index(rule.stage))
        rule_of.append(rule_index[rule.name])
        const.append(m.expr.const)
        for h in m.curve:
            h_dir.append(0 if h.direction == "above" else 1)
            h_theta.append(h.whole_theta)
            h_coef.append(hinge_coefficient(rule.effective_weight, m.mult, h.slope, m.unit, problem.scale,
                                            f"{rule.name}/{m.name}"))  # fmt: skip
        h_ptr.append(len(h_dir))
    members = [(index[key] * width + s, g, 1) for name, g in group_index.items() for key, s in ctx.any_groups[name]]
    n_items = len(index)
    as_array = lambda v: np.array(v, dtype=np.int64)  # noqa: E731
    x_ptr, x_m, x_c = csr(n_items * width, xs)
    st_ptr, st_m, st_c = csr(n_items * width, starts)
    ov_ptr, ov_m, ov_c = csr(n_items, overs)
    any_ptr, any_m, any_c = csr(len(group_index), any_entries)
    ag_ptr, ag_g, _ = csr(n_items * width, members)
    return {
        "M": len(pending), "G": len(group_index), "m_stage": as_array(stage), "m_const": as_array(const),
        "m_rule": as_array(rule_of), "h_ptr": as_array(h_ptr), "h_dir": as_array(h_dir),
        "h_theta": as_array(h_theta), "h_coef": as_array(h_coef), "x_ptr": x_ptr, "x_m": x_m, "x_c": x_c,
        "st_ptr": st_ptr, "st_m": st_m, "st_c": st_c, "ov_ptr": ov_ptr, "ov_m": ov_m, "ov_c": ov_c,
        "ag_ptr": ag_ptr, "ag_g": ag_g, "any_ptr": any_ptr, "any_m": any_m, "any_c": any_c,
    }  # fmt: skip
