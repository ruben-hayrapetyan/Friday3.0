"""Measure rules, four tests each (DESIGN §12.5). A unit measure costs round(weight × slope × 0.25 × 100) per
unit of hinge excess; a count measure round(weight × slope × 100) per count."""

from friday.core.pace import Dials, scales
from friday.planner.build import Pin
from tests.engine.brute import brute_force
from tests.engine.helpers import BOUNDARY, MON10, at, item, plan, problem, zone_problem
from tests.engine.test_rules_prices import FAR, assert_avoided, cost

B = BOUNDARY


def with_quota(p, units: int):  # noqa: ANN001, ANN201
    week = p.grid.slots[0].week
    p.items["item:1"].quotas = {week: units}
    return p


# quota: weight 3, units placed this week plus progress, below the quota


def test_quota_is_zero_when_met() -> None:
    p = with_quota(problem([item("project", 1, duration_units=8, due_utc=FAR, min_chunk_units=1)], ["quota"]), 4)
    assert cost(p, plan(item_1=(0, 1, 2, 3)), "quota") == 0


def test_quota_shortfall_counts_progress() -> None:
    p = with_quota(problem([item("project", 1, duration_units=8, due_utc=FAR, min_chunk_units=1)], ["quota"]), 4)
    p.items["item:1"].progress_by_week = {p.grid.slots[0].week: 1}
    assert cost(p, plan(item_1=(0,)), "quota") == 2 * 75  # 1 placed + 1 progress, 2 short


def test_quota_is_avoided() -> None:
    p = with_quota(problem([item("project", 1, duration_units=2, due_utc=FAR, min_chunk_units=1)], ["quota"]), 2)
    assert_avoided(p, "quota")


def test_quota_across_the_zone_boundary() -> None:
    p = with_quota(zone_problem([item("project", 1, duration_units=8, due_utc=FAR, min_chunk_units=1)], ["quota"]), 4)
    assert cost(p, plan(item_1=(B,)), "quota") == 2 * 75
    assert cost(p, plan(item_1=(B, B + 1)), "quota") == 0


# deep_run: weight 4; in every window of K + 1 units, deep units above K


DEEP_1H = [dict(type="deep_run", name="dr", weight=4, params=dict(threshold="1h"))]


def deep(units: int):  # noqa: ANN201
    return item("assignment", 1, duration_units=units, min_chunk_units=1)


def test_deep_run_is_zero_with_breaks() -> None:
    p = problem([deep(8)], extra=DEEP_1H, slots=20)
    assert cost(p, plan(item_1=(0, 1, 2, 3, 5, 6, 7, 8)), "dr") == 0


def test_deep_run_counts_each_window_over_the_limit() -> None:
    p = problem([deep(10)], extra=DEEP_1H, slots=20)
    assert cost(p, plan(item_1=(0, 1, 2, 3, 4, 5)), "dr") == 2 * 100  # windows from 0 and 1 hold 5 units each


def test_deep_run_capacity_dial_never_goes_below_an_hour() -> None:
    p = problem([deep(10)], extra=DEEP_1H, slots=20, scales=[scales(Dials(capacity=0.3))])
    assert cost(p, plan(item_1=(0, 1, 2, 3, 4, 5)), "dr") == 2 * 100


def test_deep_run_is_avoided_with_a_break() -> None:
    p = problem([deep(5)], ["unscheduled"], DEEP_1H)
    assert_avoided(p, "dr")


def test_deep_run_across_the_zone_boundary() -> None:
    p = zone_problem([deep(6)], extra=DEEP_1H)
    # 03:30 and 03:45 (1 unit each), then 04:00 and 04:30 (2 units each): windows from 03:30 (6 units) and 03:45 (5)
    assert cost(p, plan(item_1=(B - 2, B - 1, B, B + 1)), "dr") == (2 + 1) * 100


# reserve: weight 2; per matching day, busy units in the window above (free units − kept free)


EVENINGS = [dict(type="reserve", name="evenings", weight=2,
                 params=dict(days_except=["sat", "sun"], start="18:00", end="23:00", free="2h"))]  # fmt: skip


def chore(units: int):  # noqa: ANN201
    return item("chore", 1, duration_units=units, shape="split", min_chunk_units=1)


def test_reserve_is_zero_while_enough_stays_free() -> None:
    p = problem([chore(20)], extra=EVENINGS, now=at(0, "18:00"), slots=20)
    assert cost(p, plan(item_1=tuple(range(12))), "evenings") == 0


def test_reserve_exact_and_rest_dial() -> None:
    p = problem([chore(20)], extra=EVENINGS, now=at(0, "18:00"), slots=20)
    assert cost(p, plan(item_1=tuple(range(14))), "evenings") == 2 * 50  # 20 free, keep 8: 14 busy is 2 over 12
    rested = problem([chore(20)], extra=EVENINGS, now=at(0, "18:00"), slots=20, scales=[scales(Dials(rest=2.0))])
    assert cost(rested, plan(item_1=tuple(range(14))), "evenings") == 10 * 50  # keep 16: 10 over 4


def test_reserve_is_avoided() -> None:
    rule = [dict(type="reserve", name="evenings", weight=2, params=dict(start="18:00", end="20:00", free="1h"))]
    p = problem([chore(4)], ["unscheduled"], rule, now=at(0, "18:00"))
    assert_avoided(p, "evenings")


def test_reserve_across_the_zone_boundary() -> None:
    rule = [dict(type="reserve", name="dawn", weight=2, params=dict(days=["tue"], start="04:00", end="06:00",
                                                                     free="1h"))]  # fmt: skip
    p = zone_problem([chore(6)], extra=rule)
    assert cost(p, plan(item_1=(B, B + 1, B + 2)), "dawn") == 2 * 50  # 8 free, keep 4: 6 busy is 2 over 4


# daily_load: weight 5; a day's in-scope units above the threshold


LOAD_1H = [dict(type="daily_load", name="dl", weight=5, params=dict(threshold="1h"))]


def test_daily_load_is_zero_under_the_threshold() -> None:
    assert cost(problem([chore(6)], extra=LOAD_1H), plan(item_1=(0, 1, 2, 3)), "dl") == 0


def test_daily_load_threshold_is_a_soft_cap() -> None:
    assert cost(problem([chore(6)], extra=LOAD_1H), plan(item_1=(0, 1, 2, 3, 4, 5)), "dl") == 2 * 125


def test_daily_load_is_avoided() -> None:
    assert_avoided(problem([chore(4)], ["unscheduled"], LOAD_1H), "dl")


def test_daily_load_on_some_days_leaves_the_others_alone() -> None:
    weekends = [dict(type="daily_load", name="dl", weight=5, params=dict(threshold="1h", days=["sat", "sun"]))]
    mondays = [dict(type="daily_load", name="dl", weight=5, params=dict(threshold="1h", days=["mon"]))]
    six_on_monday = plan(item_1=(0, 1, 2, 3, 4, 5))
    assert cost(problem([chore(6)], extra=weekends), six_on_monday, "dl") == 0
    assert cost(problem([chore(6)], extra=mondays), six_on_monday, "dl") == 2 * 125


def test_daily_load_across_the_zone_boundary() -> None:
    p = zone_problem([chore(6)], extra=LOAD_1H)
    assert cost(p, plan(item_1=(B, B + 1, B + 2)), "dl") == 2 * 125


# even_load: weight 1 × the spread dial; a day's hard units above ⌈hard work due in the horizon / days⌉, or the
# floor when that is more (0 here, so small cases show the share)

EVEN = [dict(type="even_load", name="even", params=dict(floor=0))]  # under its own name, with no other rule


NOT_10_TO_11 = [dict(type="time_preference", name="window", params=dict(start="11:00", end="10:00", price="forbid"))]


def hard(units: int, due: int):  # noqa: ANN201
    return item("assignment", 1, duration_units=units, due_utc=due, min_chunk_units=1)


def test_even_load_is_zero_when_shared_evenly() -> None:
    p = problem([hard(8, at(1, "20:00"))], ["even"], EVEN, slots=None, days=2)
    monday, tuesday = p.grid.day_slots[0][:4], [s for s in p.grid.day_slots[1] if s in p.items["item:1"].allowed_set]
    assert cost(p, plan(item_1=(*monday, *tuesday[:4])), "even") == 0


def test_even_load_counts_units_above_the_even_share() -> None:
    p = problem([hard(8, at(1, "20:00"))], ["even"], EVEN, slots=None, days=2)
    assert cost(p, plan(item_1=tuple(p.grid.day_slots[0][:8])), "even") == 4 * 25  # share 4 a day
    spread = problem([hard(8, at(1, "20:00"))], ["even"], EVEN, slots=None, days=2,
                     scales=[scales(Dials(spread=3.0)), scales(Dials())])  # fmt: skip
    assert cost(spread, plan(item_1=tuple(spread.grid.day_slots[0][:8])), "even") == 4 * 75


def test_even_load_is_avoided_across_two_days() -> None:
    p = problem([hard(4, at(1, "10:45"))], ["late_work"], [*NOT_10_TO_11, *EVEN], slots=None, days=2)
    assert len(p.items["item:1"].allowed) == 8  # 10:00–11:00 both days; late slots stay allowed, just priced
    assert_avoided(p, "even")


def test_even_load_across_the_zone_boundary() -> None:
    p = zone_problem([hard(6, at(1, "06:00"))], ["even"], EVEN)
    assert cost(p, plan(item_1=(B, B + 1, B + 2)), "even") == 3 * 25  # share 3; 6 units on Tuesday


def test_even_load_leaves_a_light_day_alone() -> None:
    p = problem([hard(12, at(1, "20:00"))], ["even_load"], slots=None, days=2)  # share 6, under the 3-hour floor
    assert cost(p, plan(item_1=tuple(p.grid.day_slots[0][:12])), "even_load") == 0
    heavy = problem([hard(32, at(1, "20:00"))], ["even_load"], slots=None, days=2)  # share 16
    assert cost(heavy, plan(item_1=tuple(heavy.grid.day_slots[0][:20])), "even_load") == 4 * 25


# chunk_cost: weight 10; chunks above one, each costing chunk_cost × size in hours


def chunky(units: int = 4):  # noqa: ANN201
    return item("assignment", 1, duration_units=units, chunk_cost=0.5, min_chunk_units=1)


def test_chunk_cost_is_zero_for_one_chunk() -> None:
    assert cost(problem([chunky()], ["chunk_cost"]), plan(item_1=(0, 1, 2, 3)), "chunk_cost") == 0


def test_chunk_cost_counts_extra_chunks_by_size() -> None:
    assert cost(problem([chunky()], ["chunk_cost"]), plan(item_1=(0, 1, 3, 4)), "chunk_cost") == 500


def test_chunk_cost_is_avoided() -> None:
    assert_avoided(problem([chunky(2)], ["chunk_cost", "unscheduled"]), "chunk_cost")


def test_a_chunk_runs_across_the_zone_boundary() -> None:
    p = zone_problem([chunky()], ["chunk_cost"])
    assert cost(p, plan(item_1=(B - 2, B - 1, B)), "chunk_cost") == 0  # 03:30–04:30 is one chunk
    assert cost(p, plan(item_1=(B - 2, B + 1)), "chunk_cost") == 500


# spread: weight 3; per day, units above ⌈need / days with allowed time⌉


def spreading(units: int):  # noqa: ANN201
    return item("exam_prep", 1, duration_units=units, min_chunk_units=1)


def test_spread_is_zero_when_spread() -> None:
    p = problem([spreading(4)], ["spread"], slots=None, days=2)
    tuesday = [s for s in p.grid.day_slots[1] if s in p.items["item:1"].allowed_set]
    assert cost(p, plan(item_1=(*p.grid.day_slots[0][:2], *tuesday[:2])), "spread") == 0


def test_spread_counts_units_above_the_daily_share() -> None:
    p = problem([spreading(4)], ["spread"], slots=None, days=2)
    assert cost(p, plan(item_1=tuple(p.grid.day_slots[0][:4])), "spread") == 2 * 75


def test_spread_is_avoided() -> None:
    p = problem([spreading(2)], ["spread", "unscheduled"], NOT_10_TO_11, slots=None, days=2)
    assert_avoided(p, "spread")


def test_spread_across_the_zone_boundary() -> None:
    p = zone_problem([spreading(6)], ["spread"])
    assert cost(p, plan(item_1=(B, B + 1, B + 2)), "spread") == 3 * 75


# cluster: weight 3; days used above one, per_day 2 each


def clustering(units: int):  # noqa: ANN201
    return item("project", 1, duration_units=units, min_chunk_units=1)


def test_cluster_is_zero_on_one_day() -> None:
    p = problem([clustering(2)], ["cluster"], slots=None, days=2)
    assert cost(p, plan(item_1=tuple(p.grid.day_slots[0][:2])), "cluster") == 0


def test_cluster_counts_extra_days() -> None:
    p = problem([clustering(2)], ["cluster"], slots=None, days=2)
    tuesday = [s for s in p.grid.day_slots[1] if s in p.items["item:1"].allowed_set]
    assert cost(p, plan(item_1=(p.grid.day_slots[0][0], tuesday[0])), "cluster") == 600


def test_cluster_is_avoided() -> None:
    p = problem([clustering(2)], ["cluster", "unscheduled"], NOT_10_TO_11, slots=None, days=2)
    assert_avoided(p, "cluster")


def test_cluster_across_the_zone_boundary() -> None:
    p = zone_problem([clustering(4)], ["cluster"])
    assert cost(p, plan(item_1=(B - 1, B, B + 1)), "cluster") == 600  # Monday's planning day, then Tuesday's


# batch_by_day: weight 2 per extra day a group of in-scope items uses


BATCH = [dict(type="batch_by_day", name="batch", weight=2, params=dict(by="preset"), scope=dict(preset="Chore"))]


def chores():  # noqa: ANN201
    return [item("chore", 1, duration_units=1), item("chore", 2, duration_units=1)]


def test_batch_by_day_is_zero_on_one_day() -> None:
    p = problem(chores(), extra=BATCH, slots=None, days=2)
    assert cost(p, plan(item_1=(p.grid.day_slots[0][0],), item_2=(p.grid.day_slots[0][2],)), "batch") == 0


def test_batch_by_day_counts_extra_days() -> None:
    p = problem(chores(), extra=BATCH, slots=None, days=2)
    tuesday = [s for s in p.grid.day_slots[1] if s in p.items["item:2"].allowed_set]
    assert cost(p, plan(item_1=(p.grid.day_slots[0][0],), item_2=(tuesday[0],)), "batch") == 200


def test_batch_by_day_is_avoided() -> None:
    p = problem(chores(), ["unscheduled"], [*BATCH, *NOT_10_TO_11], slots=None, days=2)
    assert_avoided(p, "batch", "item:1")
    assert_avoided(p, "batch", "item:2")


def test_batch_by_day_across_the_zone_boundary() -> None:
    p = zone_problem(chores(), extra=BATCH)
    assert cost(p, plan(item_1=(B - 1,), item_2=(B,)), "batch") == 200


# target_shortfall: below-hinges at 40 % (slope 8) and 100 % (slope 3) of the target


def goal(units: int, due: int = MON10 + 120):  # noqa: ANN201
    return item("goal", 1, target_units=units, release_utc=MON10, due_utc=due, min_chunk_units=1, neglect_carry=0)


def test_target_shortfall_is_zero_when_met() -> None:
    assert cost(problem([goal(8)], ["target_shortfall"]), plan(item_1=tuple(range(8))), "target_shortfall") == 0


def test_target_shortfall_first_hours_count_most() -> None:
    p = problem([goal(8)], ["target_shortfall"])
    assert cost(p, plan(item_1=(0, 1)), "target_shortfall") == 200 * 2 + 75 * 6  # below ⌈3.2⌉ = 4 and below 8
    easy = problem([goal(8)], ["target_shortfall"], scales=[scales(Dials(growth=0.0))])
    assert cost(easy, plan(item_1=()), "target_shortfall") == 0


def test_target_shortfall_is_avoided() -> None:
    assert_avoided(problem([goal(4)], ["target_shortfall"]), "target_shortfall")


def test_target_shortfall_across_the_zone_boundary() -> None:
    p = zone_problem([item("goal", 1, target_units=8, release_utc=at(0, "23:00"), due_utc=at(1, "06:00"),
                           min_chunk_units=1)], ["target_shortfall"])  # fmt: skip
    assert cost(p, plan(item_1=(B,)), "target_shortfall") == 2 * 200 + 6 * 75


# elastic_shortfall: below min (steep 20) and below ideal (gentle 2)


def lunch(lo: int, ideal: int, hi: int, due: int = MON10 + 120):  # noqa: ANN201
    return item("routine", 1, min_units=lo, ideal_units=ideal, max_units=hi, release_utc=MON10, due_utc=due)


def test_elastic_shortfall_is_zero_at_ideal() -> None:
    assert cost(problem([lunch(2, 4, 4)], ["elastic_shortfall"]), plan(item_1=(0, 1, 2, 3)), "elastic_shortfall") == 0


def test_elastic_shortfall_hinges() -> None:
    p = problem([lunch(2, 4, 4)], ["elastic_shortfall"])
    assert cost(p, plan(item_1=(0,)), "elastic_shortfall") == 500 + 150  # 1 below min (500/unit), 3 below ideal


def test_elastic_shortfall_is_avoided() -> None:
    assert_avoided(problem([lunch(1, 2, 3)], ["elastic_shortfall"]), "elastic_shortfall")


def test_elastic_shortfall_across_the_zone_boundary() -> None:
    p = zone_problem([item("routine", 1, min_units=2, ideal_units=4, max_units=4, release_utc=at(0, "23:00"),
                           due_utc=at(1, "06:00"))], ["elastic_shortfall"])  # fmt: skip
    assert cost(p, plan(item_1=(B,)), "elastic_shortfall") == 2 * 50


# open_value: per day, below-hinges at half the ceiling (slope 1) and the ceiling (0.5), × the growth dial


def book(ceiling: int):  # noqa: ANN201
    return item("side_project", 1, daily_ceiling_units=ceiling, min_chunk_units=1)


def test_open_value_is_zero_at_the_ceiling() -> None:
    assert cost(problem([book(4)], ["open_value"]), plan(item_1=(0, 1, 2, 3)), "open_value") == 0


def test_open_value_first_hours_are_worth_most_and_growth_scales_it() -> None:
    assert cost(problem([book(4)], ["open_value"]), plan(item_1=()), "open_value") == 25 * 2 + 12 * 4
    easy = problem([book(4)], ["open_value"], scales=[scales(Dials(growth=0.0))])
    assert cost(easy, plan(item_1=()), "open_value") == 0


def test_open_value_is_avoided() -> None:
    p = problem([book(4)], ["open_value"])
    assert all(len(best["item:1"]) == 4 for best in brute_force(p).plans)


def test_open_value_across_the_zone_boundary() -> None:
    p = zone_problem([book(4)], ["open_value"])
    # Monday's day empty: 2 × 25 + 4 × 12; Tuesday holds 2 of 4 units: 2 below the ceiling × 12
    assert cost(p, plan(item_1=(B,)), "open_value") == 98 + 24


# minimize_changes: units of the current plan given up, 1 pt/h, preferred pins × 10. Split in two by the planner
# (29 Oct): undated work's planned place is held by minimize_changes_undated, among preferences; the rest as before.


def test_minimize_changes_is_zero_when_nothing_moves() -> None:
    p = problem([chore(4)], ["minimize_changes"], current={1: [(MON10, MON10 + 60)]})
    assert cost(p, plan(item_1=(0, 1, 2, 3)), "minimize_changes") == 0


def test_minimize_changes_counts_units_given_up_and_preferred_pins_more() -> None:
    p = problem([chore(4)], ["minimize_changes"], current={1: [(MON10, MON10 + 60)]})
    assert cost(p, plan(item_1=(0, 1, 6, 7)), "minimize_changes_undated") == 50  # an undated chore's place
    assert cost(p, plan(item_1=(0, 1, 6, 7)), "minimize_changes") == 0
    pinned = problem([chore(4)], ["minimize_changes"], current={1: [(MON10, MON10 + 60)]},
                     pins=[Pin(1, MON10, MON10 + 30, "preferred")])  # fmt: skip
    assert cost(pinned, plan(item_1=(1, 3, 6, 7)), "minimize_changes") == 25 * 10  # its pin, held as before
    assert cost(pinned, plan(item_1=(1, 3, 6, 7)), "minimize_changes_undated") == 25


def test_minimize_changes_holds_dated_work_in_wellbeing_and_undated_among_preferences() -> None:
    due = item("chore", 1, duration_units=4, shape="split", min_chunk_units=1, due_utc=MON10 + 600)
    p = problem([due], ["minimize_changes"], current={1: [(MON10, MON10 + 60)]})
    assert cost(p, plan(item_1=(0, 1, 6, 7)), "minimize_changes") == 50
    assert cost(p, plan(item_1=(0, 1, 6, 7)), "minimize_changes_undated") == 0
    stages = {r.name: r.stage for r in p.rules}
    assert stages["minimize_changes"] == "wellbeing" and stages["minimize_changes_undated"] == "preferences"


def test_minimize_changes_is_avoided_by_staying_put() -> None:
    p = problem([chore(2)], ["minimize_changes", "unscheduled"], current={1: [(MON10 + 60, MON10 + 90)]})
    assert_avoided(p, "minimize_changes")


def test_minimize_changes_across_the_zone_boundary() -> None:
    p = zone_problem([chore(3)], ["minimize_changes"], current={1: [(at(1, "04:00"), at(1, "04:30"))]})
    assert cost(p, plan(item_1=(B + 2,)), "minimize_changes_undated") == 50


# buffer: weight 3; a chunk that starts right after other work costs, per unit of that work inside its buffer


BUFFER_30M = [dict(type="buffer", name="buf", weight=3, params=dict(minutes="30m"))]


def split_chores(*units: int):  # noqa: ANN201
    return [item("chore", n + 1, duration_units=u, shape="split", min_chunk_units=1) for n, u in enumerate(units)]


def test_buffer_is_zero_with_room_before_each_start() -> None:
    p = problem(split_chores(2, 2), extra=BUFFER_30M)
    assert cost(p, plan(item_1=(0, 1), item_2=(4, 5)), "buf") == 0  # 30 minutes free between them


def test_buffer_counts_work_inside_it() -> None:
    p = problem(split_chores(2, 2), extra=BUFFER_30M)
    assert cost(p, plan(item_1=(0, 1), item_2=(2, 3)), "buf") == 2 * 75  # both units of item 1 are inside
    assert cost(p, plan(item_1=(0, 1), item_2=(3, 4)), "buf") == 1 * 75  # one is


def test_buffer_is_avoided() -> None:
    p = problem(
        split_chores(2, 2), ["unscheduled"], [dict(type="buffer", name="buf", weight=3, params=dict(minutes="15m"))]
    )
    assert_avoided(p, "buf")


def test_buffer_across_the_zone_boundary() -> None:
    p = zone_problem(split_chores(2, 2), extra=BUFFER_30M)
    # Mon 03:30 and 03:45 (1 unit each) right before a start at 04:00 (the first 30-minute slot)
    assert cost(p, plan(item_1=(B - 2, B - 1), item_2=(B,)), "buf") == 2 * 75


def test_minimize_changes_weighs_the_timers_hold_like_a_pin_without_one() -> None:
    held = problem([chore(4)], ["minimize_changes"], hold=(1, MON10, MON10 + 30))
    assert cost(held, plan(item_1=(0, 1, 2, 3)), "minimize_changes") == 0
    assert cost(held, plan(item_1=(2, 3, 4, 5)), "minimize_changes") == 2 * 25 * 10
    assert held.items["item:1"].preferred == frozenset()  # no pin, so no block edge


# same_course: weight 2, a count each time work goes straight on from one course to another (8 Nov)


COURSES = [dict(type="same_course", name="course", weight=2)]


def courses(units: int = 2):  # noqa: ANN201
    return [item("assignment", 1, title="MATH 1920 HW10", duration_units=units, min_chunk_units=1),
            item("assignment", 2, title="CHEM 2090 PS9", duration_units=units, min_chunk_units=1)]  # fmt: skip


def test_same_course_is_zero_with_a_break_between_courses() -> None:
    p = problem(courses(), extra=COURSES)
    assert cost(p, plan(item_1=(0, 1), item_2=(3, 4)), "course") == 0
    assert cost(p, plan(item_1=(0, 1), item_2=(2, 3)), "course") == 200  # straight on: one switch


def test_same_course_counts_each_switch() -> None:
    p = problem(courses(), extra=COURSES)
    assert cost(p, plan(item_1=(0, 2), item_2=(1, 3)), "course") == 3 * 200  # math, chem, math, chem


def test_same_course_is_avoided() -> None:
    p = problem(courses(1), ["unscheduled"], COURSES, slots=3)
    assert_avoided(p, "course", "item:1")
    assert_avoided(p, "course", "item:2")


def test_same_course_across_the_zone_boundary() -> None:
    p = zone_problem(courses(1), extra=COURSES)
    assert cost(p, plan(item_1=(B - 1,), item_2=(B,)), "course") == 200


def test_same_course_reads_the_course_from_titles() -> None:
    from friday.engine.rules.measures import course_groups

    titles = ["MATH 1920 HW10", "Math read 17.3", "CS A5 Design Doc", "PHYS 2213 PS3", "Read ch 3", "Laundry"]
    p = problem([item("assignment", n, title=t, duration_units=1) for n, t in enumerate(titles, 1)])
    groups = {c: sorted(m.key for m in ms) for c, ms in course_groups(list(p.items.values())).items()}
    assert groups == {"MATH": ["item:1", "item:2"], "CS": ["item:3"], "PHYS": ["item:4"]}
