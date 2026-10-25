"""Instances shared by the engine tests: the generator families plus DST, dial, θ and extra-rule variants."""

from datetime import date

import numpy as np

from friday.core.pace import DEFAULT_PACES, Dials, scales
from friday.engine.problem import Problem
from friday.planner.build import id_of
from tests.bench.generator import ADVERSARIAL, Scenario, reference_instance, reference_rules, tiny
from tests.engine.plans import random_plan

NEW_YORK = "America/New_York"
# Nov 1 2026 falls back at 02:00: in the 15-minute zone from Mon Oct 26, in the 30-minute zone from Oct 19.
DST_FINE_MONDAY, DST_COARSE_MONDAY = date(2026, 10, 26), date(2026, 10, 19)
# DST starts Mar 8 2026: a 23-hour planning day (Sat Mar 7) in the fine zone from Mon Mar 2.
SPRING_MONDAY = date(2026, 3, 2)

EXTRA_RULES = [
    dict(type="time_preference", name="sunday_rest", weight=3, params=dict(days=["sun"], price=4)),
    dict(type="time_preference", name="no_mornings", weight=1, params=dict(start="04:00", end="07:00", price="forbid")),
    dict(type="time_preference", name="late_wrap", weight=1, params=dict(start="22:00", end="02:00", price=2)),
    dict(type="finish_early", name="finish_two_days_early", weight=1, params=dict(days=2)),
    dict(type="after_event", name="after_class", weight=1, scope=dict(preset="Habit"),
         params=dict(events=dict(event_kind="class"), measure_from="last", slope=1, cap=3)),
    dict(type="after_event", name="after_any", weight=1, scope=dict(preset="Chore"),
         params=dict(events=dict(event_kind="class"), measure_from="any", slope=2, cap=4, on_days_without="cap")),
    dict(type="batch_by_day", name="batch_chores", weight=2, params=dict(by="preset"),
         scope=dict(preset=["Chore", "Errand"])),
    dict(type="batch_by_day", name="batch_area", weight=2, params=dict(by="area"), scope=dict(firmness="hard")),
    dict(type="buffer", name="breathing_room", weight=3, params=dict(minutes="15m", by_preset={"Assignment": "30m"})),
    dict(type="skippable", name="club_optional", weight=1, params=dict(titles=["club"], price=8)),
    dict(type="before_event", name="early_before_lecture", weight=1,
         params=dict(titles=["CS 1100"], after="22:00", price=2)),
]  # fmt: skip
MIXED = scales(Dials(capacity=0.8, rest=1.5, spread=2.0, growth=0.5))


def with_rules(sc: Scenario, rules: list[dict]) -> Scenario:
    from friday.core.settings import validate_value

    sc.settings = dict(sc.settings) | {"rules": validate_value("rules", rules)}
    return sc


def current_plan(sc: Scenario, seed: int) -> dict[int, list[tuple[int, int]]]:
    """A random 'previous plan' as blocks, so minimize_changes has something to measure."""
    p = sc.build()
    plan = random_plan(p, np.random.default_rng(seed), 0.3)
    return {id_of(k): [(int(p.grid.start[s]), int(p.grid.end[s])) for s in slots] for k, slots in plan.items()}


def add_quotas(p: Problem) -> Problem:
    weeks = sorted(p.grid.week_slots)
    for n, item in enumerate(p.items.values()):
        if n % 3 == 0 and item.amount == "fixed":
            item.quotas = {weeks[0]: 4, weeks[-1]: 8}
            item.progress_by_week = {weeks[0]: 1}
    return p


def thetas(p: Problem, seed: int) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    return {r.name: float(rng.lognormal(0, 0.6)) for r in p.rules}


def variant(name: str) -> Problem:
    """A named problem; every engine test that needs coverage beyond the plain generators uses these."""
    if name == "ref20":
        return reference_instance(20, 0).build()
    if name == "ref60":
        return reference_instance(60, 1).build()
    if name == "dst-fine":
        return reference_instance(30, 2, timezone=NEW_YORK, monday=DST_FINE_MONDAY).build()
    if name == "dst-coarse":
        return reference_instance(30, 3, timezone=NEW_YORK, monday=DST_COARSE_MONDAY).build()
    if name == "dst-spring":
        return reference_instance(30, 4, timezone=NEW_YORK, monday=SPRING_MONDAY).build()
    if name in ("easy", "push", "mixed"):
        sc = reference_instance(40, 5)
        day = {"easy": scales(DEFAULT_PACES["Easy"]), "push": scales(DEFAULT_PACES["Push"]), "mixed": MIXED}[name]
        sc.day_scales = [day] * 5 + [scales(Dials())] * 9
        return sc.build(debt_hours={})
    if name == "theta":
        sc = reference_instance(40, 6)
        return sc.build(multipliers=thetas(sc.build(), 6))
    if name == "extra":
        sc = with_rules(reference_instance(40, 7, timezone=NEW_YORK, monday=DST_FINE_MONDAY),
                        reference_rules(extra=EXTRA_RULES))  # fmt: skip
        return add_quotas(sc.build(current=current_plan(sc, 7), minimize_changes_scale=0.2))
    if name in ADVERSARIAL:
        return ADVERSARIAL[name](0).build()
    if name.startswith("tiny"):
        return tiny(int(name[4:]), 8, 3).build()
    raise KeyError(name)


VARIANTS = ["ref20", "ref60", "dst-fine", "dst-coarse", "dst-spring", "easy", "push", "mixed", "theta", "extra",
            *ADVERSARIAL, "tiny0", "tiny1", "tiny2"]  # fmt: skip


def single_rule(rule_type: str, seed: int = 0) -> Problem:
    """A DST-crossing week with only one rule switched on, with what that rule needs to fire."""
    spec = next((r for r in EXTRA_RULES if r["type"] == rule_type), None)
    if spec is None:
        spec = next(r for r in reference_rules() if r["type"] == rule_type)
    sc = with_rules(reference_instance(30, 10 + seed, timezone=NEW_YORK, monday=DST_FINE_MONDAY), [spec])
    sc.day_scales = [MIXED] * 3 + [scales(Dials())] * 11
    p = sc.build(current=current_plan(sc, seed) if rule_type == "minimize_changes" else None)
    return add_quotas(p) if rule_type == "quota" else p
