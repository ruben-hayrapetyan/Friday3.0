"""Rules: the base class, scopes, the registry, and what rules see when they build measures (DESIGN §12.1).

Every rule is a slot price, a ban, or a linear measure with a convex hinge curve. The evaluator, the kernel's
compiler and the CP-SAT fallback all read the same rule objects, so what is optimized is what is reported.
"""

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

import numpy as np
from pydantic import BaseModel, BeforeValidator, ConfigDict

from friday.core.textnorm import identity_text, norm
from friday.core.time import MINUTES_PER_DAY, UNIT_MIN, WEEKDAYS
from friday.engine.pwl import Lin, Measure

if TYPE_CHECKING:
    from friday.engine.problem import EngineItem, FixedOcc, Problem

FORBID = "forbid"
DURATION = re.compile(r"^\s*(?:(\d+(?:\.\d+)?)\s*h)?\s*(?:(\d+(?:\.\d+)?)\s*m)?\s*$")


def parse_units(value: Any) -> int:
    """`3h`, `40m` or `1h30m` → units, rounded up; a bare number is already units."""
    if isinstance(value, int | float):
        return int(value)
    match = DURATION.match(str(value))
    if not match or not (match[1] or match[2]):
        raise ValueError(f"not a duration: {value!r}")
    minutes = float(match[1] or 0) * 60 + float(match[2] or 0)
    return math.ceil(minutes / UNIT_MIN - 1e-9)


def parse_clock(value: Any) -> int:
    if isinstance(value, int):
        return value
    hours, minutes = str(value).split(":")
    return int(hours) * 60 + int(minutes)


def parse_days(value: Any) -> tuple[int, ...] | None:
    if value is None:
        return None
    return tuple(WEEKDAYS.index(d.lower()[:3]) if isinstance(d, str) else int(d) for d in value)


def matching_weekdays(days: Any, days_except: Any) -> set[int]:
    included, excluded = parse_days(days), parse_days(days_except)
    return {d for d in range(7) if (included is None or d in included) and (excluded is None or d not in excluded)}


def in_hour_window(local_minute: int, start: int | None, end: int | None) -> bool:
    """Is a minute of the day inside [start, end)? The window may wrap midnight."""
    if start is None and end is None:
        return True
    lo = 0 if start is None else start
    hi = MINUTES_PER_DAY if end is None else end
    if lo <= hi:
        return lo <= local_minute < hi
    return local_minute >= lo or local_minute < hi


Units = Annotated[int, BeforeValidator(parse_units)]
Clock = Annotated[int, BeforeValidator(parse_clock)]


def as_list(value: Any) -> list[Any] | None:
    if value is None:
        return None
    return list(value) if isinstance(value, list | tuple | set | frozenset) else [value]


@dataclass
class Scope:
    area: Any = None
    tags: Any = None  # any of
    preset: Any = None
    energy: Any = None
    firmness: Any = None
    amount: Any = None
    # Found as words in the title, compared as identity text (DESIGN §6.6): "chem" is in "Chem 2090 Problem Set 10".
    # It had to be the whole title, so a rule about chem or homework reached nothing (26 Oct).
    title: Any = None
    title_regex: Any = None
    except_preset: Any = None  # none of these kinds

    def matches(self, item: "EngineItem", problem: "Problem") -> bool:
        skipped = as_list(self.except_preset)
        if skipped is not None and item.preset in skipped:
            return False
        for wanted, value in (
            (self.area, item.area),
            (self.preset, item.preset),
            (self.energy, item.energy),
            (self.firmness, item.firmness),
            (self.amount, item.amount),
        ):
            options = as_list(wanted)
            if options is not None and value not in options:
                return False
        tags = as_list(self.tags)
        if tags is not None and not any(t in item.tags for t in tags):
            return False
        titles = as_list(self.title)
        if titles is not None and not any(within(item.norm_title, t) for t in normalized_titles(titles, problem)):
            return False
        patterns = as_list(self.title_regex)
        return patterns is None or any(re.search(p, item.title) for p in patterns)


@dataclass
class EventScope:
    event_kind: Any = None
    title: Any = None
    tags: Any = None

    def matches(self, event: "FixedOcc", problem: "Problem") -> bool:
        kinds, titles, tags = as_list(self.event_kind), as_list(self.title), as_list(self.tags)
        if kinds is not None and event.kind not in kinds:
            return False
        if titles is not None and event_title(event, problem) not in normalized_titles(titles, problem):
            return False
        return tags is None or any(t in event.tags for t in tags)


def within(title: str, words: str) -> bool:
    """Whether a title has these words in it, as words: "pe" isn't in "Open"."""
    return title == words or (bool(words) and re.search(rf"(?<!\w){re.escape(words)}(?!\w)", title) is not None)


def normalized_titles(titles: list[str], problem: "Problem") -> set[str]:
    return {identity_text(norm(t, problem.text)) for t in titles}


def event_title(event: "FixedOcc", problem: "Problem") -> str:
    return event.norm_title or identity_text(norm(event.title, problem.text))


RULE_TYPES: dict[str, type["Rule"]] = {}


def rule_type(name: str):  # noqa: ANN201
    def register(cls: type["Rule"]) -> type["Rule"]:
        cls.type = name
        RULE_TYPES[name] = cls
        return cls

    return register


class Rule:
    type: ClassVar[str]
    default_stage: ClassVar[str] = "preferences"
    default_scope: ClassVar[dict[str, Any] | None] = None
    applies_to: ClassVar[set[str]] = {"fixed", "elastic", "target", "open"}

    class Params(BaseModel):
        model_config = ConfigDict(extra="forbid")

    def __init__(
        self,
        name: str,
        *,
        weight: float = 1.0,
        stage: str | None = None,
        scope: Scope | Mapping[str, Any] | None = None,
        reason: str | None = None,
        **params: Any,
    ):
        if weight < 0:
            raise ValueError(f"{name}: weights must be ≥ 0")
        self.name = name
        self.weight = weight
        self.stage = stage or self.default_stage
        scope = scope if scope is not None else self.default_scope
        self.scope = Scope(**scope) if isinstance(scope, Mapping) else scope
        self.reason = reason or name
        self.p = self.Params(**params)
        self.problem: Problem = None  # type: ignore[assignment]
        self.theta = 1.0

    def prepare(self, problem: "Problem") -> None:
        self.problem = problem
        self.theta = problem.multiplier(self.name, self.type)

    @property
    def effective_weight(self) -> float:
        """The hand-set weight times its learned multiplier θ; dial factors are applied per day on top."""
        return self.weight * self.theta

    def price(self, item: "EngineItem", s: int) -> float:
        """Points per hour for `item` in slot s; s == S is the overflow slot."""
        return 0.0

    def forbids(self, item: "EngineItem", s: int) -> bool:
        return False

    def measures(self, ctx: "BuildContext") -> Iterable[Measure]:
        return ()

    def day_price(self, day: date) -> float:
        """Points per hour for in-scope work anywhere on `day`, for the allocator; inf when the day is forbidden."""
        return 0.0

    def day_mult(self, day: int) -> float:
        """The factor the day's dials put on this rule's price (1 unless a dial reaches it)."""
        return 1.0

    def applies_also(self, item: "EngineItem") -> bool:
        return True

    def applies(self, item: "EngineItem") -> bool:
        return (
            item.amount in self.applies_to
            and (self.scope is None or self.scope.matches(item, self.problem))
            and self.applies_also(item)
        )

    @property
    def has_price(self) -> bool:
        return type(self).price is not Rule.price

    @property
    def has_forbid(self) -> bool:
        return type(self).forbids is not Rule.forbids

    def scoped_items(self) -> list["EngineItem"]:
        return [i for i in self.problem.items.values() if self.applies(i)]

    def __repr__(self) -> str:
        return f"{self.type}({self.name}, w={self.weight}, {self.stage})"


class BuildContext:
    """The variable constructors rules use for measures. It never touches the kernel or CP-SAT."""

    def __init__(self, problem: "Problem"):
        self.problem = problem
        self.grid = problem.grid
        self.starts_requested: set[str] = set()
        self.cum_requested: set[str] = set()
        self.any_groups: dict[str, tuple[tuple[str, int], ...]] = {}

    def x(self, key: str, s: int) -> Lin:
        return Lin.var(("x", key, s)) if s in self.problem.items[key].allowed_set else Lin()

    def placed_in(self, key: str, slots: Iterable[int]) -> Lin:
        """Units of `key` placed in `slots`."""
        allowed, units = self.problem.items[key].allowed_set, self.grid.units
        return Lin({("x", key, s): int(units[s]) for s in slots if s in allowed})

    def over(self, key: str) -> Lin:
        return Lin.var(("over", key))

    def start(self, key: str, s: int) -> Lin:
        """1 when a chunk of `key` begins at slot s."""
        self.starts_requested.add(key)
        return Lin.var(("start", key, s)) if s in self.problem.items[key].allowed_set else Lin()

    def cum(self, key: str, t: int) -> Lin:
        """Units of `key` placed strictly before slot t."""
        self.cum_requested.add(key)
        return Lin.var(("cum", key, t)) if t > 0 else Lin()

    def any_of(self, group: str, pairs: Iterable[tuple[str, int]]) -> Lin:
        """1 when any of the (item, slot) pairs is occupied."""
        usable = tuple(p for p in pairs if p[1] in self.problem.items[p[0]].allowed_set)
        if not usable:
            return Lin()
        self.any_groups[group] = usable
        return Lin.var(("any", group))

    def busy_units(self, slots: Iterable[int], items: Iterable["EngineItem"] | None = None) -> Lin:
        among = list(self.problem.items.values() if items is None else items)
        out = Lin()
        for s in slots:
            for item in among:
                if s in item.allowed_set:
                    out.add_term(("x", item.key, s), int(self.grid.units[s]))
        return out


def price_row(problem: "Problem", rule: Rule, item: "EngineItem") -> np.ndarray:
    """Integer cost of `item` in each slot; entry S is the cost per overflow unit.

    Slot s costs round(weight × θ × dial × price × hours(s) × scale); an overflow unit costs
    round(weight × θ × price(S) × 0.25 × scale).
    """
    key = (rule.name, item.key)
    if key not in problem.price_cache:
        grid = problem.grid
        row = np.zeros(grid.S + 1, dtype=np.int64)
        for s in item.allowed:
            weight = rule.effective_weight * rule.day_mult(grid.slots[s].day)
            row[s] = round(weight * rule.price(item, s) * 0.25 * int(grid.units[s]) * problem.scale)
        row[grid.S] = round(rule.effective_weight * rule.price(item, grid.S) * 0.25 * problem.scale)
        problem.price_cache[key] = row
    return problem.price_cache[key]


def build_rules(specs: Iterable[Mapping[str, Any]]) -> list[Rule]:
    """Rule objects from settings-style specs: {type, name, weight?, stage?, scope?, reason?, params?}."""
    out = []
    for raw in specs:
        spec = dict(raw)
        kind = spec.pop("type")
        if kind not in RULE_TYPES:
            raise ValueError(f"rules: unknown rule type {kind!r}")
        name = spec.pop("name")
        params = spec.pop("params", None) or {}
        options = {k: v for k, v in spec.items() if v is not None}
        out.append(RULE_TYPES[kind](name, **options, **params))
    return out


from friday.engine.rules import measures, prices  # noqa: E402, F401  (registers the built-in types)
