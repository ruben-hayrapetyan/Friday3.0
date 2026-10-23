"""Helpers for scenario tests: run the scheduler, read blocks and hours back out of a plan."""

from dataclasses import replace

from friday.engine.checker import check
from friday.engine.problem import Problem
from friday.engine.scheduler import Schedule, SchedulerConfig, schedule
from tests.engine.configs import fast
from tests.engine.helpers import at, item, problem

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def run(p: Problem, config: SchedulerConfig | None = None, warm: bool = False) -> Schedule:
    result = schedule(p, config or fast(steps=100_000), warm=warm)
    assert check(p, result.plan, result.protected) == []
    return result


def blocks(p: Problem, plan: dict, key: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s in plan[key]:
        if out and out[-1][1] == int(p.grid.start[s]):
            out[-1] = (out[-1][0], int(p.grid.end[s]))
        else:
            out.append((int(p.grid.start[s]), int(p.grid.end[s])))
    return out


def hours(p: Problem, plan: dict, key: str) -> float:
    return sum(int(p.grid.units[s]) for s in plan[key]) / 4


def wall(item_id: int, day: int, start: str = "07:00", end: str = "23:59", next_day: bool = False):  # noqa: ANN201
    """A blocking commitment, so only the time around it is free."""
    return item("commitment", item_id, title="wall", start_utc=at(day, start), end_utc=at(day + next_day, end))


def days(n: int, **kw: object) -> dict:
    return {"slots": None, "days": n, **kw}


def warm_config(steps: int = 60_000) -> SchedulerConfig:
    return replace(fast(steps=steps))


__all__ = ["at", "blocks", "days", "hours", "item", "problem", "run", "wall"]
