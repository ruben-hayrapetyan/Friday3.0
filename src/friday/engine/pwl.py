"""Linear expressions and convex hinge curves (DESIGN §12.1).

`Lin` is the one expression type. The compiler flattens it into kernel arrays, the deadline fallback turns it
into a CP-SAT expression, and the evaluator evaluates it against a `Solution`, so all three agree exactly.
"""

import logging
import math
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

# ("x", key, s) | ("over", key) | ("start", key, s) | ("cum", key, s) | ("any", group)
Var = Hashable


class Lin:
    __slots__ = ("terms", "const")

    def __init__(self, terms: dict[Var, int] | None = None, const: int = 0):
        self.terms: dict[Var, int] = terms if terms is not None else {}
        self.const = const

    @staticmethod
    def var(v: Var, coefficient: int = 1) -> "Lin":
        return Lin({v: coefficient})

    def add_term(self, v: Var, coefficient: int = 1) -> "Lin":
        total = self.terms.get(v, 0) + coefficient
        if total:
            self.terms[v] = total
        else:
            self.terms.pop(v, None)
        return self

    def __iadd__(self, other: "Lin | int") -> "Lin":
        if isinstance(other, int):
            self.const += other
            return self
        for v, c in other.terms.items():
            self.add_term(v, c)
        self.const += other.const
        return self

    def __add__(self, other: "Lin | int") -> "Lin":
        out = Lin(dict(self.terms), self.const)
        out += other
        return out

    def __mul__(self, k: int) -> "Lin":
        if k == 0:
            return Lin()
        return Lin({v: c * k for v, c in self.terms.items()}, self.const * k)

    __rmul__ = __mul__

    def __neg__(self) -> "Lin":
        return self * -1

    def __sub__(self, other: "Lin | int") -> "Lin":
        return self + (-other if isinstance(other, int) else other * -1)

    def eval(self, value: Callable[[Var], int]) -> int:
        return self.const + sum(c * value(v) for v, c in self.terms.items())

    def bounds(self, var_bounds: Callable[[Var], tuple[int, int]]) -> tuple[int, int]:
        lo = hi = self.const
        for v, c in self.terms.items():
            v_lo, v_hi = var_bounds(v)
            lo += min(c * v_lo, c * v_hi)
            hi += max(c * v_lo, c * v_hi)
        return lo, hi

    def is_const(self) -> bool:
        return not self.terms

    def __repr__(self) -> str:
        return f"Lin({self.terms}, {self.const})"


def lin_sum(parts: Iterable[Lin]) -> Lin:
    terms: dict[Var, int] = {}
    const = 0
    for part in parts:
        for v, c in part.terms.items():
            terms[v] = terms.get(v, 0) + c
        const += part.const
    return Lin({v: c for v, c in terms.items() if c}, const)


@dataclass(frozen=True)
class Hinge:
    direction: Literal["above", "below"]
    theta: float
    slope: float  # points per hour for unit measures, per count for count measures

    def __post_init__(self) -> None:
        if self.slope < 0:
            raise ValueError("hinge slopes must be non-negative (convex penalties only)")

    @property
    def whole_theta(self) -> int:
        """Thresholds are made whole: floor for `above`, ceil for `below`."""
        if self.direction == "above":
            return math.floor(self.theta + 1e-9)
        return math.ceil(self.theta - 1e-9)

    def excess(self, g: int) -> int:
        theta = self.whole_theta
        return max(0, g - theta) if self.direction == "above" else max(0, theta - g)


Curve = tuple[Hinge, ...]


@dataclass
class Measure:
    name: str
    expr: Lin
    unit: Literal["units", "count"]
    curve: Curve
    mult: float = 1.0  # this measure's factor on the rule weight (dials)


def hinge_coefficient(weight: float, mult: float, slope: float, unit: str, scale: int, what: str = "") -> int:
    """Integer cost of one unit (or one count) of hinge excess. A positive coefficient never rounds to 0."""
    raw = weight * mult * slope * (0.25 if unit == "units" else 1.0) * scale
    coefficient = round(raw)
    if coefficient == 0 and raw > 0:
        log.warning("coefficient for %s rounds to 0; using 1", what)
        return 1
    return coefficient


def measure_cost(m: Measure, g: int, weight: float, scale: int, rule_name: str = "") -> int:
    return sum(
        hinge_coefficient(weight, m.mult, h.slope, m.unit, scale, f"{rule_name}/{m.name}") * h.excess(g)
        for h in m.curve
    )


def curve_from_pairs(
    direction: Literal["above", "below"], pairs: Iterable[tuple[float, float]], scale_to: float
) -> Curve:
    """[(fraction, slope), …] → hinges at fraction × scale_to."""
    return tuple(Hinge(direction, fraction * scale_to, slope) for fraction, slope in pairs)
