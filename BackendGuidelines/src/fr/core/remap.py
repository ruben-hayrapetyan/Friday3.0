"""Re-express a plan made on one grid on another grid of the same problem (different horizon or slot lengths).

A destination slot goes to an item when the source plan gives that item the whole slot's minutes.
Used to compare baseline variants that differ in grid shape on one common evaluator.
"""
from __future__ import annotations

import numpy as np

from .problem import Problem


def remap_plan(plan, src: Problem, dst: Problem) -> dict[str, tuple[int, ...]]:
    sg, dg = src.grid, dst.grid
    keys = list(src.items)
    owner = np.full(sg.S, -1, dtype=np.int64)
    for k, slots in plan.items():
        for s in slots:
            owner[s] = keys.index(k)
    out: dict[str, list[int]] = {k: [] for k in dst.items}
    starts = sg.start[: sg.S]
    for s in range(dg.S):
        a, b = int(dg.start[s]), int(dg.end[s])
        lo = int(np.searchsorted(sg.end[: sg.S], a, side="right"))
        covered, who = 0, set()
        t = lo
        while t < sg.S and starts[t] < b:
            covered += int(min(sg.end[t], b) - max(starts[t], a))
            who.add(int(owner[t]))
            t += 1
        if covered == b - a and len(who) == 1 and (w := next(iter(who))) >= 0:
            k = keys[w]
            if k in out and s in dst.items[k].allowed_set:
                out[k].append(s)
    return {k: tuple(v) for k, v in out.items()}
