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


def scn(specs, names=(), extra=(), pins=(), days=2, now=None, scales=None, current=None, rule_dicts=None, **st):
    """A multi-day problem with only the named reference rules (plus extras), one solver worker."""
    base = dict(horizon_days=days, fine_days=days, workers=1, det_time=(10.0, 10.0, 10.0), time_limit_s=30.0)
    base.update(st)
    settings = Settings(**base)
    rules = build_rules(rule_dicts if rule_dicts is not None else [d for d in REFERENCE_RULES if d["name"] in names],
                        list(extra))
    return build_problem(specs, list(pins), at(7, "09:00") if now is None else now, settings, rules,
                         scales=scales, current=current)


def blocks(problem, plan, key):
    """Maximal runs of an item as (start_minute, end_minute)."""
    g = problem.grid
    out = []
    for s in plan[key]:
        if out and out[-1][1] == g.start[s]:
            out[-1] = (out[-1][0], int(g.end[s]))
        else:
            out.append((int(g.start[s]), int(g.end[s])))
    return out


def hours(problem, plan, key):
    return sum(int(problem.grid.units[s]) for s in plan[key]) / 4
