"""Compile a Problem into flat arrays a numba sampler can use.

Everything is derived from the same sources the shared evaluator uses (`price_row`, `rule.measures`,
the checker's hard rules), so a compiled energy equals `evaluate()` to the integer. The tests prove it.

Energy = price terms (slot occupancy, stage by stage) + overflow terms + hinge costs of measure values.
A measure value is a linear function of: x(item, slot) * units, start(item, slot), over(item) and
any(group), and is kept up to date incrementally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from ..core.context import BuildContext
from ..core.evaluate import lag_slot
from ..core.problem import Problem
from ..core.pwl import hinge_coeff
from ..core.rules import price_row
from ..core.settings import STAGES

KIND = {"fixed": 0, "elastic": 1, "target": 2, "open": 3}


class Model(NamedTuple):
    I: int
    S: int
    D: int
    M: int
    G: int
    # grid
    units: np.ndarray  # [S+1] int64
    day: np.ndarray  # [S+1] int64
    day_cap: np.ndarray  # [D]
    # items
    kind: np.ndarray  # [I] 0 fixed 1 elastic 2 target 3 open
    need: np.ndarray  # [I] fixed: need; elastic: max; target: cap; open: 0
    amount_cap: np.ndarray  # [I] hard ceiling on placed units (fixed: need, elastic: max, target: cap, open: big)
    one_sit: np.ndarray  # [I] bool
    ins_units: np.ndarray  # [I] units a fresh chunk of this item gets when inserted
    min_chunk: np.ndarray  # [I]
    max_chunk: np.ndarray  # [I] -1 = none
    ceil0: np.ndarray  # [I] open: day-0 ceiling
    ceil: np.ndarray  # [I] open: other-day ceiling
    lo: np.ndarray  # [I] first allowed slot
    hi: np.ndarray  # [I] last allowed slot
    allowed: np.ndarray  # [I, S+1] bool (last column False)
    locked: np.ndarray  # [I, S+1] bool
    wall_ok: np.ndarray  # [I, S+1] bool: allowed and (for deadline-wall items) not late
    hard_due: np.ndarray  # [I] bool: hard item due inside the horizon (deadline wall candidates)
    # dependencies
    dep_ptr: np.ndarray  # [I+1] CSR over dependent item
    dep_src: np.ndarray
    dep_req: np.ndarray
    dep_lag: np.ndarray  # [ND, S+1] lag_slot per slot
    dnt_ptr: np.ndarray  # [I+1] CSR: dependents of an item
    dnt_dst: np.ndarray
    # price
    price: np.ndarray  # [3, I, S+1] int64
    over_cost: np.ndarray  # [3, I] cost per unplaced unit (fixed items)
    # measures
    m_stage: np.ndarray  # [M]
    m_const: np.ndarray  # [M]
    h_ptr: np.ndarray  # [M+1]
    h_dir: np.ndarray  # [H] 0 above 1 below
    h_theta: np.ndarray
    h_coef: np.ndarray
    x_ptr: np.ndarray  # [I*(S+1)+1]
    x_m: np.ndarray
    x_c: np.ndarray
    st_ptr: np.ndarray  # start-variable adjacency, same indexing
    st_m: np.ndarray
    st_c: np.ndarray
    ov_ptr: np.ndarray  # [I+1]
    ov_m: np.ndarray
    ov_c: np.ndarray
    ag_ptr: np.ndarray  # slot -> any groups: indexed by item*(S+1)+s
    ag_g: np.ndarray
    any_ptr: np.ndarray  # [G+1] group -> measures
    any_m: np.ndarray
    any_c: np.ndarray


def _csr(n: int, entries: list[tuple[int, int, int]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """entries (row, col, coef) -> CSR (ptr, cols, coefs)."""
    ptr = np.zeros(n + 1, dtype=np.int64)
    for r, _, _ in entries:
        ptr[r + 1] += 1
    np.cumsum(ptr, out=ptr)
    cols = np.zeros(len(entries), dtype=np.int64)
    cs = np.zeros(len(entries), dtype=np.int64)
    fill = ptr[:-1].copy()
    for r, c, k in entries:
        cols[fill[r]] = c
        cs[fill[r]] = k
        fill[r] += 1
    return ptr, cols, cs


def compile_problem(problem: Problem) -> "Compiled":
    g = problem.grid
    st = problem.settings
    keys = tuple(problem.items)
    ix = {k: i for i, k in enumerate(keys)}
    I, S, D = len(keys), g.S, g.n_days
    stage_ix = {s: n for n, s in enumerate(STAGES)}

    kind = np.zeros(I, dtype=np.int64)
    need = np.zeros(I, dtype=np.int64)
    amount_cap = np.zeros(I, dtype=np.int64)
    one_sit = np.zeros(I, dtype=bool)
    ins_units = np.ones(I, dtype=np.int64)
    min_chunk = np.ones(I, dtype=np.int64)
    max_chunk = np.full(I, -1, dtype=np.int64)
    ceil0 = np.zeros(I, dtype=np.int64)
    ceil = np.zeros(I, dtype=np.int64)
    lo = np.zeros(I, dtype=np.int64)
    hi = np.zeros(I, dtype=np.int64)
    allowed = np.zeros((I, S + 1), dtype=bool)
    locked = np.zeros((I, S + 1), dtype=bool)
    wall_ok = np.zeros((I, S + 1), dtype=bool)
    hard_due = np.zeros(I, dtype=bool)
    for k, it in problem.items.items():
        i = ix[k]
        kind[i] = KIND[it.amount]
        need[i] = {"fixed": it.need, "elastic": it.max, "target": it.cap, "open": 0}[it.amount]
        amount_cap[i] = {"fixed": it.need, "elastic": it.max, "target": it.cap, "open": 10**6}[it.amount]
        one_sit[i] = it.shape == "one_sitting"
        if it.amount == "fixed":
            ins_units[i] = max(1, it.need - it.progress * 0) if one_sit[i] else it.min_chunk
        elif it.amount == "elastic":
            ins_units[i] = max(it.min_chunk, it.ideal) if one_sit[i] else it.min_chunk
        else:
            ins_units[i] = it.min_chunk
        min_chunk[i] = it.min_chunk
        max_chunk[i] = -1 if it.max_chunk is None else it.max_chunk
        ceil0[i] = it.daily_ceiling - it.progress_today
        ceil[i] = it.daily_ceiling
        for s in it.allowed:
            allowed[i, s] = True
        for s in it.locked:
            locked[i, s] = True
        if it.allowed:
            lo[i], hi[i] = min(it.allowed), max(it.allowed)
        hard_due[i] = it.firmness == "hard" and it.due is not None and it.amount == "fixed" and it.due <= g.horizon_end
        wall_ok[i] = allowed[i]
        if hard_due[i]:
            for s in it.allowed:
                if g.end[s] > it.due:
                    wall_ok[i, s] = False
            for s in it.locked:  # a lock is never removed, even if it sits after the due date
                wall_ok[i, s] = True

    # dependencies
    dep_rows: list[tuple[int, int, int]] = []
    lag_rows = []
    for k, it in problem.items.items():
        for dep in it.depends_on:
            req = dep.required
            if req == 0 or dep.key not in ix:
                continue
            row = np.zeros(S + 1, dtype=np.int64)
            for s in it.allowed:
                row[s] = lag_slot(problem, s, dep.lag_min)
            dep_rows.append((ix[k], ix[dep.key], req))
            lag_rows.append(row)
    dep_rows_sorted = sorted(range(len(dep_rows)), key=lambda n: dep_rows[n][0])
    dep_ptr = np.zeros(I + 1, dtype=np.int64)
    for n in dep_rows_sorted:
        dep_ptr[dep_rows[n][0] + 1] += 1
    np.cumsum(dep_ptr, out=dep_ptr)
    dep_src = np.array([dep_rows[n][1] for n in dep_rows_sorted], dtype=np.int64)
    dep_req = np.array([dep_rows[n][2] for n in dep_rows_sorted], dtype=np.int64)
    dep_lag = np.stack([lag_rows[n] for n in dep_rows_sorted]) if lag_rows else np.zeros((0, S + 1), dtype=np.int64)
    dn_entries = [(dep_rows[n][1], dep_rows[n][0], 1) for n in dep_rows_sorted]
    dnt_ptr, dnt_dst, _ = _csr(I, dn_entries)

    # prices
    price = np.zeros((3, I, S + 1), dtype=np.int64)
    over_cost = np.zeros((3, I), dtype=np.int64)
    for rule in problem.rules:
        if not rule.has_price:
            continue
        sx = stage_ix[rule.stage]
        for it in problem.items.values():
            if not rule.applies(it):
                continue
            row = price_row(problem, rule, it)
            i = ix[it.key]
            price[sx, i, : S + 1] += row
            if it.amount == "fixed":
                over_cost[sx, i] += row[S]
    price[:, :, S] = 0  # column S is the overflow price, kept in over_cost

    # measures
    ctx = BuildContext(problem)
    m_stage, m_const = [], []
    h_ptr, h_dir, h_theta, h_coef = [0], [], [], []
    xs: list[tuple[int, int, int]] = []
    sts: list[tuple[int, int, int]] = []
    ovs: list[tuple[int, int, int]] = []
    any_entries: list[tuple[int, int, int]] = []
    any_index: dict[str, int] = {}
    n_m = 0
    W = S + 1
    pending = []
    for rule in problem.rules:
        for m in rule.measures(ctx):
            pending.append((rule, m))
    for rule, m in pending:
        for v, c in m.expr.terms.items():
            kd = v[0]
            if kd == "x":
                xs.append((ix[v[1]] * W + v[2], n_m, c))
            elif kd == "start":
                sts.append((ix[v[1]] * W + v[2], n_m, c))
            elif kd == "over":
                ovs.append((ix[v[1]], n_m, c))
            elif kd == "any":
                gi = any_index.setdefault(v[1], len(any_index))
                any_entries.append((gi, n_m, c))
            else:
                raise NotImplementedError(f"measure variable {kd} in {rule.name}")
        m_stage.append(stage_ix[rule.stage])
        m_const.append(m.expr.const)
        for h in m.curve:
            h_dir.append(0 if h.direction == "above" else 1)
            h_theta.append(h.whole_theta)
            h_coef.append(hinge_coeff(rule.weight, m.mult, h.slope, m.unit, st.scale, f"{rule.name}/{m.name}"))
        h_ptr.append(len(h_dir))
        n_m += 1
    G = len(any_index)
    x_ptr, x_m, x_c = _csr(I * W, xs)
    st_ptr, st_m, st_c = _csr(I * W, sts)
    ov_ptr, ov_m, ov_c = _csr(I, ovs)
    any_ptr, any_m, any_c = _csr(G, any_entries)
    ag_entries = []
    for name, gi in any_index.items():
        for key, s in ctx.any_defs[name]:
            ag_entries.append((ix[key] * W + s, gi, 1))
    ag_ptr, ag_g, _ = _csr(I * W, ag_entries)

    a = lambda v: np.array(v, dtype=np.int64)  # noqa: E731
    model = Model(
        I, S, D, n_m, G, g.units.astype(np.int64), g.day.astype(np.int64), a(problem.day_caps),
        kind, need, amount_cap, one_sit, ins_units, min_chunk, max_chunk, ceil0, ceil, lo, hi, allowed, locked, wall_ok,
        hard_due, dep_ptr, dep_src, dep_req, dep_lag, dnt_ptr, dnt_dst, price, over_cost,
        a(m_stage), a(m_const), a(h_ptr), a(h_dir), a(h_theta), a(h_coef),
        x_ptr, x_m, x_c, st_ptr, st_m, st_c, ov_ptr, ov_m, ov_c, ag_ptr, ag_g, any_ptr, any_m, any_c,
    )
    return Compiled(problem, model, keys)


@dataclass
class Compiled:
    problem: Problem
    m: Model
    keys: tuple

    def owner_from_plan(self, plan) -> np.ndarray:
        owner = np.full(self.m.S, -1, dtype=np.int16)
        ix = {k: i for i, k in enumerate(self.keys)}
        for k, slots in plan.items():
            for s in slots:
                owner[s] = ix[k]
        return owner

    def plan_from_owner(self, owner: np.ndarray) -> dict[str, tuple[int, ...]]:
        out: dict[str, list[int]] = {k: [] for k in self.keys}
        for s in range(self.m.S):
            if owner[s] >= 0:
                out[self.keys[owner[s]]].append(s)
        return {k: tuple(v) for k, v in out.items()}
