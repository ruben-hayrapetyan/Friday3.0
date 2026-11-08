"""Late work's last chance (8 Nov: "If math homework becomes overdue, it must be done before sunday"). A rule of type
`late_cutoff` names the work (its scope) and a weekday: once that work is past its due it may still be planned, as
urgently as any late work, but never on or after that day ("before sunday") or after it ends ("by sunday"). The day is
the first such weekday after the due's own day ("before") or on or after it ("by"), in your time. Past it, the work
isn't planned at all: like work that's pointless once late, with a few days' grace."""

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from friday.core.time import WEEKDAYS, local_midnight, to_local, to_utc
from friday.engine.problem import Problem
from friday.engine.rules import Scope

PLANNER_TYPE = "late_cutoff"


def cutoff_after(due_utc: int, day: str, before: bool, tz: str) -> int:
    """'before sunday': the start of the first Sunday after the due's day; 'by sunday': the end of the first Sunday on
    or after it. UTC minutes."""
    due_day = to_local(due_utc, tz).date()
    ahead = (WEEKDAYS.index(day) - due_day.weekday()) % 7
    if before and ahead == 0:
        ahead = 7  # due on a Sunday: before Sunday is the next one
    that_day = due_day + timedelta(days=ahead)
    return to_utc(local_midnight(that_day + timedelta(days=0 if before else 1)), tz)


def set_cutoffs(problem: Problem, rules: Iterable[Any], tz: str) -> None:
    """Each item a `late_cutoff` rule covers, given the earliest of their cutoffs."""
    for rule in rules:
        if rule.type != PLANNER_TYPE or not rule.enabled:
            continue
        scope = Scope(**rule.scope) if rule.scope else None
        day, before = rule.params.get("day", "sun"), bool(rule.params.get("before", True))
        for item in problem.items.values():
            if item.due_utc is None or (scope is not None and not scope.matches(item, problem)):
                continue
            last = cutoff_after(item.due_utc, day, before, tz)
            item.cutoff_utc = last if item.cutoff_utc is None else min(item.cutoff_utc, last)
