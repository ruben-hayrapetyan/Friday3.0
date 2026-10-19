"""Linear expressions and convex hinge curves (ENGINE_REFERENCE 7.1, engine/pwl.py).

`Lin` is the one expression type: it becomes a CP-SAT expression for a model and evaluates against a
`Solution` in plain Python, which is what makes every cost recomputable to the integer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Hashable, Iterable, Literal

log = logging.getLogger("fr.pwl")

Var = Hashable  # ("x", key, s) | ("over", key) | ("start", key, s) | ("cum", key, s) | ("any", name)


class Lin:
    __slots__ = ("terms", "const")

    def __init__(self, terms: dict[Var, int] | None = None, const: int = 0):
        self.terms: dict[Var, int] = terms if terms is not None else {}
        self.const = const

    @staticmethod
    def var(v: Var, c: int = 1) -> "Lin":
        return Lin({v: c}, 0)

    @staticmethod
    def constant(c: int) -> "Lin":
        return Lin({}, c)

    def add_term(self, v: Var, c: int = 1) -> "Lin":
        self.terms[v] = self.terms.get(v, 0) + c
        if self.terms[v] == 0:
            del self.terms[v]
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

    def __neg__(self) -> "Lin":
        return self * -1

    def __sub__(self, other: "Lin | int") -> "Lin":
        if isinstance(other, int):
            return Lin(dict(self.terms), self.const - other)
        return self + (other * -1)

    def __mul__(self, k: int) -> "Lin":
        if k == 0:
            return Lin()
        return Lin({v: c * k for v, c in self.terms.items()}, self.const * k)

    __rmul__ = __mul__

    def eval(self, value: Callable[[Var], int]) -> int:
        return self.const + sum(c * value(v) for v, c in self.terms.items())

    def bounds(self, var_bounds: Callable[[Var], tuple[int, int]]) -> tuple[int, int]:
        lo = hi = self.const
        for v, c in self.terms.items():
            vl, vh = var_bounds(v)
            a, b = c * vl, c * vh
            lo += min(a, b)
            hi += max(a, b)
        return lo, hi

    def is_const(self) -> bool:
        return not self.terms

    def __repr__(self) -> str:
        return f"Lin({self.terms}, {self.const})"


@dataclass(frozen=True)
class Hinge:
    direction: Literal["above", "below"]
    theta: float
    slope: float  # points per hour (unit measures) or per count (count measures); must be >= 0

    def __post_init__(self) -> None:
        if self.slope < 0:
            raise ValueError("hinge slopes must be non-negative (convex penalties only)")

    @property
    def whole_theta(self) -> int:
        """Thresholds are made whole: floor for `above`, ceil for `below`."""
        import math

        return math.floor(self.theta + 1e-9) if self.direction == "above" else math.ceil(self.theta - 1e-9)

    def value(self, g: int) -> int:
        th = self.whole_theta
        return max(0, g - th) if self.direction == "above" else max(0, th - g)


Curve = tuple[Hinge, ...]


@dataclass
class Measure:
    name: str
    expr: Lin
    unit: Literal["units", "count"]
    curve: Curve
    mult: float = 1.0  # per-measure factor on the rule weight (dials)


def hinge_coeff(weight: float, mult: float, slope: float, unit: str, scale: int, what: str = "") -> int:
    """Integer cost of one unit (or one count) of hinge excess. A positive coefficient never rounds to 0."""
    per = 0.25 if unit == "units" else 1.0
    raw = weight * mult * slope * per * scale
    c = round(raw)
    if c == 0 and raw > 0:
        log.warning("coefficient for %s rounds to 0; using 1", what)
        return 1
    return c


def measure_cost(m: Measure, g: int, weight: float, scale: int, rule_name: str = "") -> int:
    return sum(
        hinge_coeff(weight, m.mult, h.slope, m.unit, scale, f"{rule_name}/{m.name}") * h.value(g)
        for h in m.curve
    )


def curve_from_pairs(direction: str, pairs: Iterable[tuple[float, float]], scale_to: float = 1.0) -> Curve:
    """[(fraction, slope), ...] -> hinges at fraction * scale_to."""
    return tuple(Hinge(direction, f * scale_to, s) for f, s in pairs)  # type: ignore[arg-type]
