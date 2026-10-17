"""Instance generators (RESEARCH_PROMPT P1): reference benchmark, Cornell-style semester, stress, adversarial.

Everything is a `Scenario`: facet specs + pins + a clock + settings + rules. `Scenario.build()` turns it
into a pruned `Problem`. Scenarios are plain data, so warm-start variants are cheap to derive.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Callable, Mapping, Sequence

import numpy as np

from .builder import ItemSpec, Pin, build_problem, spec
from .defaults import build_rules
from .problem import DayScales, Problem
from .rules import Rule
from .settings import Settings

MONDAY_WEEK1 = 7  # epoch date 7 is a Monday; the second week of the epoch


def at(date: int, hhmm: str) -> int:
    h, m = hhmm.split(":")
    return date * 1440 + int(h) * 60 + int(m)


def q15(minutes: float, lo: int = 15, hi: int = 600) -> int:
    return int(min(hi, max(lo, round(minutes / 15) * 15)))


@dataclass
class Scenario:
    name: str
    specs: list[ItemSpec]
    pins: list[Pin]
    now: int
    settings: Settings = field(default_factory=Settings)
    rule_specs: list[dict] | None = None  # None = the reference rules
    extra_rules: list[dict] = field(default_factory=list)
    scales: Sequence[DayScales] | None = None
    end: int | None = None
    meta: dict = field(default_factory=dict)

    def rules(self) -> list[Rule]:
        return build_rules(self.rule_specs, self.extra_rules)

    def build(self, current: Mapping[str, Sequence[int]] | None = None, rules: list[Rule] | None = None) -> Problem:
        return build_problem(self.specs, self.pins, self.now, self.settings,
                             rules if rules is not None else self.rules(), self.scales, current, self.end)

    def free_hours(self) -> float:
        """Hours not blocked by fixed items or the sleep core."""
        fixed_only = [s for s in self.specs if s.when == "fixed"]
        p = build_problem(fixed_only, [], self.now, self.settings, [], None, None, self.end)
        g = p.grid
        return float(sum(g.units[s] for s in range(g.S) if not (p.blocked[s] or p.core[s]))) * 0.25

    def flexible_hours(self) -> float:
        return sum(s.duration_min for s in self.specs if s.when != "fixed" and s.amount == "fixed") / 60

    def copy(self) -> "Scenario":
        return copy.deepcopy(self)


class _Ids:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> int:
        self.n += 1
        return self.n


def _fixed_week(rng: np.random.Generator, ids: _Ids, days: range, hours_per_week: float = 15.0) -> list[ItemSpec]:
    """Class meetings and a few commitments totalling about `hours_per_week` of fixed time."""
    out: list[ItemSpec] = []
    slots = [("09:05", 75), ("10:10", 50), ("11:15", 75), ("13:25", 75), ("14:30", 75), ("15:35", 75)]
    patterns = [(0, 2, 4), (1, 3), (0, 2), (1, 3, 4)]
    for c in range(4):
        pat = patterns[c % 4]
        start, mins = slots[(c * 2 + int(rng.integers(0, 2))) % len(slots)]
        for d in days:
            if d % 7 in pat:
                s = at(d, start)
                out.append(spec("class", ids(), f"CS {1100 + c * 100} lecture", area=f"CS{c}", start=s,
                                end=s + mins))
    # extra commitments to reach roughly the requested weekly total
    class_hours = sum((o.end - o.start) for o in out) / 60 / (len(days) / 7)
    extra = max(0.0, hours_per_week - class_hours)
    n_extra = int(round(extra))
    for _ in range(n_extra * (len(days) // 7)):
        d = int(rng.choice(list(days)))
        h = int(rng.integers(16, 21))
        s = at(d, f"{h:02d}:00")
        out.append(spec("commitment", ids(), "club", area="Club", start=s, end=s + 60))
    return out


def _random_flexible(rng: np.random.Generator, ids: _Ids, n: int, now: int, days: int) -> list[ItemSpec]:
    kinds = ["assignment", "reading", "errand", "chore", "exam_prep", "project", "goal", "routine", "habit",
             "side_project", "maybe"]
    probs = np.array([0.34, 0.16, 0.08, 0.07, 0.05, 0.05, 0.04, 0.10, 0.05, 0.03, 0.03])
    probs = probs / probs.sum()
    out: list[ItemSpec] = []
    base_date = now // 1440
    for _ in range(n):
        kind = str(rng.choice(kinds, p=probs))
        area = f"CS{int(rng.integers(0, 4))}" if kind in ("assignment", "reading", "exam_prep", "project") else None
        due_day = base_date + int(rng.integers(1, days))
        due = at(due_day, str(rng.choice(["12:00", "17:00", "23:59"])))
        hours = float(np.clip(rng.lognormal(np.log(2.0), 0.6), 0.5, 8.0))
        dur = q15(hours * 60)
        if kind in ("assignment", "reading", "exam_prep", "project"):
            mult = {"assignment": 1, "reading": 0.7, "exam_prep": 2.0, "project": 3.0}[kind]
            rel = None if rng.random() < 0.7 else at(base_date + int(rng.integers(0, max(1, due_day - base_date))), "08:00")
            out.append(spec(kind, ids(), f"{kind}", area=area, duration_min=q15(dur * mult), due=due, release=rel,
                            importance=int(rng.integers(1, 6))))
        elif kind in ("errand", "chore"):
            out.append(spec(kind, ids(), kind, duration_min=q15(dur * 0.5), due=due if rng.random() < 0.5 else None,
                            release=now))
        elif kind == "goal":
            end_day = base_date + 7 * (1 + int(rng.integers(0, 2)))
            out.append(spec("goal", ids(), "goal", area="Health", target_min=q15(dur * 1.5),
                            release=at(end_day - 7, "04:00"), due=at(end_day, "04:00")))
        elif kind == "routine":
            d = base_date + int(rng.integers(0, days))
            out.append(spec("routine", ids(), "meal", min_min=20, ideal_min=30, max_min=45,
                            release=at(d, "11:30"), due=at(d, "14:30")))
        elif kind == "habit":
            d = base_date + int(rng.integers(0, days))
            out.append(spec("habit", ids(), "gym", duration_min=60, release=at(d, "06:00"), due=at(d + 1, "04:00")))
        elif kind == "side_project":
            out.append(spec("side_project", ids(), "book", ceiling_min=120))
        else:  # maybe
            d = base_date + int(rng.integers(0, days))
            out.append(spec("maybe", ids(), "maybe", duration_min=q15(dur * 0.5), release=at(d, "09:00"),
                            due=at(d + 2, "04:00")))
    return out


def _scale_load(sc: Scenario, load: float, cap_hours: int = 12) -> None:
    """Scale fixed-amount durations so hard work totals `load` x free hours (1.0 = exactly full)."""
    free = sc.free_hours()
    hard = [s for s in sc.specs if s.when != "fixed" and s.amount == "fixed" and s.firmness == "hard"]
    have = sum(s.duration_min for s in hard) / 60
    if not hard or have == 0:
        return
    k = load * free / have
    for s in hard:
        s.duration_min = q15(s.duration_min * k, 15, cap_hours * 60)


def _add_pins(rng: np.random.Generator, sc: Scenario, n: int, kinds=("locked", "preferred")) -> None:
    cands = [s for s in sc.specs if s.when != "fixed" and s.amount == "fixed" and s.duration_min >= 30]
    if not cands:
        return
    for _ in range(n):
        s = cands[int(rng.integers(0, len(cands)))]
        d = sc.now // 1440 + int(rng.integers(0, 6))
        hour = int(rng.integers(8, 21))
        start = at(d, f"{hour:02d}:{int(rng.choice([0, 15, 30, 45])):02d}")
        sc.pins.append(Pin(s.id, start, start + 30 + 15 * int(rng.integers(0, 4)), str(rng.choice(kinds))))


def _add_deps(rng: np.random.Generator, sc: Scenario, n: int) -> None:
    pool = [s for s in sc.specs if s.when != "fixed" and s.amount == "fixed" and s.due is not None
            and s.preset in ("assignment", "project", "exam_prep", "reading")]
    pool.sort(key=lambda s: s.due)
    made = 0
    for _ in range(n * 4):
        if made >= n or len(pool) < 2:
            break
        i = int(rng.integers(0, len(pool) - 1))
        j = int(rng.integers(i + 1, len(pool)))
        a, b = pool[i], pool[j]
        if a.due < b.due and not any(d[0] == a.id for d in b.deps):
            b.deps = b.deps + ((a.id, float(rng.choice([0.5, 1.0])), int(rng.choice([0, 0, 1440]))),)
            made += 1


def reference_instance(n_items: int, seed: int, load: float = 0.45, pins: int = 3, deps: int = 5,
                       settings: Settings | None = None, cap_hours: int = 12) -> Scenario:
    """The reference benchmark spec (section 12.4): n items, 14 days, ~15 h of fixed time a week."""
    rng = np.random.default_rng(seed)
    ids = _Ids()
    now = at(MONDAY_WEEK1, "09:00")
    days = range(MONDAY_WEEK1, MONDAY_WEEK1 + 14)
    specs = _fixed_week(rng, ids, days) + _random_flexible(rng, ids, n_items, now, 13)
    sc = Scenario(f"ref-n{n_items}-s{seed}", specs, [], now, settings or Settings(), meta=dict(n=n_items, seed=seed))
    _scale_load(sc, load, cap_hours)
    _add_deps(rng, sc, deps)
    _add_pins(rng, sc, pins)
    return sc


def cornell_semester(seed: int, settings: Settings | None = None, meals: str = "lunch",
                     load: float = 0.5) -> Scenario:
    """A realistic two-week window of a Cornell-style term (reference 12.3)."""
    rng = np.random.default_rng(seed)
    ids = _Ids()
    now = at(MONDAY_WEEK1, "09:00")
    days = range(MONDAY_WEEK1, MONDAY_WEEK1 + 14)
    specs = _fixed_week(rng, ids, days, hours_per_week=17.0)
    # social events: 2-4 evenings a week
    for wk in range(2):
        for d in rng.choice(range(7), size=int(rng.integers(2, 5)), replace=False):
            date = MONDAY_WEEK1 + 7 * wk + int(d)
            s = at(date, "19:00")
            specs.append(spec("commitment", ids(), "social", area="Social", start=s, end=s + 120, event_kind="other"))
    # weekly coursework
    for c in range(4):
        for wk in range(2):
            due_date = MONDAY_WEEK1 + 7 * wk + int(rng.choice([3, 4]))
            specs.append(spec("assignment", ids(), f"CS{1100 + c * 100} problem set", area=f"CS{c}",
                              duration_min=q15(rng.lognormal(np.log(240), 0.4)), due=at(due_date, "23:59"),
                              release=at(MONDAY_WEEK1 + 7 * wk, "04:00"), importance=int(rng.integers(2, 5))))
            specs.append(spec("reading", ids(), f"CS{1100 + c * 100} reading", area=f"CS{c}",
                              duration_min=q15(rng.lognormal(np.log(100), 0.3)),
                              due=at(MONDAY_WEEK1 + 7 * wk + 5, "12:00")))
    # two exams with prep, and one project
    for k, d in enumerate((MONDAY_WEEK1 + 9, MONDAY_WEEK1 + 12)):
        ex = at(d, "19:30")
        specs.append(spec("commitment", ids(), f"prelim {k + 1}", area=f"CS{k}", start=ex, end=ex + 90))
        specs.append(spec("exam_prep", ids(), f"prelim {k + 1} prep", area=f"CS{k}", duration_min=360, due=ex,
                          release=at(d - 5, "04:00")))
    specs.append(spec("project", ids(), "final project", area="CS3", duration_min=20 * 60,
                      due=at(MONDAY_WEEK1 + 13, "23:59")))
    # life
    for d in days:
        if meals in ("lunch", "both"):
            specs.append(spec("routine", ids(), "lunch", min_min=20, ideal_min=30, max_min=45,
                              release=at(d, "11:30"), due=at(d, "14:30")))
        if meals == "both":
            specs.append(spec("routine", ids(), "dinner", min_min=30, ideal_min=45, max_min=60,
                              release=at(d, "17:30"), due=at(d, "20:30")))
    for wk in range(2):
        w0 = MONDAY_WEEK1 + 7 * wk
        specs.append(spec("chore", ids(), "laundry", duration_min=90, release=at(w0, "09:00"), due=at(w0 + 7, "04:00")))
        specs.append(spec("errand", ids(), "groceries", duration_min=60, release=at(w0, "09:00"), due=at(w0 + 7, "04:00")))
        specs.append(spec("goal", ids(), "guitar", area="Health", target_min=180, release=at(w0, "04:00"),
                          due=at(w0 + 7, "04:00")))
        for i in range(3):
            specs.append(spec("habit", ids(), "gym", area="Health", duration_min=60, release=at(w0 + 2 * i, "06:00"),
                              due=at(w0 + 2 * i + 2, "04:00")))
    specs.append(spec("side_project", ids(), "side project", ceiling_min=180))
    sc = Scenario(f"cornell-s{seed}", specs, [], now, settings or Settings(), meta=dict(seed=seed))
    _scale_load(sc, load)
    _add_deps(rng, sc, 3)
    _add_pins(rng, sc, 3)
    return sc


# ---------------------------------------------------------------- adversarial families


def tight_deadlines(seed: int, n: int = 12, fill: float = 0.92) -> Scenario:
    """Hard deadlines in the first days that nearly fill the free time before them."""
    sc = reference_instance(0, seed, load=0.0, pins=0, deps=0)
    rng = np.random.default_rng(seed + 1)
    ids = _Ids()
    ids.n = max(s.id for s in sc.specs)
    horizon_days = 3
    sc.end = at(sc.now // 1440 + horizon_days, "04:00")
    free = sc.free_hours()
    each = free * fill / n
    for i in range(n):
        d = sc.now // 1440 + 1 + int(rng.integers(0, horizon_days - 1))
        sc.specs.append(spec("assignment", ids(), f"tight-{i}", duration_min=q15(each * 60),
                             due=at(d, "23:59") if i % 2 else sc.end, importance=int(rng.integers(1, 6))))
    sc.name = f"tight-s{seed}"
    return sc


def overload(seed: int, n: int = 30, load: float = 1.6) -> Scenario:
    sc = reference_instance(n, seed, load=load, pins=3, deps=3, cap_hours=40)
    sc.name = f"overload-s{seed}"
    return sc


def fragmented(seed: int, n: int = 20) -> Scenario:
    """Fixed items leave gaps of 30-60 minutes; chunks want 30 or 60."""
    sc = reference_instance(n, seed, load=0.35, pins=0, deps=0)
    rng = np.random.default_rng(seed + 2)
    ids = _Ids()
    ids.n = max(s.id for s in sc.specs)
    for d in range(sc.now // 1440, sc.now // 1440 + 7):
        t = at(d, "08:00")
        while t < at(d, "22:00"):
            gap = int(rng.choice([30, 45, 60]))
            block = int(rng.choice([45, 60, 75]))
            sc.specs.append(spec("commitment", ids(), "frag", start=t + gap, end=t + gap + block, event_kind="shove"))
            t += gap + block
    for s in sc.specs:
        if s.when != "fixed" and s.preset in ("assignment", "project"):
            s.min_chunk_min = 60
    sc.name = f"fragmented-s{seed}"
    return sc


def many_deps(seed: int, chain: int = 15) -> Scenario:
    sc = reference_instance(10, seed, load=0.3, pins=0, deps=0)
    ids = _Ids()
    ids.n = max(s.id for s in sc.specs)
    prev = None
    for i in range(chain):
        s = spec("assignment", ids(), f"chain-{i}", duration_min=90, due=at(sc.now // 1440 + 12, "23:59"))
        if prev is not None:
            s.deps = ((prev.id, 1.0 if i % 2 else 0.5, 0),)
        sc.specs.append(s)
        prev = s
    sc.name = f"deps-s{seed}"
    return sc


def many_one_sitting(seed: int, n: int = 30) -> Scenario:
    sc = reference_instance(10, seed, load=0.3, pins=0, deps=0)
    rng = np.random.default_rng(seed + 3)
    ids = _Ids()
    ids.n = max(s.id for s in sc.specs)
    for i in range(n):
        d = sc.now // 1440 + int(rng.integers(1, 13))
        sc.specs.append(spec("errand", ids(), f"os-{i}", duration_min=q15(rng.choice([60, 90, 120])),
                             release=sc.now, due=at(d, "23:59")))
    sc.name = f"onesit-s{seed}"
    return sc


def many_pins(seed: int, n_pins: int = 20) -> Scenario:
    sc = reference_instance(30, seed, load=0.4, pins=0, deps=2)
    _add_pins(np.random.default_rng(seed + 4), sc, n_pins)
    sc.name = f"pins-s{seed}"
    return sc


ADVERSARIAL: dict[str, Callable[[int], Scenario]] = {
    "tight": tight_deadlines,
    "overload": overload,
    "fragmented": fragmented,
    "deps": many_deps,
    "onesit": many_one_sitting,
    "pins": many_pins,
}


def stress(n_items: int, seed: int) -> Scenario:
    sc = reference_instance(n_items, seed, load=0.5, pins=5, deps=8)
    sc.name = f"stress-n{n_items}-s{seed}"
    return sc


# ---------------------------------------------------------------- tiny instances for brute force


def tiny(seed: int, n_slots: int = 8, n_items: int = 2) -> Scenario:
    """A few items on a short run of 15-minute slots from 10:00: small enough to enumerate."""
    rng = np.random.default_rng(seed)
    ids = _Ids()
    d = MONDAY_WEEK1
    now = at(d, "10:00")
    end = now + n_slots * 15
    st = Settings(horizon_days=1, fine_days=1)
    specs: list[ItemSpec] = []
    for _ in range(n_items):
        kind = str(rng.choice(["assignment", "reading", "chore", "routine", "goal", "side_project", "habit"]))
        if kind in ("assignment", "reading"):
            specs.append(spec(kind, ids(), kind, duration_min=int(rng.integers(1, 4)) * 15,
                              due=now + int(rng.integers(2, n_slots + 1)) * 15, min_chunk_min=int(rng.choice([15, 30])),
                              importance=int(rng.integers(1, 6)), chunk_cost=float(rng.choice([0.0, 0.2]))))
        elif kind in ("chore", "habit"):
            specs.append(spec(kind, ids(), kind, duration_min=int(rng.integers(1, 3)) * 15))
        elif kind == "routine":
            specs.append(spec(kind, ids(), kind, min_min=15, ideal_min=30, max_min=45, release=now, due=end))
        elif kind == "goal":
            specs.append(spec(kind, ids(), kind, target_min=45, release=now, due=end, min_chunk_min=15))
        else:
            specs.append(spec(kind, ids(), kind, ceiling_min=45, min_chunk_min=15))
    return Scenario(f"tiny-s{seed}", specs, [], now, st, end=end, meta=dict(seed=seed))
