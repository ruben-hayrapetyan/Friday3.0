"""Rules that contradict each other, read from the rules themselves rather than from a plan (the Rules page): two
rules about the same work whose hours together leave it no time ("Deep work in the morning" and "No work before
noon"), every day or on some days ("Reading 9–11am on Saturdays" and "Keep Saturday mornings free"). Alongside, the
rules that overlap: one kind of rule twice for the same work, with different amounts ("At most 8 h a day" and "At most
6 h a day", where the stricter is the one that counts) or the same hours twice. `rule_clash` finds what a rule is up
against in this week's plan; this needs no plan, so it can warn before a rule is added.

Hours are compared as the planner reads them (`time_preference` and a `reserve` kept wholly free): each weekday's
quarter hours a rule keeps its work out of. A day one rule rules out on its own ("No work on Sundays") isn't a
contradiction with the other rules about that day; only what the two do together counts."""

from dataclasses import dataclass
from typing import Any

from friday.core.rule_text import DAYS, days_spoken
from friday.core.time import MINUTES_PER_DAY, UNIT_MIN
from friday.engine.rules import as_list, in_hour_window, matching_weekdays, parse_clock, parse_units

QUARTER = 15
FULL = (1 << (MINUTES_PER_DAY // QUARTER)) - 1  # every quarter hour of a day
EXCLUDING = {"except_preset"}  # a scope that only leaves kinds out is still about work in general
AMOUNTS = {"daily_load": "threshold", "finish_early": "days", "sleep_min": "hours"}


@dataclass(frozen=True)
class Conflict:
    other: str  # the other rule's name
    why: str  # in plain words, to follow "Contradicts “…”:" or "Overlaps “…”:"
    days: tuple[str, ...] = ()  # the weekdays it bites on; () for all of them
    overlap: bool = False  # the same kind of rule for the same work: not a contradiction, the stricter counts


def contradictions(rules: list[dict[str, Any]], wins: list[dict[str, str]]) -> dict[str, list[Conflict]]:
    """Each switched-on rule's contradictions with the others, by rule name; a pair you said which wins is settled."""
    settled = {frozenset((w["winner"], w["loser"])) for w in wins}
    on = [r for r in rules if r.get("enabled", True)]
    out: dict[str, list[Conflict]] = {}
    for i, a in enumerate(on):
        for b in on[i + 1 :]:
            if frozenset((a["name"], b["name"])) in settled:
                continue
            found = conflict(a, b)
            if found and not found.overlap:
                out.setdefault(a["name"], []).append(found)
                out.setdefault(b["name"], []).append(Conflict(a["name"], found.why, found.days))
    return out


def against(new: dict[str, Any], rules: list[dict[str, Any]]) -> list[Conflict]:
    """What a rule about to be added contradicts or overlaps among the switched-on rules."""
    return [c for r in rules if r.get("enabled", True) and (c := conflict(new, r))]


def conflict(a: dict[str, Any], b: dict[str, Any]) -> Conflict | None:
    """How b stands against a: its contradiction, its overlap, or None. The Conflict names b."""
    subject = shared(a.get("scope"), b.get("scope"))
    if subject is None:
        return None
    same_scope = same_work(a.get("scope"), b.get("scope"))
    if same_scope and a["type"] == b["type"] and a["type"] in AMOUNTS:
        return amounts(a, b, subject)
    ma, mb = hours(a), hours(b)
    if ma is None or mb is None:
        return None
    if same_scope and ma == mb:
        return Conflict(b["name"], f"the same hours for {subject}", overlap=True)
    days = no_time(ma, mb)
    if days is None:
        return None
    on = "" if days == DAYS else f" on {days_spoken(days)}"
    return Conflict(b["name"], f"together they leave no time for {subject}{on}", days if days != DAYS else ())


def amounts(a: dict[str, Any], b: dict[str, Any], subject: str) -> Conflict | None:
    key = AMOUNTS[a["type"]]
    x, y = a["params"].get(key), b["params"].get(key)
    if x is None or y is None:
        return None
    if a["type"] == "daily_load":
        lo, hi = sorted((parse_units(x), parse_units(y)))
        if lo == hi:
            return Conflict(b["name"], f"the same daily limit for {subject}", overlap=True)
        said = f"{short(lo)} and {short(hi)}"
        return Conflict(b["name"], f"both limit {subject} a day ({said}); the lower one is what counts", overlap=True)
    if a["type"] == "sleep_min":
        lo, hi = sorted((float(x), float(y)))
        if lo == hi:
            return Conflict(b["name"], "the same night's sleep", overlap=True)
        return Conflict(b["name"], f"both keep sleep ({lo:g} and {hi:g} h a night); the longer one is what counts",
                        overlap=True)  # fmt: skip
    lo, hi = sorted((int(x), int(y)))
    if lo == hi:
        return Conflict(b["name"], f"the same head start for {subject}", overlap=True)
    why = f"both say how early to finish {subject} ({lo} and {hi} days before it’s due); the earlier one is what counts"
    return Conflict(b["name"], why, overlap=True)


def short(units: int) -> str:
    return f"{units * UNIT_MIN / 60:g} h"


def no_time(a: list[int], b: list[int]) -> tuple[str, ...] | None:
    """The weekdays two rules together leave no time on (neither alone does), or every day when together they leave
    none all week; None when there's time left."""
    both = [x | y for x, y in zip(a, b, strict=True)]
    if all(d == FULL for d in both) and not all(d == FULL for d in a) and not all(d == FULL for d in b):
        return DAYS
    days = tuple(DAYS[w] for w in range(7) if both[w] == FULL and a[w] != FULL and b[w] != FULL)
    return days or None


def hours(rule: dict[str, Any]) -> list[int] | None:
    """Each weekday's quarter hours (Monday first) the rule keeps its work out of; None for a rule not about hours."""
    p = rule.get("params") or {}
    if rule["type"] == "reserve":
        if not wholly_free(p):
            return None
    elif rule["type"] != "time_preference":
        return None
    weekdays = matching_weekdays(p.get("days"), p.get("days_except"))
    start = parse_clock(p["start"]) if p.get("start") is not None else None
    end = parse_clock(p["end"]) if p.get("end") is not None else None
    day = sum(1 << q for q in range(MINUTES_PER_DAY // QUARTER) if in_hour_window(q * QUARTER, start, end))
    return [day if w in weekdays else 0 for w in range(7)]


def wholly_free(p: dict[str, Any]) -> bool:
    """A reserve that keeps all of its window free (`keep saturday mornings free`), not some of it (`lighter`)."""
    start, end = p.get("start"), p.get("end")
    window = (parse_clock(end) - parse_clock(start)) % MINUTES_PER_DAY if start is not None and end is not None else 0
    return parse_units(p.get("free", "8h")) * UNIT_MIN >= (window or MINUTES_PER_DAY)


def general(scope: dict[str, Any] | None) -> bool:
    return not scope or set(scope) <= EXCLUDING


def shared(a: dict[str, Any] | None, b: dict[str, Any] | None) -> str | None:
    """The work two rules are both about, in words; None when they're about different work."""
    if general(a) and general(b):
        return "work"
    if general(a) or general(b):
        wide, narrow = (a, b) if general(a) else (b, a)
        left_out = as_list((wide or {}).get("except_preset")) or []
        if any(p in left_out for p in as_list((narrow or {}).get("preset")) or []):
            return None
        return words(narrow or {})
    return words(a or {}) if same_work(a, b) else None


def same_work(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if general(a) and general(b):
        return True
    return not general(a) and not general(b) and normal(a or {}) == normal(b or {})


def normal(scope: dict[str, Any]) -> dict[str, list[str]]:
    return {k: sorted(str(v).lower() for v in as_list(scope[k]) or []) for k in scope if k not in EXCLUDING}


def words(scope: dict[str, Any]) -> str:
    """deep work; reading; gym."""
    if as_list(scope.get("energy")) == ["deep"]:
        return "deep work"
    for key in ("title", "area", "preset", "tags", "energy"):
        found = as_list(scope.get(key))
        if found:
            return " or ".join(str(v).lower() for v in found)
    return "that work"
