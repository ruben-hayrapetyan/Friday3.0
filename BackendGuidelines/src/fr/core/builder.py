"""From facet specs to a pruned `Problem` (ENGINE_REFERENCE sections 4, 6A.2, 8.1)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from .grid import Grid, make_grid, planning_day_of
from .problem import DayScales, DepSpec, EngineItem, FixedOcc, NORMAL, Night, Problem
from .rules import Rule
from .settings import MINUTES_PER_DAY, UNIT_MIN, Settings


def units_of(minutes: float) -> int:
    """Flexible durations are whole units, input rounded up (40 min -> 3 units)."""
    return math.ceil(minutes / UNIT_MIN - 1e-9)


@dataclass(frozen=True)
class Pin:
    item_id: int
    start: int
    end: int
    kind: str = "locked"  # locked | preferred


@dataclass
class ItemSpec:
    id: int
    title: str = ""
    preset: str = "assignment"
    area: str | None = None
    tags: tuple[str, ...] = ()
    when: str = "window"  # fixed | window | anytime
    start: int | None = None
    end: int | None = None
    release: int | None = None
    due: int | None = None
    amount: str = "fixed"  # fixed | elastic | target | open
    duration_min: int = 0
    min_min: int = 0
    ideal_min: int = 0
    max_min: int = 0
    target_min: int = 0
    cap_min: int | None = None
    ceiling_min: int = 180
    neglect_carry: float = 0.5
    carry_min: int = 0  # shortfall of the last window, already known
    shape: str = "split"
    min_chunk_min: int = 30
    max_chunk_min: int | None = None
    chunk_cost: float = 0.0
    spread: str = "none"
    firmness: str = "none"
    importance: int = 3
    energy: str | None = None
    certainty: str = "planned"
    event_kind: str = "other"
    blocks_time: bool = True
    parent_id: int | None = None
    deps: tuple[tuple[int, float, int], ...] = ()  # (depends_on id, fraction, lag_min)
    progress_min: int = 0
    progress_today_min: int = 0


PRESETS: dict[str, dict] = {
    "assignment": dict(when="window", amount="fixed", shape="split", min_chunk_min=30, chunk_cost=0.1,
                       firmness="hard", energy="deep", importance=3),
    "project": dict(when="window", amount="fixed", shape="split", min_chunk_min=60, chunk_cost=0.05,
                    spread="cluster", firmness="hard", energy="deep"),
    "reading": dict(when="window", amount="fixed", shape="split", min_chunk_min=30, chunk_cost=0.1,
                    firmness="soft", energy="light"),
    "exam_prep": dict(when="window", amount="fixed", shape="split", min_chunk_min=30, chunk_cost=0.1,
                      spread="spread", firmness="hard", energy="deep"),
    "class": dict(when="fixed", event_kind="class"),
    "commitment": dict(when="fixed", event_kind="other"),
    "errand": dict(when="window", amount="fixed", shape="one_sitting", firmness="none", energy="physical"),
    "chore": dict(when="window", amount="fixed", shape="one_sitting", firmness="none", energy="physical"),
    "routine": dict(when="window", amount="elastic", shape="one_sitting", firmness="none", energy="light"),
    "habit": dict(when="window", amount="fixed", shape="one_sitting", spread="spread", firmness="none"),
    "goal": dict(when="window", amount="target", shape="split", min_chunk_min=30, chunk_cost=0.1,
                 firmness="none", energy="deep"),
    "side_project": dict(when="anytime", amount="open", shape="split", min_chunk_min=45, ceiling_min=180,
                         firmness="none", energy="deep"),
    "maybe": dict(when="window", amount="fixed", shape="one_sitting", firmness="none", certainty="tentative"),
}


def spec(preset: str, id: int, title: str = "", **over) -> ItemSpec:
    base = dict(PRESETS[preset])
    base.update(over)
    return ItemSpec(id=id, title=title or f"{preset}-{id}", preset=preset, **base)


def make_nights(settings: Settings, first_date: int, last_date: int) -> dict[int, Night]:
    sl = settings.sleep
    out = {}
    for date in range(first_date, last_date + 1):
        wd = date % 7
        out[date] = Night(
            bedtime=date * MINUTES_PER_DAY + sl.bedtime[wd],
            wake=(date + 1) * MINUTES_PER_DAY + sl.wake[(date + 1) % 7],
            margin=sl.margin,
        )
    return out


def _fixed_occ(sp: ItemSpec, settings: Settings) -> FixedOcc:
    before, after = settings.buffers.get(sp.event_kind, (0, 0))
    return FixedOcc(sp.title, sp.event_kind, sp.start, sp.end, sp.tags, before, after, sp.blocks_time)


def _to_item(sp: ItemSpec, grid: Grid, by_id: Mapping[int, ItemSpec], fixed_end: Mapping[int, int]) -> EngineItem | None:
    release, due = sp.release, sp.due
    parent = by_id.get(sp.parent_id) if sp.parent_id is not None else None
    if due is None and parent is not None:
        due = parent.due
    for dep_id, _frac, lag in sp.deps:
        if dep_id in fixed_end:
            release = max(release or grid.now, fixed_end[dep_id] + lag)
    progress = units_of(sp.progress_min) if sp.progress_min else 0
    tentative = sp.certainty == "tentative"
    shape = sp.shape
    min_chunk = 1 if shape == "one_sitting" else max(1, units_of(sp.min_chunk_min))
    it = EngineItem(
        key=f"item:{sp.id}", title=sp.title, area=sp.area, tags=tuple(sp.tags), preset=sp.preset,
        energy=sp.energy, importance=sp.importance, firmness=sp.firmness, amount=sp.amount,
        release=release, due=due, shape=shape, min_chunk=min_chunk,
        max_chunk=units_of(sp.max_chunk_min) if sp.max_chunk_min else None,
        chunk_cost=sp.chunk_cost, spread=sp.spread, tentative=tentative, progress=progress,
        window_is_hard=tentative or sp.amount in ("elastic", "target"),
    )
    if sp.amount == "fixed":
        it.need = max(0, units_of(sp.duration_min) - progress)
        if it.need == 0:
            return None
        it.size_hours = sp.duration_min / 60
    elif sp.amount == "elastic":
        it.min = max(0, units_of(sp.min_min) - progress)
        it.ideal = max(it.min, units_of(sp.ideal_min) - progress)
        it.max = max(it.ideal, units_of(sp.max_min) - progress)
        it.size_hours = sp.ideal_min / 60
    elif sp.amount == "target":
        it.target = units_of(sp.target_min + sp.neglect_carry * sp.carry_min)
        it.cap = units_of(sp.cap_min) if sp.cap_min else math.ceil(1.5 * it.target)
        it.size_hours = sp.target_min / 60
    else:
        it.daily_ceiling = units_of(sp.ceiling_min)
        it.progress_today = units_of(sp.progress_today_min) if sp.progress_today_min else 0
    return it


def _repair_locks(items: dict[str, EngineItem], pin_slots: dict[str, dict[str, set[int]]], blocked,
                  grid: Grid, settings: Settings, ids: Mapping[str, int]) -> list[int]:
    """Section 8.1 lock checks. Returns the day caps after raising them where locks exceed them."""
    owner: dict[int, str] = {}
    for key in sorted(items, key=lambda k: ids[k]):  # newer (higher id) wins an overlap
        for s in sorted(pin_slots[key]["locked"]):
            old = owner.get(s)
            if old is not None:
                pin_slots[old]["locked"].discard(s)
                pin_slots[old]["preferred"].add(s)
            owner[s] = key
    for key, p in pin_slots.items():
        over_fixed = {s for s in p["locked"] if blocked[s]}
        p["locked"] -= over_fixed
        p["preferred"] |= over_fixed
    caps = [settings.day_cap_units] * grid.n_days
    for key, p in pin_slots.items():
        it = items[key]
        locked_units = sum(int(grid.units[s]) for s in p["locked"])
        if it.amount == "fixed" and locked_units > it.need:
            it.need = locked_units
    for d in range(grid.n_days):
        locked_day = sum(int(grid.units[s]) for p in pin_slots.values() for s in p["locked"]
                         if grid.slots[s].day == d)
        caps[d] = max(caps[d], locked_day)
    return caps


def build_problem(
    specs: Sequence[ItemSpec],
    pins: Sequence[Pin],
    now: int,
    settings: Settings,
    rules: Sequence[Rule],
    scales: Sequence[DayScales] | None = None,
    current: Mapping[str, Sequence[int]] | None = None,
    end: int | None = None,
    debt_hours: Mapping[int, float] | None = None,
) -> Problem:
    grid = make_grid(now, settings, end=end)
    by_id = {s.id: s for s in specs}
    children = {s.parent_id for s in specs if s.parent_id is not None}
    p0 = grid.slots[0].date
    nights = make_nights(settings, p0 - 1, p0 + settings.horizon_days + 1)
    if debt_hours:
        nights = {d: replace(n, debt_hours=debt_hours.get(d, 0.0)) for d, n in nights.items()}

    fixed: list[FixedOcc] = []
    fixed_end: dict[int, int] = {}
    for sp in specs:
        if sp.when == "fixed":
            if sp.end > grid.now and sp.start < grid.horizon_end + MINUTES_PER_DAY:
                fixed.append(_fixed_occ(sp, settings))
            fixed_end[sp.id] = sp.end

    items: dict[str, EngineItem] = {}
    ids: dict[str, int] = {}
    for sp in specs:
        if sp.when == "fixed" or sp.id in children:
            continue
        it = _to_item(sp, grid, by_id, fixed_end)
        if it is not None:
            items[it.key] = it
            ids[it.key] = sp.id

    key_of = {v: k for k, v in ids.items()}
    for key, it in items.items():
        sp = by_id[ids[key]]
        deps = []
        for dep_id, frac, lag in sp.deps:
            other = items.get(key_of.get(dep_id, ""))
            if other is not None:
                deps.append(DepSpec(other.key, frac, lag, other.total_units, other.progress))
        it.depends_on = tuple(deps)

    # pins -> slot sets
    pin_slots = {k: {"locked": set(), "preferred": set()} for k in items}
    for pin in pins:
        key = key_of.get(pin.item_id)
        if key is None:
            continue
        pin_slots[key][pin.kind if pin.kind in ("locked", "preferred") else "preferred"].update(
            grid.slots_in(pin.start, pin.end))

    pre = Problem(grid, settings, items, fixed, nights, [settings.day_cap_units] * grid.n_days, [],
                  list(scales) if scales is not None else [NORMAL] * grid.n_days, settings.energy_map)
    repaired = _repair_locks(items, pin_slots, pre.blocked, grid, settings, ids)
    for key, it in items.items():
        it.locked = frozenset(pin_slots[key]["locked"])
        it.preferred = frozenset(pin_slots[key]["preferred"])
        it.current = frozenset(current.get(key, ())) if current else frozenset()

    problem = Problem(grid, settings, items, fixed, nights, repaired,
                      list(rules), pre.scales, settings.energy_map)
    for r in problem.rules:
        r.prepare(problem)
    prune(problem)
    if _demote_unusable_locks(problem):
        prune(problem)
    return problem


def _demote_unusable_locks(problem: Problem) -> bool:
    """A locked run that breaks the item's own chunk rules and cannot grow becomes a preferred pin
    (the reference only covers one-sitting locks, 8.1; the same contradiction exists for chunk limits)."""
    g, changed = problem.grid, False
    for it in problem.items.values():
        if not it.locked:
            continue
        keep, demote = set(it.locked), set()
        run: list[int] = []
        for s in sorted(it.locked) + [None]:
            if run and (s is None or s != run[-1] + 1):
                units = sum(int(g.units[x]) for x in run)
                can_grow = any(n in it.allowed_set and n not in it.locked
                               for n in (run[0] - 1, run[-1] + 1))
                too_short = units < it.min_chunk and not can_grow
                too_long = it.max_chunk is not None and units > it.max_chunk
                if too_short or too_long:
                    demote.update(run)
                run = []
            if s is not None:
                run.append(s)
        if demote:
            it.locked = frozenset(keep - demote)
            it.preferred = frozenset(it.preferred | demote)
            changed = True
    if changed:
        problem.lock_owner = {s: it.key for it in problem.items.values() for s in it.locked}
    return changed


def prune(problem: Problem) -> None:
    """Remove slots no variable should ever exist for (6A.2). Locked slots are always kept."""
    g = problem.grid
    forbidders = [r for r in problem.rules if type(r).forbids is not Rule.forbids]
    for it in problem.items.values():
        rel = g.now if it.release is None else it.release
        keep = []
        for s in range(g.S):
            if g.start[s] < rel:
                continue
            if it.window_is_hard and it.due is not None and g.start[s] >= it.due:
                continue
            if problem.blocked[s] or problem.core[s]:
                continue
            owner = problem.lock_owner.get(s)
            if owner is not None and owner != it.key:
                continue
            if any(r.applies(it) and r.forbids(it, s) for r in forbidders):
                continue
            keep.append(s)
        it.set_allowed(keep)
