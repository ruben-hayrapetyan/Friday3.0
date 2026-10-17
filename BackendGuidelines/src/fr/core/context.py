"""BuildContext: what rules see when they emit measures (ENGINE_REFERENCE 7.1).

It only builds `Lin` expressions over named variables and records which helper variables a model must
define. It never touches a solver, so the evaluator and the CP-SAT builder share one source of truth.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .pwl import Lin

if TYPE_CHECKING:
    from .problem import EngineItem, Problem
    from .rules import Scope


class BuildContext:
    def __init__(self, problem: "Problem"):
        self.problem = problem
        self.grid = problem.grid
        self.starts_requested: set[str] = set()
        self.cum_requested: set[str] = set()
        self.any_defs: dict[str, tuple[tuple[str, int], ...]] = {}

    def x(self, key: str, s: int) -> Lin:
        if s in self.problem.items[key].allowed_set:
            return Lin.var(("x", key, s))
        return Lin()

    def placed_in(self, key: str, slots: Iterable[int]) -> Lin:
        """Units of `key` placed in `slots`."""
        item = self.problem.items[key]
        out = Lin()
        u = self.grid.units
        for s in slots:
            if s in item.allowed_set:
                out.add_term(("x", key, s), int(u[s]))
        return out

    def over(self, key: str) -> Lin:
        return Lin.var(("over", key))

    def start(self, key: str, s: int) -> Lin:
        """1 when a chunk of `key` begins at slot s. Asking for it makes models define it."""
        self.starts_requested.add(key)
        if s in self.problem.items[key].allowed_set:
            return Lin.var(("start", key, s))
        return Lin()

    def cum(self, key: str, t: int) -> Lin:
        """Units of `key` placed strictly before slot t."""
        self.cum_requested.add(key)
        if t <= 0:
            return Lin()
        return Lin.var(("cum", key, t))

    def any_of(self, name: str, pairs: Iterable[tuple[str, int]]) -> Lin:
        pairs = tuple(p for p in pairs if p[1] in self.problem.items[p[0]].allowed_set)
        if not pairs:
            return Lin()
        self.any_defs[name] = pairs
        return Lin.var(("any", name))

    def busy_units(self, slots: Iterable[int]) -> Lin:
        out = Lin()
        u = self.grid.units
        for s in slots:
            for it in self.problem.items.values():
                if s in it.allowed_set:
                    out.add_term(("x", it.key, s), int(u[s]))
        return out

    def items_in(self, scope: "Scope | None") -> list["EngineItem"]:
        return [i for i in self.problem.items.values() if scope is None or scope.matches(i)]
