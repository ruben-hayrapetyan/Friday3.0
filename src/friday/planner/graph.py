"""What waits for what, as one graph (23 Nov, your design: "generate a dependency graph and then schedule things based
off of a topological ordering"; the earlier special cases kept letting a step be planned after one with no time).

Every wait the planner knows is an edge: the ones you set ("waits for"), a project's steps in their order, parts of a
set, short-term work before long-term, and a wait on a whole project, which is a wait on each of its open steps
(planner/build.py makes those). Three things are read from the graph, and only from it:

- the order things are placed in: a topological order, earliest deadline first among what's ready;
- what's held back: nothing is planned until everything it waits for has all its time, so what waits for work with no
  room before its due waits too, and what waits for that in turn;
- loops: waits that go round in a circle can't be planned in any order; they're held back and said, not planned.

The plan saves what's held back and why (assemble.py), and the pages read it from there, never working it out again.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from friday.engine.problem import Problem
from friday.engine.waits import Waits, topological


@dataclass
class Held:
    """What the plan leaves out because of a wait, and why."""

    no_room: set[str] = field(default_factory=set)  # never planned after its due, and part of it doesn't fit before
    waiting: dict[str, str] = field(default_factory=dict)  # item → the item with no room (or in a loop) it waits behind
    loops: list[list[str]] = field(default_factory=list)

    def out(self) -> set[str]:
        return set(self.waiting) | {k for loop in self.loops for k in loop}


def held(problem: Problem, over_units: Mapping[str, int]) -> Held:
    """Walk the graph in topological order: an item waits when anything it waits for has no room or waits itself.
    No room: work that's never planned after its due (pointless once late: an exam's prep, a step marked so) and part
    of which doesn't fit before it. Work still worth doing late is planned late, and what waits for it follows."""
    waits = Waits.of(problem)
    order, circles = topological(waits, sorted(problem.items))
    out = Held(loops=circles)
    in_loop = {k: loop[0] for loop in circles for k in loop}
    for key in [*order, *(k for k in problem.items if k not in order)]:
        item = problem.items[key]
        if key in in_loop:
            continue
        if item.window_is_hard and item.amount == "fixed" and item.due_utc is not None and over_units.get(key, 0) > 0:
            out.no_room.add(key)
            continue
        for source in waits.sources[key]:
            root = (
                source if source in out.no_room
                else out.waiting.get(source) or in_loop.get(source)
            )  # fmt: skip
            if root is not None:
                out.waiting[key] = root
                break
    return out
