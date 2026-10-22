"""Dials reach exactly the rules they should, one day at a time; learned multipliers reach only soft rules."""

from friday.core.pace import Dials, scales
from friday.engine.evaluate import evaluate
from tests.engine.helpers import MON10, at, item, plan, problem

NORMAL = scales(Dials())


def two_days(**dials: float):  # noqa: ANN201
    return [scales(Dials(**dials)), NORMAL]


def day_cost(p, rule: str, slots_by_item) -> int:  # noqa: ANN001
    return evaluate(p, slots_by_item).rule_totals[rule]


def test_growth_zero_switches_open_value_off_for_that_day_only() -> None:
    book = [item("side_project", 1, daily_ceiling_units=4, min_chunk_units=1)]
    normal = problem(book, ["open_value"], slots=None, days=2)
    easy_monday = problem(book, ["open_value"], slots=None, days=2, scales=two_days(growth=0.0))
    both_days = day_cost(normal, "open_value", plan(item_1=()))
    assert day_cost(easy_monday, "open_value", plan(item_1=())) == both_days // 2  # only Tuesday still counts


def test_spread_zero_switches_even_load_off_for_that_day_only() -> None:
    work = [item("assignment", 1, duration_units=8, due_utc=at(1, "20:00"), min_chunk_units=1)]
    even = [dict(type="even_load", name="even_load", params=dict(floor=0))]
    p = problem(work, ["none"], even, slots=None, days=2, scales=two_days(spread=0.0))
    monday = tuple(p.grid.day_slots[0][:8])
    tuesday = tuple(s for s in p.grid.day_slots[1] if s in p.items["item:1"].allowed_set)[:8]
    assert day_cost(p, "even_load", plan(item_1=monday)) == 0
    assert day_cost(p, "even_load", plan(item_1=tuesday)) == 4 * 25


def test_rest_scales_late_night_but_not_daily_load() -> None:
    chore = [item("chore", 1, duration_units=4, shape="split", min_chunk_units=1)]
    rules = ["late_night", "daily_load"]
    base = problem(chore, rules, now=at(0, "22:00"), slots=8)
    rested = problem(chore, rules, now=at(0, "22:00"), slots=8, scales=[scales(Dials(rest=3.0))])
    late = plan(item_1=(1,))  # 22:15–22:30 costs exactly 1 pt/h, so tripling it rounds cleanly
    assert day_cost(base, "late_night", late) == 25
    assert day_cost(rested, "late_night", late) == 75
    assert day_cost(rested, "daily_load", late) == day_cost(base, "daily_load", late) == 0


def test_capacity_scales_the_daily_load_threshold() -> None:
    chore = [item("chore", 1, duration_units=8, shape="split", min_chunk_units=1)]
    rule = [dict(type="daily_load", name="dl", weight=5, params=dict(threshold="2h"))]
    tired = problem(chore, extra=rule, scales=[scales(Dials(capacity=0.5))])
    assert day_cost(tired, "dl", plan(item_1=tuple(range(8)))) == 4 * 125  # threshold 4 units instead of 8


def test_learned_multipliers_scale_soft_rules_and_never_deadlines() -> None:
    items = [
        item("assignment", 1, duration_units=4, due_utc=MON10 + 60, importance=4),
        item("chore", 2, duration_units=4, importance=2),
    ]
    rules = ["late_work", "late_night", "unscheduled"]
    late = plan(item_1=(4, 5, 6, 7), item_2=())
    base = problem(items, rules)
    learned = problem(items, rules, multipliers={"late_work": 5.0, "unscheduled": 2.0})
    assert day_cost(learned, "late_work", late) == day_cost(base, "late_work", late) > 0
    assert day_cost(learned, "unscheduled", late) == 2 * day_cost(base, "unscheduled", late) > 0
