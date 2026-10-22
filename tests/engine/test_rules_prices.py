"""Price rules, four tests each (DESIGN §12.5): zero when untriggered, an exact hand-computed value,
avoidance when a free alternative exists, and the 15/30-minute zone boundary. Costs are in scaled points,
100 to the point; a slot costs round(weight × price per hour × hours × 100)."""

from datetime import date

from friday.core.pace import Dials, scales
from friday.engine.evaluate import evaluate
from tests.engine.brute import brute_force
from tests.engine.direct_eval import direct_rule_costs
from tests.engine.helpers import BOUNDARY, MON10, at, item, plan, problem, zone_problem

B = BOUNDARY
FAR = at(6, "12:00")  # a due date beyond every test horizon


def cost(p, slots_by_item, rule: str) -> int:  # noqa: ANN001
    ev = evaluate(p, slots_by_item)
    assert ev.rule_totals == direct_rule_costs(p, slots_by_item)
    return ev.rule_totals[rule]


def assert_avoided(p, rule: str, key: str = "item:1") -> None:  # noqa: ANN001
    """Every optimal plan places all of the item and pays nothing for the rule."""
    result = brute_force(p)
    for best in result.plans:
        assert evaluate(p, best).rule_totals[rule] == 0
        assert sum(int(p.grid.units[s]) for s in best[key]) >= p.items[key].need


# late_work: weight 10, importance × hours late, overflow priced at the horizon end plus 48 h


def test_late_work_is_zero_on_time() -> None:
    p = problem([item("assignment", 1, duration_units=4, due_utc=MON10 + 60, importance=4)], ["late_work"])
    assert cost(p, plan(item_1=(0, 1, 2, 3)), "late_work") == 0


def test_late_work_slot_and_overflow_prices() -> None:
    p = problem([item("assignment", 1, duration_units=4, due_utc=MON10 + 60, importance=4)], ["late_work"])
    assert cost(p, plan(item_1=(1, 2, 3, 4)), "late_work") == 250  # last slot ends 0.25 h late: 4 × 0.25 × 10 × 0.25
    assert cost(p, plan(item_1=()), "late_work") == 4 * 49_000  # per unit: 4 × (1 h + 48 h) × 0.25 × 10
    far = problem([item("assignment", 1, duration_units=4, due_utc=FAR, importance=4)], ["late_work"])
    assert cost(far, plan(item_1=()), "late_work") == 0  # due beyond the horizon: overflow isn't late yet


def test_late_work_is_avoided_when_time_before_the_due_is_free() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=MON10 + 45, min_chunk_units=1)], ["late_work"])
    assert_avoided(p, "late_work")


def test_late_work_across_the_zone_boundary() -> None:
    p = zone_problem([item("assignment", 1, duration_units=2, due_utc=at(1, "04:15"), importance=4)], ["late_work"])
    assert cost(p, plan(item_1=(B,)), "late_work") == 500  # 04:00–04:30 ends 0.25 h late: 4 × 0.25 × 10 × 0.5 h
    assert cost(p, plan(item_1=(B - 2, B - 1)), "late_work") == 0


# soft_late: weight 3, the same formula for soft deadlines


def test_soft_late_is_zero_on_time_and_ignores_hard_items() -> None:
    p = problem([item("reading", 1, duration_units=4, due_utc=MON10 + 60, importance=4),
                 item("assignment", 2, duration_units=4, due_utc=MON10, importance=4)], ["soft_late"])  # fmt: skip
    assert cost(p, plan(item_1=(0, 1, 2, 3), item_2=(4, 5, 6, 7)), "soft_late") == 0


def test_soft_late_exact() -> None:
    p = problem([item("reading", 1, duration_units=4, due_utc=MON10 + 60, importance=4)], ["soft_late"])
    assert cost(p, plan(item_1=(1, 2, 3, 4)), "soft_late") == 75


def test_soft_late_is_avoided() -> None:
    p = problem([item("reading", 1, duration_units=2, due_utc=MON10 + 45, min_chunk_units=1)], ["soft_late"])
    assert_avoided(p, "soft_late")


def test_soft_late_across_the_zone_boundary() -> None:
    p = zone_problem([item("reading", 1, duration_units=2, due_utc=at(1, "04:15"), importance=4)], ["soft_late"])
    assert cost(p, plan(item_1=(B,)), "soft_late") == 150


# unscheduled: weight 0.5, base × importance per overflow hour, for work with no hard due in the horizon and no due
# after it (the allocator's quotas pace that)


def test_unscheduled_is_zero_when_placed_and_skips_hard_work_due_inside() -> None:
    p = problem([item("chore", 1, duration_units=4, importance=2),
                 item("assignment", 2, duration_units=2, due_utc=MON10 + 60)], ["unscheduled"])  # fmt: skip
    assert cost(p, plan(item_1=(0, 1, 2, 3), item_2=()), "unscheduled") == 0


def test_unscheduled_leaves_work_due_after_the_horizon_to_the_allocator() -> None:
    p = problem([item("reading", 1, duration_units=4, due_utc=at(3, "12:00"))], ["unscheduled"])
    assert cost(p, plan(item_1=()), "unscheduled") == 0


def test_unscheduled_prices_overflow_only() -> None:
    p = problem([item("chore", 1, duration_units=4, importance=2)], ["unscheduled"])
    assert cost(p, plan(item_1=()), "unscheduled") == 4 * 25  # 0.5 × 2 pt/h × 0.25 h per unit


def test_unscheduled_is_avoided_by_placing_the_work() -> None:
    assert_avoided(problem([item("chore", 1, duration_units=2)], ["unscheduled"]), "unscheduled")


def test_unscheduled_across_the_zone_boundary() -> None:
    p = zone_problem([item("chore", 1, duration_units=3, shape="split", min_chunk_units=1, importance=2)],
                     ["unscheduled"])  # fmt: skip
    assert cost(p, plan(item_1=(B, B + 1)), "unscheduled") == 0  # two 30-minute slots hold all 3 units
    assert cost(p, plan(item_1=(B,)), "unscheduled") == 25  # one unit left over


# late_night: a × (min(τ, bed) − 22) + b × debt × (τ − bed), weight × the rest dial


def test_late_night_is_zero_in_the_day() -> None:
    p = problem([item("chore", 1, duration_units=1)], ["late_night"])
    assert cost(p, plan(item_1=(0,)), "late_night") == 0


def test_late_night_gradient_and_margin() -> None:
    p = problem([item("chore", 1, duration_units=1)], ["late_night"], now=at(0, "22:15"))
    assert cost(p, plan(item_1=(0,)), "late_night") == 25  # ends 22:30: 2 × 0.5 = 1 pt/h
    assert cost(p, plan(item_1=(6,)), "late_night") == 325  # ends 24:00: 2 × 1.5 + 20 × 0.5 = 13 pt/h


def test_late_night_sleep_debt_and_the_rest_dial() -> None:
    chore = [item("chore", 1, duration_units=1)]
    base = problem(chore, ["late_night"], now=at(0, "23:45"), slots=1)
    assert cost(base, plan(item_1=(0,)), "late_night") == round((2 * 1.5 + 20 * 0.5) * 25)
    rested = problem(chore, ["late_night"], now=at(0, "23:45"), slots=1, scales=[scales(Dials(rest=2.0))],
                     debt_hours={date(2026, 10, 19): 2.0})  # fmt: skip
    # weight × rest 2; debt multiplier 1 + 0.5 × rest 2 × 2 h = 3: 2 × (2 × 1.5 + 20 × 3 × 0.5) × 0.25 × 100
    assert cost(rested, plan(item_1=(0,)), "late_night") == 1650


def test_late_night_prices_the_first_hour_after_waking_gently() -> None:
    p = problem([item("chore", 1, duration_units=1)], ["late_night"], slots=None, days=2)
    wake = p.nights[date(2026, 10, 19)].wake_utc  # Tuesday morning
    assert cost(p, plan(item_1=(p.grid.slot_at(wake),)), "late_night") == 50  # 2 pt/h for 15 minutes
    assert cost(p, plan(item_1=(p.grid.slot_at(wake + 45),)), "late_night") == 50
    assert cost(p, plan(item_1=(p.grid.slot_at(wake + 60),)), "late_night") == 0


def test_late_night_is_avoided_before_the_gradient() -> None:
    p = problem([item("chore", 1, duration_units=2, shape="split", min_chunk_units=1)], ["late_night", "unscheduled"],
                now=at(0, "21:00"))  # fmt: skip
    assert_avoided(p, "late_night")


def test_late_night_across_the_zone_boundary() -> None:
    p = zone_problem([item("chore", 1, duration_units=3, shape="split", min_chunk_units=1)], ["late_night"])
    evening = p.grid.slot_at(at(1, "22:00"))
    assert p.grid.units[evening] == 2
    # Mon 23:45 ends at 24:00 before a 02:00 bedtime: 2 × 2 = 4 pt/h × 0.25 h; Tue 22:00–22:30: 1 pt/h × 0.5 h
    assert cost(p, plan(item_1=(3, evening)), "late_night") == 100 + 50


# time_preference: a price, or FORBID, on matching weekdays and hours


EXTRA_REST = [
    dict(type="time_preference", name="rest", weight=2, params=dict(days=["mon"], price=4)),
    dict(type="time_preference", name="nope", params=dict(start="10:00", end="10:30", price="forbid")),
]


def test_time_preference_is_zero_on_other_days() -> None:
    p = problem([item("chore", 1, duration_units=4)], extra=[dict(type="time_preference", name="tue",
                                                                  params=dict(days=["tue"], price=4))])  # fmt: skip
    assert cost(p, plan(item_1=(0, 1, 2, 3)), "tue") == 0


def test_time_preference_price_and_forbid() -> None:
    p = problem([item("chore", 1, duration_units=4)], extra=EXTRA_REST)
    assert 0 not in p.items["item:1"].allowed_set and 1 not in p.items["item:1"].allowed_set
    assert cost(p, plan(item_1=(2, 3)), "rest") == 400  # 2 × 4 pt/h × 0.25 h per slot


def test_time_preference_is_avoided() -> None:
    rule = dict(type="time_preference", name="morning", params=dict(start="10:00", end="10:30", price=4))
    p = problem([item("chore", 1, duration_units=2, shape="split", min_chunk_units=1)], ["unscheduled"], [rule])
    assert_avoided(p, "morning")


def test_time_preference_across_the_zone_boundary() -> None:
    rule = dict(type="time_preference", name="early", params=dict(start="04:00", end="05:00", price=1))
    p = zone_problem([item("chore", 1, duration_units=3, shape="split", min_chunk_units=1)], extra=[rule])
    assert cost(p, plan(item_1=(B - 1, B)), "early") == 50  # 03:45 is outside; 04:00–04:30 is 1 pt/h × 0.5 h


# energy: energy_map[weekday][half hour] for deep work


def test_energy_is_zero_in_good_hours_and_for_light_work() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=FAR), item("reading", 2, duration_units=2)],
                ["energy"], now=at(0, "08:00"))  # fmt: skip
    assert cost(p, plan(item_1=(), item_2=(0, 1)), "energy") == 0
    assert cost(problem([item("assignment", 1, duration_units=2, due_utc=FAR)], ["energy"]), plan(item_1=(0, 1)),
                "energy") == 0  # fmt: skip


def test_energy_uses_the_weekday_hour_map() -> None:
    p = problem([item("assignment", 1, duration_units=2, due_utc=FAR)], ["energy"], now=at(0, "08:00"))
    assert cost(p, plan(item_1=(0, 1)), "energy") == 50  # 08:xx costs 1 pt/h


def test_energy_is_avoided_in_free_hours() -> None:
    p = problem([item("assignment", 1, duration_units=2, min_chunk_units=1)], ["energy", "unscheduled"],
                now=at(0, "09:30"))  # fmt: skip
    assert_avoided(p, "energy")


def test_energy_across_the_zone_boundary() -> None:
    p = zone_problem([item("assignment", 1, duration_units=2, due_utc=FAR)], ["energy"])
    assert cost(p, plan(item_1=(B,)), "energy") == 150  # 04:xx costs 3 pt/h × 0.5 h


# finish_early: min(L, days into the lead zone before the due)


FINISH = [dict(type="finish_early", name="fe", params=dict(days=2))]


def test_finish_early_is_zero_before_the_lead_zone() -> None:
    p = problem([item("reading", 1, duration_units=4, due_utc=FAR)], extra=FINISH)
    assert cost(p, plan(item_1=(0, 1, 2, 3)), "fe") == 0


def test_finish_early_exact() -> None:
    p = problem([item("reading", 1, duration_units=4, due_utc=MON10 + 2880)], extra=FINISH)
    assert cost(p, plan(item_1=(0, 1, 2, 3)), "fe") == sum(round(m / 1440 * 25) for m in (15, 30, 45, 60))
    assert cost(p, plan(item_1=()), "fe") == 4 * round(120 / 1440 * 25)  # overflow, priced at the horizon end


def test_finish_early_is_avoided_by_working_early() -> None:
    p = problem([item("reading", 1, duration_units=2, due_utc=MON10 + 2880 + 60, min_chunk_units=1)],
                ["unscheduled"], FINISH)  # fmt: skip
    assert_avoided(p, "fe")


def test_finish_early_across_the_zone_boundary() -> None:
    p = zone_problem([item("reading", 1, duration_units=2, due_utc=at(3, "04:30"))], extra=FINISH)
    assert cost(p, plan(item_1=(B,)), "fe") == 0  # ends exactly where the lead zone starts
    assert cost(p, plan(item_1=(B + 1,)), "fe") == round(30 / 1440 * 50)


# after_event: pulls items to start right after matching fixed items


AFTER = [dict(type="after_event", name="ae", params=dict(events=dict(event_kind="class"), slope=2, cap=3))]


def lecture(start: int, end: int):  # noqa: ANN201
    return item("class", 9, start_utc=start, end_utc=end, event_kind="class", buffer_after_min=0, buffer_before_min=0)


def test_after_event_is_zero_on_days_without_a_match() -> None:
    p = problem([item("habit", 2, duration_units=1)], extra=AFTER)
    assert cost(p, plan(item_2=(3,)), "ae") == 0


def test_after_event_distance_and_cap() -> None:
    p = problem([lecture(MON10 - 120, MON10 + 30), item("habit", 2, duration_units=1)], extra=AFTER,
                now=MON10 - 60, slots=12)  # fmt: skip
    g = p.grid
    assert cost(p, plan(item_2=(g.slot_at(MON10 + 30),)), "ae") == 0  # starts as the class ends
    assert cost(p, plan(item_2=(g.slot_at(MON10 + 60),)), "ae") == 25  # 30 min later: 2 × 0.5 pt/h
    assert cost(p, plan(item_2=(g.slot_at(MON10 + 105),)), "ae") == round(2.5 * 25)  # 75 min: 2.5 pt/h, under the cap


def test_after_event_is_avoided_by_starting_right_after() -> None:
    p = problem([lecture(MON10 - 60, MON10 + 30), item("habit", 2, duration_units=1)], ["unscheduled"], AFTER)
    assert_avoided(p, "ae", "item:2")


def test_after_event_across_the_zone_boundary() -> None:
    p = zone_problem([lecture(at(1, "04:00"), at(1, "04:30")), item("habit", 2, duration_units=2)], extra=AFTER)
    assert cost(p, plan(item_2=(B + 2,)), "ae") == 50  # 05:00 is 30 min after: 1 pt/h × 0.5 h
