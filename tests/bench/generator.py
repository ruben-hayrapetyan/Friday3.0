"""Static benchmark and adversarial instances (DESIGN §24.5), ported from the research generators.

A `Scenario` is v3 items, dependencies and pins plus a clock and settings; `build()` turns it into a Problem
through the planner's builder, as the app does.
"""

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

from friday.core.items import Item, apply_preset, with_defaults
from friday.core.pace import DayScales
from friday.core.presets import DEFAULT_PRESETS
from friday.core.settings import DEFAULTS, validate_value
from friday.core.time import format_utc, parse_utc, to_utc
from friday.engine.problem import Problem
from friday.planner.build import BuildInput, Dependency, Pin, build_problem

MONDAY = date(2026, 10, 19)
# Deep work is cheap mid-morning, dear late and very early; the research's starting curve, by hour.
DEEP_HOURS = [3, 3, 3, 3, 3, 3, 3, 2, 1, 0.5, 0, 0, 0.5, 1, 0.5, 0.5, 0.5, 1, 1, 1.5, 2, 2, 2.5, 3]
PRESET_NAMES = {
    "assignment": "Assignment", "project": "Project", "reading": "Reading", "exam_prep": "Exam prep",
    "class": "Class", "commitment": "Event", "errand": "Errand", "chore": "Chore", "routine": "Routine",
    "habit": "Habit", "goal": "Goal", "side_project": "Side project", "maybe": "Maybe",
}  # fmt: skip


def bench_settings(timezone: str = "UTC", horizon_days: int = 14, fine_days: int = 7, cap_hours: float = 12,
                   rules: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:  # fmt: skip
    """The research's benchmark settings: sleep 23:30–07:30 on weekdays, 00:30–09:00 at weekends, 12 h cap.

    Each weekday's bedtime is that evening's and its wake is that morning's.
    """
    weekday = {"bedtime": "23:30", "wake": "07:30", "margin_min": 60}
    weekend = {"bedtime": "00:30", "wake": "09:00", "margin_min": 60}
    sleep = {d: weekday for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": weekend, "sun": weekend}
    values = dict(DEFAULTS)
    values["time"] = validate_value(
        "time", {"timezone": timezone, "horizon_days": horizon_days, "fine_days": fine_days}
    )
    values["sleep"] = validate_value("sleep", sleep)
    values["daily_cap"] = validate_value("daily_cap", dict.fromkeys(sleep, cap_hours))
    values["energy_map"] = tuple(tuple(DEEP_HOURS[cell // 2] for cell in range(48)) for _ in range(7))
    if rules is not None:
        values["rules"] = validate_value("rules", list(rules))
    return values


def reference_rules(names: Sequence[str] = (), extra: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """The named reference rules (all of them when no names are given) plus extras, as settings specs."""
    chosen = [r.model_dump() for r in DEFAULTS["rules"] if not names or r.name in names]
    return chosen + [dict(e) for e in extra]


@dataclass
class Scenario:
    name: str
    items: list[Item]
    now_utc: int
    settings: dict[str, Any]
    dependencies: list[Dependency] = field(default_factory=list)
    pins: list[Pin] = field(default_factory=list)
    areas: dict[int, str] = field(default_factory=dict)
    day_scales: Sequence[DayScales] | None = None
    end_utc: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def build(self, current: Mapping[int, Sequence[tuple[int, int]]] | None = None, **extra: Any) -> Problem:
        return build_problem(self.build_input(current, **extra))

    def build_input(self, current: Mapping[int, Sequence[tuple[int, int]]] | None = None, **extra: Any) -> BuildInput:
        return BuildInput(
            items=self.items, now_utc=self.now_utc, settings=self.settings, dependencies=self.dependencies,
            pins=self.pins, areas=self.areas, current=current or {}, day_scales=self.day_scales,
            end_utc=self.end_utc, **extra,
        )  # fmt: skip

    def copy(self) -> "Scenario":
        return copy.deepcopy(self)

    def free_hours(self) -> float:
        """Hours not blocked by fixed items or the sleep core."""
        fixed_only = Scenario(self.name, [i for i in self.items if i.when == "fixed"], self.now_utc, self.settings,
                              end_utc=self.end_utc)  # fmt: skip
        p = fixed_only.build()
        return float(sum(p.grid.units[s] for s in range(p.grid.S) if not (p.blocked[s] or p.core[s]))) * 0.25


class Maker:
    """Hands out ids and turns research-style specs (minutes, local times) into v3 items."""

    def __init__(self, timezone: str, monday: date, first_id: int = 1):
        self.timezone = timezone
        self.monday = monday
        self.next_id = first_id
        self.area_ids: dict[str, int] = {}

    def at(self, day: int, hhmm: str) -> int:
        hours, minutes = map(int, hhmm.split(":"))
        return to_utc(datetime.combine(self.monday + timedelta(days=day), datetime.min.time())
                      + timedelta(hours=hours, minutes=minutes), self.timezone)  # fmt: skip

    def item(self, preset: str, title: str = "", area: str | None = None, **fields: Any) -> Item:
        item_id, self.next_id = self.next_id, self.next_id + 1
        given = {key: (format_utc(value) if key.endswith("_utc") and isinstance(value, int) else value)
                 for key, value in fields.items()}  # fmt: skip
        if area is not None:
            given["area_id"] = self.area_ids.setdefault(area, len(self.area_ids) + 1)
        name = PRESET_NAMES[preset]
        defaults = DEFAULT_PRESETS[name].model_dump(exclude_none=True)
        return with_defaults(Item(title=title or f"{preset}-{item_id}", id=item_id, preset=name,
                                  **apply_preset(given, defaults)))  # fmt: skip

    def fixed(self, preset: str, title: str, start: int, minutes: int, **fields: Any) -> Item:
        return self.item(preset, title, start_utc=start, end_utc=start + minutes, **fields)

    def areas(self) -> dict[int, str]:
        return {i: name for name, i in self.area_ids.items()}


def units(minutes: float) -> int:
    return max(1, int(np.ceil(minutes / 15 - 1e-9)))


def q15(minutes: float, lo: int = 15, hi: int = 600) -> int:
    return int(min(hi, max(lo, round(minutes / 15) * 15)))


def fixed_week(rng: np.random.Generator, make: Maker, days: range, hours_per_week: float = 15.0) -> list[Item]:
    """Class meetings and a few commitments totalling about `hours_per_week` of fixed time."""
    out = []
    starts = [("09:05", 75), ("10:10", 50), ("11:15", 75), ("13:25", 75), ("14:30", 75), ("15:35", 75)]
    patterns = [(0, 2, 4), (1, 3), (0, 2), (1, 3, 4)]
    for c in range(4):
        start, minutes = starts[(c * 2 + int(rng.integers(0, 2))) % len(starts)]
        for d in days:
            if d % 7 in patterns[c % 4]:
                out.append(make.fixed("class", f"CS {1100 + c * 100} lecture", make.at(d, start), minutes,
                                      area=f"CS{c}", event_kind="class"))  # fmt: skip
    class_hours = sum((to_minutes(i.end_utc) - to_minutes(i.start_utc)) for i in out) / 60 / (len(days) / 7)
    for _ in range(int(round(max(0.0, hours_per_week - class_hours))) * (len(days) // 7)):
        d = int(rng.choice(list(days)))
        out.append(make.fixed("commitment", "club", make.at(d, f"{int(rng.integers(16, 21)):02d}:00"), 60,
                              area="Club"))  # fmt: skip
    return out


def to_minutes(iso: str | None) -> int:
    assert iso is not None
    return parse_utc(iso)


def random_flexible(rng: np.random.Generator, make: Maker, n: int, now: int, days: int) -> list[Item]:
    kinds = ["assignment", "reading", "errand", "chore", "exam_prep", "project", "goal", "routine", "habit",
             "side_project", "maybe"]  # fmt: skip
    probs = np.array([0.34, 0.16, 0.08, 0.07, 0.05, 0.05, 0.04, 0.10, 0.05, 0.03, 0.03])
    probs = probs / probs.sum()
    out = []
    for _ in range(n):
        kind = str(rng.choice(kinds, p=probs))
        area = f"CS{int(rng.integers(0, 4))}" if kind in ("assignment", "reading", "exam_prep", "project") else None
        due_day = 1 + int(rng.integers(0, days - 1))
        due = make.at(due_day, str(rng.choice(["12:00", "17:00", "23:59"])))
        minutes = q15(float(np.clip(rng.lognormal(np.log(2.0), 0.6), 0.5, 8.0)) * 60)
        if kind in ("assignment", "reading", "exam_prep", "project"):
            factor = {"assignment": 1, "reading": 0.7, "exam_prep": 2.0, "project": 3.0}[kind]
            release = None if rng.random() < 0.7 else make.at(int(rng.integers(0, max(1, due_day))), "08:00")
            out.append(make.item(kind, kind, area, duration_units=units(q15(minutes * factor)), due_utc=due,
                                 release_utc=release, importance=int(rng.integers(1, 6))))  # fmt: skip
        elif kind in ("errand", "chore"):
            out.append(make.item(kind, kind, duration_units=units(q15(minutes * 0.5)),
                                 due_utc=due if rng.random() < 0.5 else None, release_utc=now))  # fmt: skip
        elif kind == "goal":
            end_day = 7 * (1 + int(rng.integers(0, 2)))
            out.append(
                make.item(
                    "goal",
                    "goal",
                    "Health",
                    target_units=units(q15(minutes * 1.5)),
                    release_utc=make.at(end_day - 7, "04:00"),
                    due_utc=make.at(end_day, "04:00"),
                )
            )
        elif kind == "routine":
            d = int(rng.integers(0, days))
            out.append(make.item("routine", "meal", min_units=2, ideal_units=2, max_units=3,
                                 release_utc=make.at(d, "11:30"), due_utc=make.at(d, "14:30")))  # fmt: skip
        elif kind == "habit":
            d = int(rng.integers(0, days))
            out.append(make.item("habit", "gym", duration_units=4, release_utc=make.at(d, "06:00"),
                                 due_utc=make.at(d + 1, "04:00")))  # fmt: skip
        elif kind == "side_project":
            out.append(make.item("side_project", "book", daily_ceiling_units=8))
        else:
            d = int(rng.integers(0, days))
            out.append(make.item("maybe", "maybe", duration_units=units(q15(minutes * 0.5)),
                                 release_utc=make.at(d, "09:00"), due_utc=make.at(d + 2, "04:00")))  # fmt: skip
    return out


def scale_load(sc: Scenario, load: float, cap_hours: int = 12) -> None:
    """Scale hard work so it totals `load` × the free hours (1.0 is exactly full)."""
    hard = [i for i in sc.items if i.when != "fixed" and i.amount == "fixed" and i.firmness == "hard"]
    have = sum(i.duration_units or 0 for i in hard) / 4
    if not hard or have == 0:
        return
    factor = load * sc.free_hours() / have
    for item in hard:
        item.duration_units = units(q15((item.duration_units or 0) * 15 * factor, 15, cap_hours * 60))
        item.min_chunk_units = min(item.min_chunk_units, item.duration_units)


def add_pins(rng: np.random.Generator, sc: Scenario, n: int, kinds: Sequence[str] = ("locked", "preferred")) -> None:
    """Pins inside each item's own window, before its due, so a pin never forces lateness by itself."""
    candidates = [i for i in sc.items if i.when != "fixed" and i.amount == "fixed" and (i.duration_units or 0) >= 2]
    for n_pin in range(n if candidates else 0):
        item = candidates[int(rng.integers(0, len(candidates)))]
        length = 30 + 15 * int(rng.integers(0, 4))
        lo = max(sc.now_utc + 60, to_minutes(item.release_utc) if item.release_utc else 0)
        due = to_minutes(item.due_utc) if item.due_utc else sc.now_utc + 6 * 1440
        hi = min(sc.now_utc + 6 * 1440, due - length - 60)
        if hi <= lo:
            continue
        start = int(rng.integers(lo // 15, hi // 15)) * 15
        sc.pins.append(Pin(item.id, start, start + length, str(rng.choice(kinds)), created=n_pin))  # type: ignore[arg-type]


def add_dependencies(rng: np.random.Generator, sc: Scenario, n: int) -> None:
    pool = [i for i in sc.items if i.when != "fixed" and i.amount == "fixed" and i.due_utc is not None
            and i.preset in ("Assignment", "Project", "Exam prep", "Reading")]  # fmt: skip
    pool.sort(key=lambda i: i.due_utc or "")
    made = 0
    for _ in range(n * 4):
        if made >= n or len(pool) < 2:
            break
        a_ix = int(rng.integers(0, len(pool) - 1))
        a, b = pool[a_ix], pool[int(rng.integers(a_ix + 1, len(pool)))]
        if (a.due_utc or "") < (b.due_utc or "") and not any(
            d.item_id == b.id and d.depends_on_id == a.id for d in sc.dependencies
        ):
            sc.dependencies.append(Dependency(b.id, a.id, float(rng.choice([0.5, 1.0])), int(rng.choice([0, 0, 1440]))))
            made += 1


def reference_instance(n_items: int, seed: int, load: float = 0.45, pins: int = 3, deps: int = 5,
                       timezone: str = "UTC", monday: date = MONDAY, cap_hours: int = 12) -> Scenario:  # fmt: skip
    """The reference benchmark: n items, 14 days, about 15 h of fixed time a week (DESIGN §24.5)."""
    rng = np.random.default_rng(seed)
    make = Maker(timezone, monday)
    now = make.at(0, "09:00")
    items = fixed_week(rng, make, range(14)) + random_flexible(rng, make, n_items, now, 13)
    sc = Scenario(f"ref-n{n_items}-s{seed}", items, now, bench_settings(timezone, cap_hours=cap_hours),
                  areas=make.areas(), meta={"n": n_items, "seed": seed})  # fmt: skip
    scale_load(sc, load, cap_hours)
    add_dependencies(rng, sc, deps)
    add_pins(rng, sc, pins)
    return sc


def tight_deadlines(seed: int, n: int = 12, fill: float = 0.92) -> Scenario:
    """Hard deadlines in the first days that nearly fill the free time before them."""
    sc = reference_instance(0, seed, load=0.0, pins=0, deps=0)
    rng = np.random.default_rng(seed + 1)
    make = Maker("UTC", MONDAY, max(i.id for i in sc.items) + 1)
    sc.end_utc = make.at(3, "04:00")
    each = sc.free_hours() * fill / n
    for k in range(n):
        d = 1 + int(rng.integers(0, 2))
        sc.items.append(make.item("assignment", f"tight-{k}", duration_units=units(q15(each * 60)),
                                  due_utc=make.at(d, "23:59") if k % 2 else sc.end_utc,
                                  importance=int(rng.integers(1, 6))))  # fmt: skip
    sc.name = f"tight-s{seed}"
    return sc


def overload(seed: int, n: int = 30, load: float = 1.6) -> Scenario:
    sc = reference_instance(n, seed, load=load, pins=3, deps=3, cap_hours=40)
    sc.name = f"overload-s{seed}"
    return sc


def fragmented(seed: int, n: int = 20) -> Scenario:
    """Fixed items leave gaps of 30–60 minutes; chunks want 30 or 60."""
    sc = reference_instance(n, seed, load=0.35, pins=0, deps=0)
    rng = np.random.default_rng(seed + 2)
    make = Maker("UTC", MONDAY, max(i.id for i in sc.items) + 1)
    for d in range(7):
        t, stop = make.at(d, "08:00"), make.at(d, "22:00")
        while t < stop:
            gap, block = int(rng.choice([30, 45, 60])), int(rng.choice([45, 60, 75]))
            sc.items.append(make.fixed("commitment", "frag", t + gap, block, event_kind="shove"))
            t += gap + block
    for item in sc.items:
        if item.when != "fixed" and item.preset in ("Assignment", "Project"):
            item.min_chunk_units = min(4, item.duration_units or 4)
    sc.name = f"fragmented-s{seed}"
    return sc


def many_dependencies(seed: int, chain: int = 15) -> Scenario:
    sc = reference_instance(10, seed, load=0.3, pins=0, deps=0)
    make = Maker("UTC", MONDAY, max(i.id for i in sc.items) + 1)
    previous = None
    for k in range(chain):
        item = make.item("assignment", f"chain-{k}", duration_units=6, due_utc=make.at(12, "23:59"))
        if previous is not None:
            sc.dependencies.append(Dependency(item.id, previous.id, 1.0 if k % 2 else 0.5, 0))
        sc.items.append(item)
        previous = item
    sc.name = f"deps-s{seed}"
    return sc


def many_one_sitting(seed: int, n: int = 30) -> Scenario:
    sc = reference_instance(10, seed, load=0.3, pins=0, deps=0)
    rng = np.random.default_rng(seed + 3)
    make = Maker("UTC", MONDAY, max(i.id for i in sc.items) + 1)
    for k in range(n):
        d = int(rng.integers(1, 13))
        sc.items.append(make.item("errand", f"os-{k}", duration_units=units(q15(rng.choice([60, 90, 120]))),
                                  release_utc=sc.now_utc, due_utc=make.at(d, "23:59")))  # fmt: skip
    sc.name = f"onesit-s{seed}"
    return sc


def many_pins(seed: int, n_pins: int = 20) -> Scenario:
    sc = reference_instance(30, seed, load=0.4, pins=0, deps=2)
    add_pins(np.random.default_rng(seed + 4), sc, n_pins)
    sc.name = f"pins-s{seed}"
    return sc


ADVERSARIAL: dict[str, Callable[[int], Scenario]] = {
    "tight": tight_deadlines,
    "overload": overload,
    "fragmented": fragmented,
    "deps": many_dependencies,
    "onesit": many_one_sitting,
    "pins": many_pins,
}


def tiny(seed: int, n_slots: int = 8, n_items: int = 2) -> Scenario:
    """A few items on a short run of 15-minute slots from 10:00: small enough to enumerate."""
    rng = np.random.default_rng(seed)
    make = Maker("UTC", MONDAY)
    now = make.at(0, "10:00")
    items = []
    for _ in range(n_items):
        kind = str(rng.choice(["assignment", "reading", "chore", "routine", "goal", "side_project", "habit"]))
        if kind in ("assignment", "reading"):
            items.append(make.item(kind, kind, duration_units=int(rng.integers(1, 4)),
                                   due_utc=now + int(rng.integers(2, n_slots + 1)) * 15,
                                   min_chunk_units=int(rng.choice([1, 2])), importance=int(rng.integers(1, 6)),
                                   chunk_cost=float(rng.choice([0.0, 0.2]))))  # fmt: skip
        elif kind in ("chore", "habit"):
            items.append(make.item(kind, kind, duration_units=int(rng.integers(1, 3))))
        elif kind == "routine":
            items.append(make.item(kind, kind, min_units=1, ideal_units=2, max_units=3, release_utc=now,
                                   due_utc=now + n_slots * 15))  # fmt: skip
        elif kind == "goal":
            items.append(make.item(kind, kind, target_units=3, release_utc=now, due_utc=now + n_slots * 15,
                                   min_chunk_units=1))  # fmt: skip
        else:
            items.append(make.item(kind, kind, daily_ceiling_units=3, min_chunk_units=1))
    settings = bench_settings(horizon_days=1, fine_days=1)
    return Scenario(f"tiny-s{seed}", items, now, settings, end_utc=now + n_slots * 15, meta={"seed": seed})


def warm_variant(sc: Scenario, seed: int, added: int = 2, removed: int = 1) -> Scenario:
    """The warm-start case: the same week with `added` new items and `removed` flexible items gone."""
    rng = np.random.default_rng(seed + 10_000)
    out = sc.copy()
    flexible = [i for i in out.items if i.when != "fixed" and i.amount == "fixed"]
    gone = {flexible[int(k)].id for k in rng.choice(len(flexible), size=min(removed, len(flexible)), replace=False)}
    out.items = [i for i in out.items if i.id not in gone]
    out.pins = [p for p in out.pins if p.item_id not in gone]
    out.dependencies = [d for d in out.dependencies if d.item_id not in gone and d.depends_on_id not in gone]
    make = Maker(out.settings["time"].timezone, MONDAY, max(i.id for i in out.items) + 100)
    out.items += random_flexible(rng, make, added, out.now_utc, 13)
    out.name = sc.name + "-warm"
    return out
