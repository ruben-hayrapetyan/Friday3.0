"""The scenario tests of DESIGN §24.2, numbered as there. Each builds its own small rule set.

Scenarios 3, 4, 21, 22, 24 and 29 need the planner, commands and shove (M5).
"""

import pytest

from friday.core.pace import DEFAULT_PACES, scales
from friday.core.time import to_local
from friday.engine.allocator import allocate, apply_quotas
from friday.engine.checker import runs
from friday.engine.construct import prepare_start
from friday.engine.evaluate import evaluate
from friday.engine.explain import block_costs, blocks_of
from friday.engine.sampler import tolerated
from friday.planner.build import Dependency, Pin, id_of
from friday.planner.inputs import allocator_input
from tests.bench.generator import Scenario, bench_settings, overload, reference_instance, reference_rules
from tests.engine.configs import fast
from tests.scenarios.common import FRI, MON, SUN, TUE, WED, at, blocks, days, hours, item, problem, run, wall

EASY, PUSH = scales(DEFAULT_PACES["Easy"]), scales(DEFAULT_PACES["Push"])


def test_01_a_rest_day_is_used_when_it_is_the_only_time_before_the_deadline() -> None:
    blocked = item("commitment", 90, title="away", start_utc=at(FRI, "06:00"), end_utc=at(SUN, "04:00"))
    ps = item("assignment", 1, title="PS", duration_units=8, due_utc=at(SUN, "23:00"), min_chunk_units=1)
    rest = dict(type="time_preference", name="rest", weight=3, params=dict(days=["sun"], price=5))
    p = problem([blocked, ps], ["late_work"], [rest], now=at(FRI, "06:00"), **days(3))
    result = run(p)
    assert result.stage_values["deadlines"] == 0
    assert hours(p, result.plan, "item:1") == 2 and result.evaluation.rule_totals["rest"] > 0


def test_02_more_work_than_fits_returns_a_plan_with_overflow_never_infeasible() -> None:
    huge = item("assignment", 1, duration_units=160, due_utc=at(TUE, "12:00"), min_chunk_units=1)
    p = problem([huge], ["late_work", "unscheduled"], **days(2))
    result = run(p)
    assert result.evaluation.over_units["item:1"] > 0 and result.stage_values["deadlines"] > 0


NAMES_5 = ["late_work", "soft_late", "energy", "chunk_cost", "minimize_changes", "late_night"]


def two_items():  # noqa: ANN201
    return [item("assignment", 1, duration_units=6, due_utc=at(TUE, "17:00"), min_chunk_units=1, chunk_cost=0.1),
            item("reading", 2, duration_units=4, due_utc=at(TUE, "12:00"), min_chunk_units=1)]  # fmt: skip


def as_blocks(p, plan: dict) -> dict[int, list[tuple[int, int]]]:  # noqa: ANN001
    return {id_of(k): [(int(p.grid.start[s]), int(p.grid.end[s])) for s in slots] for k, slots in plan.items()}


def test_05_a_replan_with_nothing_changed_moves_nothing() -> None:
    first_problem = problem(two_items(), NAMES_5, **days(2))
    first = run(first_problem)
    again = problem(two_items(), NAMES_5, current=as_blocks(first_problem, first.plan), **days(2))
    second = run(again, warm=True)
    assert second.plan == first.plan
    assert second.evaluation.rule_totals["minimize_changes"] == 0


def test_06_a_preferred_pin_resists_a_slightly_cheaper_slot() -> None:
    work = [item("assignment", 1, duration_units=4, due_utc=at(TUE, "17:00"), min_chunk_units=4)]
    dear = dict(type="time_preference", name="dear_afternoon", params=dict(start="13:00", end="14:00", price=3))
    current = {1: [(at(MON, "13:00") + 15 * k, at(MON, "13:00") + 15 * (k + 1)) for k in range(4)]}
    pinned = problem(work, ["late_work", "minimize_changes"], [dear], current=current, **days(2),
                     pins=[Pin(1, at(MON, "13:00"), at(MON, "14:00"), "preferred")])  # fmt: skip
    kept = run(pinned, warm=True)
    assert blocks(pinned, kept.plan, "item:1") == [(at(MON, "13:00"), at(MON, "14:00"))]  # moving saves 3, costs 10
    # Unpinned, it stays too: keeping the plan is a wellbeing cost (decision 120), so a preference price alone
    # doesn't move work already placed.
    free = problem(work, ["late_work", "minimize_changes"], [dear], current=current, **days(2))
    assert blocks(free, run(free, warm=True).plan, "item:1") == [(at(MON, "13:00"), at(MON, "14:00"))]


def test_06b_a_block_moves_to_a_new_preferred_pin() -> None:
    work = [item("assignment", 1, duration_units=4, due_utc=at(TUE, "17:00"), min_chunk_units=4)]
    current = {1: [(at(TUE, "10:00"), at(TUE, "11:00"))]}
    pinned = problem(work, ["late_work", "minimize_changes"], current=current, **days(2),
                     pins=[Pin(1, at(MON, "15:00"), at(MON, "16:00"), "preferred")])  # fmt: skip
    assert blocks(pinned, run(pinned, warm=True).plan, "item:1") == [(at(MON, "15:00"), at(MON, "16:00"))]


def test_07_a_one_sitting_item_is_one_block_or_all_overflow() -> None:
    chore = item("chore", 1, title="two hours", duration_units=8)
    p = problem([wall(90, MON, "11:00", "12:00"), chore], ["unscheduled"], now=at(MON, "09:00"), **days(1))
    result = run(p)
    assert len(blocks(p, result.plan, "item:1")) == 1 and hours(p, result.plan, "item:1") == 2
    cuts = [item("commitment", 80 + k, start_utc=at(MON, f"{h:02d}:00"), end_utc=at(MON, f"{h:02d}:30"),
                 event_kind="meeting") for k, h in enumerate(range(9, 23, 2))]  # fmt: skip
    cuts.append(item("commitment", 99, start_utc=at(MON, "23:00"), end_utc=at(MON, "23:59"), event_kind="meeting"))
    q = problem([*cuts, chore], ["unscheduled"], now=at(MON, "09:00"), **days(1))
    crowded = run(q)
    assert crowded.plan["item:1"] == () and crowded.evaluation.over_units["item:1"] == 8


def test_08_a_target_is_placed_only_where_its_shortfall_slope_beats_the_slot_price() -> None:
    guitar = item("goal", 1, target_units=16, cap_units=40, release_utc=at(MON, "09:00"), due_utc=at(TUE, "04:00"),
                  min_chunk_units=1, neglect_carry=0)  # fmt: skip
    price = dict(type="time_preference", name="dear", params=dict(price=6))
    p = problem([guitar], ["target_shortfall"], [price], **days(1))
    # Below ⌈0.4 × 16⌉ = 7 units each hour is worth 8 + 3 = 11 > 6; above, only 3 < 6.
    assert sum(int(p.grid.units[s]) for s in run(p).plan["item:1"]) == 7


def test_09_batch_by_day_pulls_three_chores_to_saturday() -> None:
    chores = [item("chore", k, duration_units=4, release_utc=at(TUE, "06:00"), due_utc=at(SUN + 1, "04:00"))
              for k in (1, 2, 3)]  # fmt: skip
    extra = [dict(type="time_preference", name="sat", params=dict(days_except=["sat"], price=1)),
             dict(type="batch_by_day", name="batch", weight=5, params=dict(by="preset"))]  # fmt: skip
    p = problem(chores, ["unscheduled"], extra, now=at(WED, "09:00"), **days(5))
    result = run(p)
    assert {p.grid.slots[s].weekday for k in result.plan for s in result.plan[k]} == {5}


def test_10_late_night_keeps_work_before_bedtime_unless_a_deadline_needs_it() -> None:
    day = wall(90, MON, "04:30", "21:00")
    short = item("assignment", 1, duration_units=4, due_utc=at(TUE, "04:00"), min_chunk_units=1)
    p = problem([day, short], ["late_work", "late_night"], now=at(MON, "09:00"), **days(1))
    assert max(p.grid.end[s] for s in run(p).plan["item:1"]) <= at(MON, "22:00")
    long = item("assignment", 1, duration_units=10, due_utc=at(TUE, "00:00"), min_chunk_units=1)
    q = problem([day, long], ["late_work", "late_night"], now=at(MON, "09:00"), **days(1))
    assert run(q).stage_values["deadlines"] == 0  # met, even though it needs the gradient


def test_11_a_daylight_saving_change_inside_the_horizon() -> None:
    from datetime import date

    sc = reference_instance(25, 5, timezone="America/New_York", monday=date(2026, 10, 26))
    p = sc.build()
    tz = "America/New_York"
    assert sorted({len(p.grid.day_slots[d]) for d in range(1, 7)}) == [96, 100]
    result = run(p, fast(steps=50_000))
    for occurrence in p.fixed:  # no block overlaps a class or commitment at its true UTC time
        for key, slots in result.plan.items():
            for s in slots:
                assert not (p.grid.start[s] < occurrence.blocked_hi and p.grid.end[s] > occurrence.blocked_lo), key
    lectures = [f for f in p.fixed if "lecture" in f.title]
    assert {to_local(f.start_utc, tz).strftime("%H:%M") for f in lectures} <= {"09:05", "10:10", "11:15", "13:25",
                                                                              "14:30", "15:35"}  # fmt: skip


def test_12_explanations_equal_the_evaluator_and_the_evaluator_equals_the_kernel() -> None:
    sc = reference_instance(30, 6)
    p = sc.build()
    result = run(p, fast(steps=40_000))  # the scheduler itself raises if the kernel and evaluator disagree
    per_block, other = block_costs(p, result.plan, blocks_of(result.plan))
    for rule, total in result.evaluation.rule_totals.items():
        assert sum(b.get(rule, 0) for b in per_block) + other.get(rule, 0) == total
    assert sum(result.stage_values.values()) == sum(result.evaluation.rule_totals.values())


def test_13_a_dependency_orders_the_work() -> None:
    a = item("assignment", 1, title="A", duration_units=4, due_utc=at(MON, "12:00"), min_chunk_units=1)
    b = item("assignment", 2, title="B", duration_units=4, due_utc=at(MON, "12:00"), min_chunk_units=1)
    walls = [wall(90, MON, "04:00", "09:50"), wall(91, MON, "11:20", "23:59")]  # only 09:50–11:20 is free
    p = problem([*walls, a, b], ["late_work"], deps=[Dependency(2, 1)], now=at(MON, "09:00"), **days(1))
    result = run(p)
    assert max(p.grid.end[s] for s in result.plan["item:1"]) <= min(p.grid.start[s] for s in result.plan["item:2"])


def test_14_half_of_a_with_a_day_of_lag_before_b() -> None:
    a = item("assignment", 1, duration_units=8, due_utc=at(MON + 3, "12:00"), min_chunk_units=1)
    b = item("assignment", 2, duration_units=4, due_utc=at(MON + 3, "12:00"), min_chunk_units=1)
    early = dict(type="finish_early", name="fe", weight=3, params=dict(days=3))
    p = problem([a, b], ["late_work"], [early], deps=[Dependency(2, 1, 0.5, 1440)], **days(4))
    result = run(p)
    done, half_done = 0, None
    for s in sorted(result.plan["item:1"]):
        done += int(p.grid.units[s])
        if done >= 4 and half_done is None:
            half_done = int(p.grid.end[s])
    assert min(p.grid.start[s] for s in result.plan["item:2"]) >= half_done + 1440 - 15


def test_15_no_isolated_fifteen_minute_pieces() -> None:
    cuts = [item("commitment", 80 + k, start_utc=at(MON, f"{h:02d}:15"), end_utc=at(MON, f"{h:02d}:45"),
                 event_kind="shove") for k, h in enumerate(range(9, 12))]  # fmt: skip
    work = item("assignment", 1, duration_units=4, due_utc=at(MON, "13:00"), min_chunk_units=2)
    p = problem([*cuts, wall(90, MON, "13:00"), work], ["late_work"], now=at(MON, "09:00"), **days(1))
    plan = run(p).plan
    assert all(int(p.grid.units[a : b + 1].sum()) >= 2 for a, b in runs(plan["item:1"]))


def test_16_chunk_cost_keeps_a_three_hour_item_in_one_chunk() -> None:
    work = item("assignment", 1, duration_units=12, due_utc=at(TUE, "17:00"), min_chunk_units=1, chunk_cost=0.2)
    p = problem([work], ["late_work", "chunk_cost"], **days(2))
    assert len(blocks(p, run(p).plan, "item:1")) == 1


def test_17_deep_work_runs_either_side_of_a_class_and_never_more_than_three_hours_straight() -> None:
    lecture = item("class", 9, start_utc=at(MON, "11:00"), end_utc=at(MON, "12:00"), event_kind="class")
    deep = item("assignment", 1, duration_units=20, due_utc=at(MON, "17:00"), min_chunk_units=1)
    p = problem([lecture, deep, wall(90, MON, "04:00", "07:55")], ["late_work", "deep_run"], now=at(MON, "08:00"),
                **days(1))  # fmt: skip
    result = run(p)
    assert result.evaluation.rule_totals["deep_run"] == 0 and result.stage_values["deadlines"] == 0
    placed, g = set(result.plan["item:1"]), p.grid
    for a in range(g.S):  # no 3 h 15 min window holds more than 3 h of deep work
        units, b = 0, a
        while b < g.S and units < 13:
            units, b = units + int(g.units[b]), b + 1
        if units >= 13:
            assert sum(int(g.units[s]) for s in range(a, b) if s in placed) <= 12


def test_18_weekday_evenings_keep_two_free_hours_on_a_light_load() -> None:
    work = [item("assignment", k, duration_units=6, due_utc=at(WED, "04:00"), min_chunk_units=1) for k in (1, 2, 3, 4)]
    evenings = dict(type="reserve", name="evenings", weight=2,
                    params=dict(days_except=["sat", "sun"], start="18:00", end="23:00", free="2h"))  # fmt: skip
    p = problem(work, ["late_work"], [evenings], **days(2))
    result = run(p)
    for d in range(2):
        window = [s for s in p.grid.day_slots[d] if 18 * 60 <= p.grid.slots[s].local_minute < 23 * 60]
        busy = sum(int(p.grid.units[s]) for s in window if any(s in slots for slots in result.plan.values()))
        assert 20 - busy >= 8


def test_19_lunch_fits_its_window_on_a_busy_day() -> None:
    classes = [item("class", 9, start_utc=at(MON, "10:00"), end_utc=at(MON, "11:30"), buffer_before_min=0,
                    buffer_after_min=0),
               item("class", 10, start_utc=at(MON, "12:15"), end_utc=at(MON, "14:30"), buffer_before_min=0,
                    buffer_after_min=0),
               item("commitment", 11, start_utc=at(MON, "14:30"), end_utc=at(MON, "23:00"))]  # fmt: skip
    lunch = item("routine", 1, min_units=2, ideal_units=2, max_units=3, release_utc=at(MON, "11:30"),
                 due_utc=at(MON, "14:30"))  # fmt: skip
    p = problem([*classes, lunch], ["elastic_shortfall"], now=at(MON, "09:00"), **days(1))
    plan = run(p).plan
    assert hours(p, plan, "item:1") >= 20 / 60
    assert all(at(MON, "11:30") <= a and b <= at(MON, "14:30") for a, b in blocks(p, plan, "item:1"))


def test_20_a_far_project_gets_about_a_linear_share_this_week_and_next() -> None:
    """30 h due in six weeks, a light fortnight: the allocator's quotas ask for about 5 h a week, and the scheduler
    places that much rather than pulling the whole project forward."""
    classes = [item("class", 10 + d, start_utc=at(d, "10:00"), end_utc=at(d, "12:00")) for d in (MON, WED, FRI)]
    project = item("project", 1, duration_units=120, due_utc=at(41, "17:00"))
    rules = reference_rules(["late_work", "quota", "unscheduled"])
    sc = Scenario("20", [*classes, project], at(MON, "10:00"), bench_settings(horizon_days=14, rules=rules))
    p = sc.build()
    allocation = allocate(allocator_input(sc.build_input(), p))
    apply_quotas(p.items.values(), allocation, p.grid.horizon_end)
    assert set(p.items["item:1"].quotas) == set(p.grid.week_slots)
    plan = run(p, fast(steps=60_000)).plan
    for week, slots in p.grid.week_slots.items():
        placed = sum(int(p.grid.units[s]) for s in plan["item:1"] if s in set(slots)) / 4
        assert 4 <= placed <= 6.5, (week, placed)


def test_23_the_same_snapshot_planned_with_different_thread_counts_is_identical() -> None:
    p = reference_instance(30, 9).build()
    assert run(p, fast(steps=20_000, chains=4, threads=1)).plan == run(p, fast(steps=20_000, chains=4, threads=4)).plan


PACE_RULES = ["late_work", "late_night", "daily_load", "even_load", "open_value", "weekday_evenings", "weekends"]


def book():  # noqa: ANN201
    return item("side_project", 1, title="book", daily_ceiling_units=12, min_chunk_units=3)


def mornings():  # noqa: ANN201
    return [wall(90, MON, "04:00", "09:00"), wall(91, TUE, "04:00", "09:00")]


def open_hours(p, result, day: int | None = None) -> float:  # noqa: ANN001
    return sum(int(p.grid.units[s]) for s in result.plan["item:1"] if day is None or p.grid.slots[s].day == day) / 4


def test_25_an_open_item_fills_free_time_outside_the_reserve_at_normal_pace() -> None:
    p = problem([book(), *mornings()], PACE_RULES, now=at(MON, "09:00"), **days(2))
    result = run(p)
    assert 0 < open_hours(p, result) <= 6
    assert all(open_hours(p, result, d) <= 3 for d in range(2))  # its daily ceiling
    assert result.evaluation.rule_totals["weekday_evenings"] == 0


def test_26_at_easy_pace_the_open_item_waits_and_hard_work_is_spread() -> None:
    hard = [item("assignment", 10 + k, duration_units=20, due_utc=at(MON + 3, "12:00"), min_chunk_units=2)
            for k in range(3)]  # fmt: skip
    p = problem([book(), *hard], PACE_RULES, now=at(MON, "09:00"), scales=[EASY] * 4, **days(4))
    result = run(p)
    assert open_hours(p, result) == 0
    per_day = [sum(int(p.grid.units[s]) for k in result.plan if k != "item:1" for s in result.plan[k]
                   if p.grid.slots[s].day == d) for d in range(4)]  # fmt: skip
    share = -(-60 // 4)  # 60 hard units over four days with free time
    assert max(per_day) <= share + 4  # within one chunk of the even share


def test_27_at_push_pace_the_open_item_also_uses_reserve_evenings_and_never_the_sleep_core() -> None:
    # Days busy until 18:00, so the evening is the open item's only time. At Normal it stops where the reserve
    # starts to cost (2 pt/h against 0.5–1.5 pt/h of value); at Push its hours are worth more and less is kept free.
    book = item("side_project", 1, title="book", daily_ceiling_units=20, min_chunk_units=3)
    busy = [wall(90 + d, d, "04:00", "18:00") for d in (MON, TUE)]
    normal = problem([book, *busy], PACE_RULES, now=at(MON, "09:00"), **days(2))
    pushed = problem([book, *busy], PACE_RULES, now=at(MON, "09:00"), scales=[PUSH, PUSH], **days(2))
    r_normal, r_push = run(normal), run(pushed)

    def evening_units(p, result) -> int:  # noqa: ANN001
        return sum(
            int(p.grid.units[s]) for s in result.plan["item:1"] if 18 * 60 <= p.grid.slots[s].local_minute < 23 * 60
        )

    assert evening_units(pushed, r_push) > evening_units(normal, r_normal)
    assert not any(pushed.core[s] for s in r_push.plan["item:1"])


def test_28_easy_pace_still_meets_deadlines_it_cannot_make_light() -> None:
    hard = [item("assignment", 10 + k, duration_units=20, due_utc=at(MON + 3, "12:00"), min_chunk_units=2)
            for k in range(3)]  # fmt: skip
    p = problem(hard, PACE_RULES, now=at(MON, "09:00"), scales=[EASY] * 4, **days(4))
    assert run(p).stage_values["deadlines"] == 0  # the pace notice naming each day comes from the planner (M5)


def test_30_a_thirty_item_dependency_chain_needs_no_fallback() -> None:
    chain = [item("assignment", k, duration_units=4, due_utc=at(MON + 12, "23:59"), min_chunk_units=1)
             for k in range(1, 31)]  # fmt: skip
    deps = [Dependency(k + 1, k, 1.0 if k % 2 else 0.5) for k in range(1, 30)]
    p = problem(chain, ["late_work"], deps=deps, now=at(MON, "09:00"), **days(14))
    result = run(p, fast(steps=30_000, fallback=False))
    assert result.stage_values["deadlines"] == 0 and result.fallback == "none"


def test_31_a_tight_one_sitting_packing_is_found_by_the_fallback_and_reported() -> None:
    # Free: 09:00–12:00 and 13:00–15:00. Two hours (due 15:00) and three hours (due 16:00) fit only one way;
    # earliest-deadline order puts the two-hour item in the morning and leaves the other nowhere.
    walls = [wall(90, MON, "12:00", "13:00"), wall(91, MON, "15:00", "23:59")]
    two = item("errand", 1, title="two", duration_units=8, release_utc=at(MON, "09:00"), due_utc=at(MON, "15:00"),
               firmness="hard")  # fmt: skip
    three = item("errand", 2, title="three", duration_units=12, release_utc=at(MON, "09:00"),
                 due_utc=at(MON, "16:00"), firmness="hard")  # fmt: skip
    p = problem([*walls, two, three], ["late_work"], now=at(MON, "09:00"), **days(1))
    start = prepare_start(p)
    assert evaluate(p, start.c.plan_from_owner(start.owner)).stage_values["deadlines"] > 0
    from dataclasses import replace

    result = run(p, replace(fast(steps=20_000), repair_steps=0))  # with repair off, only the fallback can fix it
    assert result.stage_values["deadlines"] == 0
    assert result.fallback == "first:cpsat-better"


def test_32_an_item_on_time_in_the_start_plan_stays_on_time_against_a_preference() -> None:
    work = item("assignment", 1, duration_units=4, due_utc=at(MON, "12:00"), min_chunk_units=1)
    before_noon = dict(type="time_preference", name="mornings", params=dict(start="09:00", end="12:00", price=100))
    p = problem([work], [], [before_noon], now=at(MON, "09:00"), **days(1))  # no late_work: only W9 holds it
    result = run(p)
    assert "item:1" in result.protected
    assert max(p.grid.end[s] for s in result.plan["item:1"]) <= at(MON, "12:00")


@pytest.mark.parametrize("seed", [0, 1])
def test_33_overload_plans_are_valid_never_later_than_any_step_and_report_lateness(seed: int) -> None:
    p = overload(seed).build()
    result = run(p, fast(steps=60_000, fallback_s=5.0))
    steps = result.deadlines_after
    assert "fallback" in steps  # the fallback ran, since lateness was left
    # Polishing may trade a sliver of lateness (LATE_TOLERANCE) for late work in sittings rather than slivers.
    assert steps["final"] <= tolerated(min(steps.values()))
    assert result.evaluation.deadline_misses  # per-item lateness is reported
