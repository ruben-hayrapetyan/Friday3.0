"""What waits for what, as a graph, and an order that respects it (23 Nov, your design: "generate a dependency graph
and then schedule things based off of a topological ordering"). The engine places work in this order
(construct.placement_order); the planner reads what's held back from it (planner/graph.py)."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from friday.engine.problem import Problem


@dataclass(frozen=True)
class Waits:
    """The graph: for each item, the items it waits for (its sources)."""

    sources: Mapping[str, tuple[str, ...]]

    @staticmethod
    def of(problem: Problem) -> "Waits":
        items = problem.items
        return Waits({k: tuple(d.key for d in it.depends_on if d.key in items) for k, it in items.items()})

    def dependents(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {k: [] for k in self.sources}
        for key, sources in self.sources.items():
            for s in sources:
                out.setdefault(s, []).append(key)
        return out


def topological(waits: Waits, preferred: Sequence[str]) -> tuple[list[str], list[list[str]]]:
    """Every item after everything it waits for; among those ready, the one earliest in `preferred` (e.g. by deadline).
    Returns the order and the loops: items in a circle of waits, which no order can satisfy, left out of it."""
    rank = {k: i for i, k in enumerate(preferred)}
    rank |= {k: len(rank) + i for i, k in enumerate(sorted(k for k in waits.sources if k not in rank))}
    left = {k: len(set(s)) for k, s in waits.sources.items()}
    dependents = waits.dependents()
    ready = sorted((k for k, n in left.items() if n == 0), key=rank.__getitem__)
    order: list[str] = []
    while ready:
        key = ready.pop(0)
        order.append(key)
        for d in dependents.get(key, []):
            left[d] -= 1
            if left[d] == 0:
                ready.append(d)
        ready.sort(key=rank.__getitem__)
    stuck = [k for k, n in left.items() if n > 0]
    return order, loops(waits, stuck)


def loops(waits: Waits, among: Iterable[str]) -> list[list[str]]:
    """The circles of waits among items no order could place (Tarjan's strongly connected components), each as a list;
    what merely waits for a circle isn't in one."""
    among = set(among)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    out: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in waits.sources.get(v, ()):
            if w not in among:
                continue
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            part = []
            while True:
                w = stack.pop()
                on.discard(w)
                part.append(w)
                if w == v:
                    break
            if len(part) > 1 or v in waits.sources.get(v, ()):
                out.append(sorted(part))

    for v in sorted(among):
        if v not in index:
            visit(v)
    return out
