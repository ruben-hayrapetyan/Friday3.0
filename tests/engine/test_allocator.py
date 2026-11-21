"""The allocator: capacities, pacing, lateness first, no front-loading, dependencies, quotas (DESIGN §13)."""

import time
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


def chain(n: int = 8, days: int = 84) -> tuple[list[EngineItem], AllocatorInput]:
    """A project of `n` steps, each waiting on every step before it, as a user's projects and exam prep do."""
    items: list[EngineItem] = []
    for s in range(n):
        waits = tuple(DepSpec(f"s{k}", 1.0, 0, 8, 0) for k in range(s))
        items.append(work(f"s{s}", 4 + s % 5, 20 + 6 * s, depends_on=waits))
    return items, AllocatorInput(make_days(days), items, [], NOW, 14, at(14, "04:00"))


def test_waits_cost_a_few_terms_a_day_not_every_day_before() -> None:
    """20 Nov: a user's plans took three minutes. Each "waits for" link, each day, summed every day before for both
    tasks: 492 links over 84 days were 41 million terms, built again each of 12 rounds. Running totals say the same in
    a few terms a link a day."""
    from ortools.linear_solver import linear_solver_pb2  # noqa: PLC0415

    from friday.engine.allocator import AllocatorLP, DayIndex  # noqa: PLC0415

    items, inp = chain()
    caps = day_capacities(inp)
    lp = AllocatorLP(inp, caps, DayIndex(inp.days), items, {})
    proto = linear_solver_pb2.MPModelProto()
    lp.lp.ExportModelToProto(proto)
    terms = sum(len(c.var_index) for c in proto.constraint)
    links = sum(len(i.depends_on) for i in items)
    assert terms <= 4 * links * len(caps)  # summed afresh it was some 80 a link a day


def test_the_running_totals_find_the_same_best_allocation_as_the_sums() -> None:
    """The same rules written sparsely: the same lateness and the same shape score as summing every day before."""
    from friday.engine import allocator  # noqa: PLC0415

    class Summed(allocator.AllocatorLP):
        def keep_behind_sources(self) -> None:
            needs = {it.key: it.need for it in self.todo}
            for one in self.todo:
                for dep in one.depends_on:
                    if dep.key not in needs or dep.required == 0 or needs[dep.key] <= 0 or dep.lag_min > 0:
                        continue
                    for d in range(self.A):
                        mine, theirs = self.days_of(one.key, before=d + 1), self.days_of(dep.key, before=d + 1)
                        if mine:
                            self.lp.Add(self.lp.Sum(mine) * needs[dep.key] <= self.lp.Sum(theirs) * one.need
                                        if theirs else self.lp.Sum(mine) <= 0)  # fmt: skip

    def scores(kind: type) -> list[float]:
        got: list[float] = []
        real = kind.minimize
        kind.minimize = lambda self, terms: got.append(real(self, terms)) or got[-1]  # type: ignore[method-assign]
        try:
            items, inp = chain(7, 42)
            items.append(work("late", 30, 3, depends_on=(DepSpec("s2", 1.0, 0, 8, 0),)))
            caps = day_capacities(inp)
            kind(inp, caps, allocator.DayIndex(inp.days), items, {}).solve()
        finally:
            kind.minimize = real  # type: ignore[method-assign]
        return got

    assert scores(Summed) == pytest.approx(scores(allocator.AllocatorLP), abs=1e-6)  # the solver's 1e-12s aside


def users_shape() -> list[EngineItem]:
    """A week shaped like a user's (20 Nov): 14 projects of 7 steps, each waiting on every step before it and half of
    them a day apart, 5 exams' prep each waiting on 40 steps, and loose work: 103 tasks, 494 links."""
    items: list[EngineItem] = []
    keys: list[str] = []
    for p in range(14):
        mine: list[str] = []
        for s in range(7):
            gap = 1440 if p % 2 == 0 else 0
            waits = tuple(DepSpec(k, 1.0, gap if mine and k == mine[-1] else 0, 8, 0) for k in mine)
            pacing = "linear" if s == 0 else "none"
            items.append(work(f"p{p}s{s}", 4 + (p + s) % 9, 10 + p * 4 + s * 2, depends_on=waits, pacing=pacing))
            mine.append(f"p{p}s{s}")
        keys += mine
    for e in range(5):
        waits = tuple(DepSpec(k, 1.0, 0, 8, 0) for k in keys[e * 9 : e * 9 + 40])
        items.append(work(f"exam{e}", 16, 30 + e * 9, depends_on=waits))
    return items + [work(f"loose{k}", 2 + k % 5, 3 + k % 70) for k in range(103 - len(items))]


def test_a_week_shaped_like_a_users_allocates_in_seconds(capfd: pytest.CaptureFixture[str]) -> None:
    """20 Nov: a user's plans took over three minutes, all but a few seconds of it here. This shape took 55 s summed
    afresh, 30 s with running totals on GLOP and 3 s on HiGHS; and the solver says nothing (HiGHS printed its banner
    on every solve)."""
    items = users_shape()
    began = time.perf_counter()
    alloc = run(items, make_days(84, free=40))
    assert time.perf_counter() - began < 20  # a loaded test machine: 3 s here
    assert set(alloc.units) == {i.key for i in items}
    assert "HiGHS" not in "".join(capfd.readouterr())


def rounds_of(items: list[EngineItem], cancel: object = None) -> int:
    from friday.engine import allocator  # noqa: PLC0415

    count = [0]
    real = allocator.AllocatorLP.solve

    def counted(self: allocator.AllocatorLP) -> tuple:
        count[0] += 1
        return real(self)

    allocator.AllocatorLP.solve = counted  # type: ignore[method-assign]
    try:
        days = make_days(84, free=40)
        allocate(AllocatorInput(days, items, [], NOW, 14, at(14, "04:00")), cancel)  # type: ignore[arg-type]
    finally:
        allocator.AllocatorLP.solve = real  # type: ignore[method-assign]
    return count[0]


def test_spaced_steps_settle_in_a_few_rounds() -> None:
    """20 Nov: a user's 16 spaced waits ("a day after") took 12 rounds, each the whole allocation again; held behind
    their sources by the gap from the first, 2, to the same scores. This shape took 7."""
    assert rounds_of(users_shape()) <= 3


def test_a_raised_cancel_stops_after_the_round_its_in() -> None:
    """A replan or a What if try replaced by a newer one stops between rounds, not after all of them."""
    import numpy as np  # noqa: PLC0415

    assert rounds_of(users_shape(), np.ones(1, dtype=np.int64)) == 1
