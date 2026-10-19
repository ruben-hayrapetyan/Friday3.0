"""The reference rule set (ENGINE_REFERENCE 7.4) as Python."""
from __future__ import annotations

from typing import Any

from .rules import RULE_TYPES, Rule

REFERENCE_RULES: list[dict[str, Any]] = [
    dict(type="late_work", name="late_work", weight=10, params=dict(overflow_extra_hours=48)),
    dict(type="quota", name="quota", weight=3),
    dict(type="late_night", name="late_night", params=dict(gradient_start="22:00", a=2, b=20, debt_factor=0.5)),
    dict(type="deep_run", name="deep_run", weight=4, params=dict(threshold="3h")),
    dict(type="reserve", name="weekday_evenings", weight=2,
         params=dict(days_except=["sat", "sun"], start="18:00", end="23:00", free="2h")),
    dict(type="reserve", name="weekends", weight=2,
         params=dict(days=["sat", "sun"], start="10:00", end="23:00", free="4h")),
    dict(type="daily_load", name="daily_load", weight=5, params=dict(threshold="8h")),
    dict(type="even_load", name="even_load", weight=1),
    dict(type="energy", name="energy", weight=1),
    dict(type="soft_late", name="soft_late", weight=3),
    dict(type="unscheduled", name="unscheduled", weight=0.5, params=dict(base=1)),
    dict(type="chunk_cost", name="chunk_cost", weight=10),
    dict(type="spread", name="spread", weight=3),
    dict(type="cluster", name="cluster", weight=3, params=dict(per_day=2)),
    dict(type="target_shortfall", name="target_shortfall", params=dict(curve=[[0.4, 8], [1.0, 3]])),
    dict(type="elastic_shortfall", name="elastic_shortfall", params=dict(steep=20, gentle=2)),
    dict(type="open_value", name="open_value", params=dict(curve=[[0.5, 1], [1.0, 0.5]])),
    dict(type="minimize_changes", name="minimize_changes", weight=1, params=dict(preferred_multiplier=10)),
]


def build_rules(spec: list[dict[str, Any]] | None = None, extra: list[dict[str, Any]] | None = None) -> list[Rule]:
    """Instantiate rules from dict specs. Weights and slopes are validated here, once."""
    out = []
    for d in (spec if spec is not None else REFERENCE_RULES) + (extra or []):
        d = dict(d)
        cls = RULE_TYPES[d.pop("type")]
        name = d.pop("name")
        params = d.pop("params", {})
        out.append(cls(name, **d, **params))
    return out


def only(names: list[str], extra: list[dict[str, Any]] | None = None) -> list[Rule]:
    """A small rule set for scenario tests: just the named reference rules (and any extras)."""
    return build_rules([d for d in REFERENCE_RULES if d["name"] in names], extra)
