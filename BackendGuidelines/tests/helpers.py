from __future__ import annotations

from fr.core.builder import build_problem
from fr.core.defaults import REFERENCE_RULES, build_rules
from fr.core.settings import Settings


def at(date: int, hhmm: str) -> int:
    h, m = hhmm.split(":")
    return date * 1440 + int(h) * 60 + int(m)


MON10 = at(7, "10:00")


def problem(specs, rule_names=(), extra=(), pins=(), now=MON10, slots=8, settings=None, current=None, scales=None):
    """A short run of 15-minute slots from `now` with only the named reference rules."""
    st = settings or Settings(horizon_days=1, fine_days=1)
    rules = build_rules([d for d in REFERENCE_RULES if d["name"] in rule_names], list(extra))
    return build_problem(specs, list(pins), now, st, rules, scales=scales, current=current, end=now + slots * 15)
