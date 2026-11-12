"""The allocator: capacities, pacing, lateness first, no front-loading, dependencies, quotas (DESIGN §13)."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from friday.core.pace import DayScales
from friday.engine.allocator import AllocatorInput, AllocDay, allocate, day_capacities, pacing_fraction
from friday.engine.problem import DepSpec, EngineItem
from friday.engine.rules import Rule
from tests.engine.helpers import MONDAY, at, item, problem

NOW = at(0, "04:00")


def make_days(n: int = 28, free: int = 40, cap: int = 48, scales: Sequence[DayScales] = ()) -> list[AllocDay]:
    return [AllocDay(date=MONDAY + timedelta(days=d), start_utc=at(d, "04:00"), end_utc=at(d + 1, "04:00"),
                     free_units=free, cap_units=cap, week=d // 7, scales=scales[d] if d < len(scales) else DayScales())
            for d in range(n)]  # fmt: skip


def work(key: str, need: int, due_day: int | None = None, **fields: object) -> EngineItem:
    due = at(due_day, "23:00") if due_day is not None else None
    return EngineItem(key=key, need=need, due_utc=due, firmness=fields.pop("firmness", "hard"), **fields)  # type: ignore[arg-type]


def run(items: list[EngineItem], days: list[AllocDay] | None = None, rules: Sequence[Rule] = (), horizon: int = 14,
        **kw: object):  # noqa: ANN201  # fmt: skip
    days = days or make_days()
    inp = AllocatorInput(days, items, list(rules), NOW, horizon, at(horizon, "04:00"), **kw)  # type: ignore[arg-type]
    return allocate(inp)


def prepared(*specs: dict) -> list[Rule]:
    """Only these rules, prepared on a small problem so their scopes and weekdays are set."""
    names = {spec["name"] for spec in specs}
    return [r for r in problem([item("assignment", 1)], extra=list(specs)).rules if r.name in names]


def week_totals(units: list[float]) -> list[float]:
    return [round(sum(units[w * 7 : w * 7 + 7]), 6) for w in range(len(units) // 7)]


def test_pacing_curves_are_clipped_and_ordered() -> None:
    assert pacing_fraction("linear", 0, 100, 50) == 0.5
    assert pacing_fraction("front", 0, 100, 50) > 0.5 > pacing_fraction("back", 0, 100, 50)
    assert pacing_fraction("linear", 0, 100, -10) == 0 and pacing_fraction("linear", 0, 100, 150) == 1


def test_capacity_is_utilization_of_free_time_under_the_day_cap() -> None:
    days = make_days(4, free=40, cap=30, scales=[DayScales(), DayScales(utilization=0.5), DayScales(utilization=1.5)])
    days[0] = AllocDay(days[0].date, days[0].start_utc, days[0].end_utc, 40, 48, 0)
    caps = day_capacities(AllocatorInput(days, [], [], NOW, 14, at(14, "04:00"), utilization=0.8))
    assert caps == [32, 16, 30, 30]  # 0.8 × 40; the capacity dial halves it; 1.5 × 0.8 is capped at 0.95, then 30


def test_reserves_keep_free_time_scaled_by_the_rest_dial() -> None:
    reserve = prepared(dict(type="reserve", name="evenings", params=dict(days=["mon"], free="2h")))
    days = make_days(2, free=40, cap=48, scales=[DayScales(reserve_free=2.0)])
    caps = day_capacities(AllocatorInput(days, [], reserve, NOW, 14, at(14, "04:00"), utilization=0.5))
    assert caps == [12, 20]  # Monday keeps 4 h (2 h × rest 2) free: 0.5 × (40 − 16); Tuesday has no reserve


def test_elastic_and_target_items_claim_capacity_before_fixed_work() -> None:
    lunch = EngineItem(key="lunch", amount="elastic", ideal=3, release_utc=at(1, "11:00"))
    goal = EngineItem(key="goal", amount="target", target=14, due_utc=at(7, "04:00"))
    alloc = run([lunch, goal, work("a", 1, 3)], make_days(7, free=10, cap=48))
    assert alloc.capacity == [6, 3, 6, 6, 6, 6, 6]  # 0.8 × 10 = 8, less 2 a day for the goal and 3 for Tuesday's lunch


def test_lateness_comes_first_and_the_more_important_item_is_on_time() -> None:
    days = make_days(4, free=10, cap=48)  # 8 units a day
    urgent = work("urgent", 8, 0, importance=5)
    minor = work("minor", 8, 0, importance=1)
    alloc = run([minor, urgent], days, horizon=2)
    assert alloc.units["urgent"][0] == pytest.approx(8)
    assert alloc.units["minor"][1] == pytest.approx(8)  # one day late, rather than four


def test_work_due_in_three_weeks_is_not_front_loaded() -> None:
    alloc = run([work("essay", 16, 20)])
    assert sum(alloc.units["essay"][:14]) == pytest.approx(0)
    assert alloc.quotas == {}
    assert sum(alloc.units["essay"]) == pytest.approx(16)


def test_a_paced_project_follows_its_line_week_by_week() -> None:
    project = work("project", 112, 27, pacing="linear")
    alloc = run([project])
    for total in week_totals(alloc.units["project"]):
        assert total == pytest.approx(28, abs=2)


def test_quotas_cover_the_horizon_weeks_of_items_due_after_it() -> None:
    project = work("project", 112, 27, pacing="linear")
    soon = work("soon", 8, 5)
    alloc = run([project, soon])
    assert "soon" not in alloc.quotas
    assert set(alloc.quotas["project"]) == {0, 1}
    assert all(abs(q - 28) <= 2 for q in alloc.quotas["project"].values())


def test_dependent_work_waits_for_its_source_and_the_lag() -> None:
    source = work("a", 40, 20)
    dependent = work("b", 8, 20, depends_on=(DepSpec("a", 1.0, 1440, 40, 0),))
    alloc = run([source, dependent])
    last_of_a = max(d for d, u in enumerate(alloc.units["a"]) if u > 1e-6)
    first_of_b = min(d for d, u in enumerate(alloc.units["b"]) if u > 1e-6)
    assert first_of_b >= last_of_a + 2  # the next day, plus a day of lag


def test_a_whole_day_price_moves_work_and_a_forbidden_day_gets_none() -> None:
    rest = dict(type="time_preference", name="rest", params=dict(days=["sun"], price="forbid"))
    dear = dict(type="time_preference", name="dear", params=dict(days=["sat"], price=5))
    rules = prepared(rest, dear)
    alloc = run([work("a", 8, 13)], make_days(14, free=10), rules)
    assert alloc.units["a"][13] == 0 and alloc.units["a"][12] == 0 and alloc.units["a"][6] == 0
    assert sum(alloc.units["a"]) == pytest.approx(8)


def test_overflow_when_capacity_is_short() -> None:
    alloc = run([work("huge", 400, 6)], make_days(7, free=10))
    assert alloc.over["huge"] == pytest.approx(400 - 7 * 8)


def test_the_same_input_gives_the_same_allocation() -> None:
    items = [work(f"i{k}", 4 + k, 5 + k % 9, pacing="linear" if k % 3 == 0 else "none") for k in range(30)]
    assert run(items).units == run(items).units


def test_work_due_as_a_day_begins_is_done_by_the_day_before() -> None:
    # Due at 4am Thursday, as Thursday begins: Thursday's own time is after the due, so it isn't the due day.
    item = EngineItem(key="a", need=8, due_utc=at(3, "04:00"), firmness="hard")
    alloc = run([item])
    assert sum(alloc.units["a"][3:]) == pytest.approx(0) and sum(alloc.units["a"][:3]) == pytest.approx(8)
