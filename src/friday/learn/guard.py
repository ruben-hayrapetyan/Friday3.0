"""What learning may do to what you said (29 Oct: "make sure that there is guards against any of friday's learned
behaviours and the rules contradicting (and whether the rules need to be updated or the behaviours)").

Learning weighs the planner's rules from how you move things (learn/preferences.py). It had taken rules you wrote
("Keep Fri, Sat 8pm–11:59pm lighter", Strongly; "Lunch and dinner are never skipped for work") and ones set by your
answers (winding down before bed, finishing a day early) down to a thirtieth: what you said, quietly overruled. Now a
rule you wrote, or one your answers and settings set, is weighed at no less than half and no more than double what
you set, whatever was learned; past that it's a question for you (commands/conflicts.py), not a quiet change. Kept
as written, it's weighed as set; let go, it's weighed as learned."""

from collections.abc import Iterable, Mapping
from typing import Any

# Set by your answers and settings, and (8 Nov, your choice) the built-in rules that shape your sittings and meals:
# learning cut "fewer, longer sessions" and "don't skip meals" to 4% from 44 drags, and the plan took turns between
# two tasks every quarter hour.
# Setup's answers too (audit, 8 Nov): a normal day's hours, the longest stretch, free evenings and weekends.
STATED_TYPES = frozenset({"late_night", "finish_early", "sleep_min", "chunk_cost", "same_course", "elastic_minimum",
                          "elastic_shortfall", "spread", "daily_load", "deep_run", "reserve"})  # fmt: skip
BAND = (0.5, 2.0)  # how far learning may move what you said, until you decide
HELD = "rules_held"  # kv: rules you said to keep as written
FREED = "rules_learned_free"  # kv: rules you let Friday weigh as learned


def stated(rule: Any) -> bool:
    """A rule you wrote, or one your answers and settings set."""
    return str(rule.name).startswith("you:") or rule.type in STATED_TYPES


def guarded(
    theta: Mapping[str, float], rules: Iterable[Any], held: Iterable[str] = (), freed: Iterable[str] = ()
) -> dict[str, float]:
    """`theta` as the planner may use it: a rule kept as written at 1, what you said within `BAND`."""
    out, held, freed = dict(theta), set(held), set(freed)
    for rule in rules:
        if rule.name not in out:
            continue
        if rule.name in held:
            out[rule.name] = 1.0
        elif stated(rule) and rule.name not in freed:
            out[rule.name] = min(max(out[rule.name], BAND[0]), BAND[1])
    return out


def outside(theta: Mapping[str, float], rules: Iterable[Any], held: Iterable[str] = (), freed: Iterable[str] = ()):
    """What you said that learning would move past `BAND`, with its learned weight, the rules' order kept."""
    held, freed = set(held), set(freed)
    return [
        (rule, theta[rule.name])
        for rule in rules
        if rule.enabled and stated(rule) and rule.name in theta and rule.name not in held | freed
        and not BAND[0] <= theta[rule.name] <= BAND[1]
    ]  # fmt: skip
