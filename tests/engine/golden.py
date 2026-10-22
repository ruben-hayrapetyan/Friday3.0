"""Load a golden fixture (written once from the research code) as a v3 Problem."""

import gzip
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from friday.core.pace import Dials, scales
from friday.core.time import GridSpec, make_grid, week_of
from friday.engine.problem import DepSpec, EngineItem, FixedOcc, Night, Problem
from friday.engine.rules import build_rules

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
# The research counted minutes from a Monday 00:00 with no timezone; 1970-01-05 is that Monday in UTC.
RESEARCH_DAY_ZERO = date(1970, 1, 5)
OFFSET = 4 * 1440


# Parameters added after the research (M14), off as the research had them: a floor under even_load's share and a
# price on the hour after waking.
ADDED_SINCE = {"even_load": {"floor": 0}, "late_night": {"morning": 0}}


def research_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r | {"params": ADDED_SINCE.get(r["type"], {}) | r.get("params", {})} for r in rules]


def fixture_names() -> list[str]:
    return sorted(p.name.removesuffix(".json.gz") for p in FIXTURES.glob("*.json.gz"))


def read(name: str) -> dict[str, Any]:
    with gzip.open(FIXTURES / f"{name}.json.gz", "rt") as f:
        return json.load(f)


def slots_of(ranges: list[list[int]]) -> list[int]:
    return [s for a, b in ranges for s in range(a, b + 1)]


def research_date(d: int) -> date:
    return RESEARCH_DAY_ZERO + timedelta(days=d)


def moment(minutes: int | None) -> int | None:
    return None if minutes is None else minutes + OFFSET


def week(research_week: int, week_start: int) -> int:
    return week_of(research_date(research_week * 7 + week_start), week_start)


def item(raw: dict[str, Any], week_start: int) -> EngineItem:
    return EngineItem(
        key=raw["key"], title=raw["title"], area=raw["area"], tags=tuple(raw["tags"]), preset=raw["preset"],
        energy=raw["energy"], importance=raw["importance"], firmness=raw["firmness"], amount=raw["amount"],
        daily_ceiling=raw["daily_ceiling"], progress_today=raw["progress_today"], need=raw["need"],
        min=raw["min"], ideal=raw["ideal"], max=raw["max"], target=raw["target"], cap=raw["cap"],
        progress=raw["progress"],
        progress_by_week={week(int(w), week_start): u for w, u in raw["progress_by_week"].items()},
        release_utc=moment(raw["release"]), due_utc=moment(raw["due"]), window_is_hard=raw["window_is_hard"],
        shape=raw["shape"], min_chunk=raw["min_chunk"], max_chunk=raw["max_chunk"],
        chunk_cost=raw["chunk_cost"], spread=raw["spread"], size_hours=raw["size_hours"],
        tentative=raw["tentative"], allowed=tuple(slots_of(raw["allowed"])),
        locked=frozenset(slots_of(raw["locked"])), preferred=frozenset(slots_of(raw["preferred"])),
        current=frozenset(slots_of(raw["current"])),
        depends_on=tuple(DepSpec(**d) for d in raw["depends_on"]),
        quotas={week(int(w), week_start): u for w, u in raw["quotas"].items()},
    )  # fmt: skip


def problem(fixture: dict[str, Any]) -> Problem:
    g = fixture["grid"]
    spec = GridSpec(timezone="UTC", day_start=g["day_start"], week_start=g["week_start"],
                    horizon_days=g["horizon_days"], fine_days=g["fine_days"])  # fmt: skip
    grid = make_grid(g["now"] + OFFSET, spec, moment(g["end"]))
    fixed = [
        FixedOcc(
            f["title"],
            f["kind"],
            f["start"] + OFFSET,
            f["end"] + OFFSET,
            tuple(f["tags"]),
            f["buf_before"],
            f["buf_after"],
            f["blocks_time"],
        )  # fmt: skip
        for f in fixture["fixed"]
    ]
    nights = {
        research_date(int(d)): Night(n["bedtime"] + OFFSET, n["wake"] + OFFSET, n["margin"], n["debt_hours"])
        for d, n in fixture["nights"].items()
    }
    hourly = fixture["energy_map"]
    energy_map = tuple(tuple(hourly[str(wd)][cell // 2] for cell in range(48)) for wd in range(7))
    day_scales = [scales(Dials(capacity=c, rest=r, spread=s, growth=gr)) for c, r, s, gr in fixture["dials"]]
    built = Problem(
        grid=grid,
        items={raw["key"]: item(raw, g["week_start"]) for raw in fixture["items"]},
        fixed=fixed,
        nights=nights,
        day_caps=fixture["day_caps"],
        rules=build_rules(research_rules(fixture["rules"])),
        scales=day_scales,
        energy_map=energy_map,
        scale=fixture["scale"],
        minimize_changes_scale=fixture["minimize_changes_scale"],
    )
    for rule in built.rules:
        rule.prepare(built)
    return built


def plan_of(raw: dict[str, Any], problem: Problem) -> dict[str, tuple[int, ...]]:
    plan = {k: () for k in problem.items}
    plan.update({k: tuple(slots_of(r)) for k, r in raw["plan"].items()})
    return plan
