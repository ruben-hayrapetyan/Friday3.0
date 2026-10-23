"""Small problems for rule and wall tests: a few items on a short run of slots, with chosen rules only."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from friday.core.pace import DayScales
from friday.core.settings import validate_value
from friday.engine.problem import Problem
from friday.planner.build import Dependency, Pin
from tests.bench.generator import Maker, Scenario, bench_settings, reference_rules

MONDAY = date(2026, 10, 19)
make = Maker("UTC", MONDAY)
MON10 = make.at(0, "10:00")


def at(day: int, hhmm: str) -> int:
    return make.at(day, hhmm)


def item(preset: str, item_id: int, **fields: Any):  # noqa: ANN201
    maker = Maker("UTC", MONDAY, item_id)
    return maker.item(preset, fields.pop("title", f"{preset}-{item_id}"), fields.pop("area", None), **fields)


def problem(items: Sequence[Any], rule_names: Sequence[str] = (), extra: Sequence[Mapping[str, Any]] = (),
            pins: Sequence[Pin] = (), deps: Sequence[Dependency] = (), now: int = MON10, slots: int | None = 8,
            days: int = 1, fine_days: int | None = None, cap_hours: float = 12,
            scales: Sequence[DayScales] | None = None, current: Mapping[int, Sequence[tuple[int, int]]] | None = None,
            short_night: bool = False, **build: Any) -> Problem:  # fmt: skip
    """`slots` 15-minute slots from `now` (or whole days when None), with only the named reference rules.

    `short_night` makes the sleep core 02:00–03:00, so time on both sides of the 04:00 zone boundary is free.
    """
    rules = reference_rules(rule_names, extra) if rule_names or extra else []
    settings = bench_settings(horizon_days=days, fine_days=days if fine_days is None else fine_days,
                              cap_hours=cap_hours, rules=rules)  # fmt: skip
    if short_night:
        night = {"bedtime": "02:00", "wake": "03:00", "margin_min": 0}
        settings["sleep"] = validate_value(
            "sleep", dict.fromkeys(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), night)
        )
    end = None if slots is None else now + slots * 15
    sc = Scenario("test", list(items), now, settings, list(deps), list(pins), day_scales=scales, end_utc=end)
    return sc.build(current=current, **build)


def plan(**slots: Sequence[int]) -> dict[str, tuple[int, ...]]:
    """plan(item_1=(0, 1)) → {"item:1": (0, 1)}."""
    return {key.replace("item_", "item:"): tuple(v) for key, v in slots.items()}


def zone_problem(items: Sequence[Any], rule_names: Sequence[str] = (), extra: Sequence[Mapping[str, Any]] = (),
                 **kw: Any) -> Problem:  # fmt: skip
    """Mon 23:00 through Tuesday: 15-minute slots 0–19 until Tue 04:00, then 30-minute slots from index 20."""
    return problem(items, rule_names, extra, now=at(0, "23:00"), slots=None, days=2, fine_days=1, short_night=True,
                   **kw)  # fmt: skip


BOUNDARY = 20  # the first 30-minute slot in zone_problem
