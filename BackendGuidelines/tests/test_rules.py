"""Rule costs worked out by hand from ENGINE_REFERENCE section 7, in scaled integer points (100 = 1 point)."""
from fr.core.builder import Pin, spec
from fr.core.direct import direct_rule_costs
from fr.core.evaluate import evaluate
from fr.core.problem import DayScales
from helpers import MON10, at, problem


def cost(p, plan, rule):
    ev = evaluate(p, plan)
    assert ev.rule_totals == direct_rule_costs(p, plan)
    return ev.rule_totals[rule]


def test_late_work_slot_price():
    # importance 4, due 11:00, one slot ends 11:15 -> 0.25 h late: 4 * 0.25 = 1 pt/h * 0.25 h * weight 10
    s = [spec("assignment", 1, due=MON10 + 60, duration_min=60, importance=4)]
    p = problem(s, ["late_work"])
    assert cost(p, {"item:1": (1, 2, 3, 4)}, "late_work") == 250
    assert cost(p, {"item:1": (0, 1, 2, 3)}, "late_work") == 0


def test_late_work_overflow_price():
    # due 11:00, horizon end 12:00: (1 h + 48 h) * importance 4 = 196 pt/h; per unit 196 * 0.25 * 10 * 100
    s = [spec("assignment", 1, due=MON10 + 60, duration_min=60, importance=4)]
    p = problem(s, ["late_work"])
    assert cost(p, {"item:1": ()}, "late_work") == 4 * 49000


def test_late_work_overflow_is_free_when_due_is_beyond_horizon():
    s = [spec("assignment", 1, due=MON10 + 600, duration_min=60, importance=4)]
    p = problem(s, ["late_work"])
    assert cost(p, {"item:1": ()}, "late_work") == 0


def test_unscheduled_prices_overflow_only():
    s = [spec("chore", 1, duration_min=60, importance=2)]  # firmness none
    p = problem(s, ["unscheduled"])
    assert cost(p, {"item:1": ()}, "unscheduled") == 4 * 25  # 2 pt/h * .25 h * w .5 * 100 per unit
    assert cost(p, {"item:1": (0, 1, 2, 3)}, "unscheduled") == 0


def test_unscheduled_skips_hard_work_due_inside_the_horizon():
    s = [spec("assignment", 1, duration_min=60, due=MON10 + 60)]
    p = problem(s, ["unscheduled"])
    assert cost(p, {"item:1": ()}, "unscheduled") == 0


def test_late_night_gradient_and_margin():
    now = at(7, "22:15")  # Monday evening; bedtime 23:30, margin 60
    s = [spec("chore", 1, duration_min=15, shape="one_sitting")]
    p = problem(s, ["late_night"], now=now, slots=8)
    g = p.grid
    # slot ending 22:30: tau 22.5, gradient 22 -> 2 * 0.5 = 1 pt/h; 0.25 h * 100
    s_a = g.slot_at(at(7, "22:15"))
    assert cost(p, {"item:1": (s_a,)}, "late_night") == 25
    # slot ending 24:00: tau 24, bed 23.5: 2*1.5 + 20*1*0.5 = 13 pt/h -> 0.25 h = 325
    s_b = g.slot_at(at(7, "23:45"))
    assert cost(p, {"item:1": (s_b,)}, "late_night") == 325


def test_late_night_sleep_debt_and_rest_dial():
    now = at(7, "23:45")
    s = [spec("chore", 1, duration_min=15)]
    p = problem(s, ["late_night"], now=now, slots=1)
    base = cost(p, {"item:1": (0,)}, "late_night")
    sc = [DayScales(rest=2.0)]
    p2 = problem(s, ["late_night"], now=now, slots=1, scales=sc * 1)
    # weight x rest and debt_factor x rest, with 2 h of debt: m = 1 + 0.5*2*2 = 3
    from dataclasses import replace
    p2.nights = {d: replace(n, debt_hours=2.0) for d, n in p2.nights.items()}
    p2._price_cache.clear()
    expected = round(1.0 * 2.0 * (2 * 1.5 + 20 * 3 * 0.5) * 0.25 * 100)  # tau 24, bed 23.5, gradient 22
    assert cost(p2, {"item:1": (0,)}, "late_night") == expected
    assert base == round((2 * 1.5 + 20 * 0.5) * 0.25 * 100)


def test_elastic_shortfall_hinges():
    s = [spec("routine", 1, min_min=30, ideal_min=60, max_min=60, release=MON10, due=MON10 + 120)]
    p = problem(s, ["elastic_shortfall"])
    # placed 1 unit: below min(2) steep 20 -> 500/unit * 1; below ideal(4) gentle 2 -> 50/unit * 3
    assert cost(p, {"item:1": (0,)}, "elastic_shortfall") == 500 + 150
    assert cost(p, {"item:1": (0, 1, 2, 3)}, "elastic_shortfall") == 0


def test_target_shortfall_first_hours_count_most():
    s = [spec("goal", 1, target_min=120, release=MON10, due=MON10 + 120, min_chunk_min=15, neglect_carry=0)]
    p = problem(s, ["target_shortfall"])
    # target 8 units, whole window inside the horizon. hinges: below ceil(.4*8)=4 slope 8 (200/unit), below 8 slope 3 (75/unit)
    assert cost(p, {"item:1": (0, 1)}, "target_shortfall") == 200 * 2 + 75 * 6
    assert cost(p, {"item:1": tuple(range(8))}, "target_shortfall") == 0


def test_chunk_cost_counts_extra_chunks_by_size():
    s = [spec("assignment", 1, duration_min=60, due=MON10 + 480, chunk_cost=0.5, min_chunk_min=15)]
    p = problem(s, ["chunk_cost"])
    # slope = chunk_cost * size_hours = 0.5 per extra chunk, weight 10 -> 500
    assert cost(p, {"item:1": (0, 1, 3, 4)}, "chunk_cost") == 500
    assert cost(p, {"item:1": (0, 1, 2, 3)}, "chunk_cost") == 0


def test_daily_load_threshold_is_a_soft_cap():
    s = [spec("chore", 1, duration_min=90, shape="split")]
    extra = [dict(type="daily_load", name="dl", weight=5, params=dict(threshold="1h"))]
    p = problem(s, (), extra)
    # 6 units placed, threshold 4: 2 over * round(5 * .25 * 100)=125
    assert cost(p, {"item:1": (0, 1, 2, 3, 4, 5)}, "dl") == 250


def test_open_value_first_hours_worth_most_and_growth_dial():
    s = [spec("side_project", 1, ceiling_min=60, min_chunk_min=15)]
    p = problem(s, ["open_value"])
    # ceiling 4 units: below 2 slope 1 (25/unit), below 4 slope .5 (12 or 13 -> round(12.5)=12)/unit
    c0 = cost(p, {"item:1": ()}, "open_value")
    assert c0 == 25 * 2 + 12 * 4
    easy = problem(s, ["open_value"], scales=[DayScales(growth=0.0)])
    assert cost(easy, {"item:1": ()}, "open_value") == 0


def test_minimize_changes_counts_units_given_up():
    s = [spec("chore", 1, duration_min=60, shape="split")]
    p = problem(s, ["minimize_changes"], current={"item:1": (0, 1, 2, 3)})
    # each unit given up: 1 pt/h * .25 h * 100 = 25; moved 2 units
    assert cost(p, {"item:1": (0, 1, 6, 7)}, "minimize_changes") == 50


def test_minimize_changes_preferred_pin_units_cost_more():
    s = [spec("chore", 1, duration_min=60, shape="split")]
    pins = [Pin(1, MON10, MON10 + 30, "preferred")]
    p = problem(s, ["minimize_changes"], pins=pins, current={"item:1": (0, 1, 2, 3)})
    # slots 0-1 preferred (x10), slots 2-3 normal; give up 1 of each
    assert cost(p, {"item:1": (1, 3, 6, 7)}, "minimize_changes") == 25 * 10 + 25


def test_time_preference_price_and_forbid():
    s = [spec("chore", 1, duration_min=60)]
    extra = [dict(type="time_preference", name="rest", weight=2, params=dict(days=["mon"], price=4)),
             dict(type="time_preference", name="nope", weight=1, params=dict(start="10:00", end="10:30", price="forbid"))]
    p = problem(s, (), extra)
    assert 0 not in p.items["item:1"].allowed and 1 not in p.items["item:1"].allowed
    # 4 pt/h * .25 h * w 2 = 2 pt per slot
    assert cost(p, {"item:1": (2, 3)}, "rest") == 400


def test_finish_early_pulls_work_ahead_of_the_due_date():
    s = [spec("reading", 1, duration_min=60, due=MON10 + 2880)]  # due in 2 days; lead 2 days
    extra = [dict(type="finish_early", name="fe", weight=1, params=dict(days=2))]
    p = problem(s, (), extra)
    # slot ends 15/30/45/60 min into the lead zone: price = minutes/1440 pt/h, cost round(price*.25*100) each
    assert cost(p, {"item:1": (0, 1, 2, 3)}, "fe") == sum(round(m / 1440 * 25) for m in (15, 30, 45, 60))
    # unplaced units go to the overflow slot, priced at the horizon end (2 h in): 120/1440 pt/h
    assert cost(p, {"item:1": ()}, "fe") == 4 * round(120 / 1440 * 25)


def test_after_event_distance_and_cap():
    cls = spec("class", 1, start=MON10 - 120, end=MON10 + 30, event_kind="class")  # ends 10:30, +5? class buffer after = 0
    hab = spec("habit", 2, duration_min=15)
    extra = [dict(type="after_event", name="ae", weight=1,
                  params=dict(events=dict(event_kind="class"), measure_from="last", slope=2, cap=3))]
    p = problem([cls, hab], (), extra, now=MON10 - 60, slots=12)
    g = p.grid
    hab_key = "item:2"
    # find slot starting at 10:30 (right at the class's end): distance 0 -> cost 0
    s_at = g.slot_at(MON10 + 30)
    assert s_at in p.items[hab_key].allowed_set
    assert cost(p, {hab_key: (s_at,)}, "ae") == 0
    s_later = g.slot_at(MON10 + 60)  # 30 min later -> 2*0.5 = 1 pt/h
    assert cost(p, {hab_key: (s_later,)}, "ae") == 25
    s_far = g.slot_at(MON10 + 105)  # 75 min -> 2 * 1.25 = 2.5 pt/h
    assert cost(p, {hab_key: (s_far,)}, "ae") == round(2.5 * 25)


def test_energy_uses_the_weekday_hour_map():
    s = [spec("assignment", 1, duration_min=60, due=MON10 + 480)]
    p = problem(s, ["energy"])
    # 10:xx -> hour 10 -> 0 ; 08:xx would be 1
    assert cost(p, {"item:1": (0, 1)}, "energy") == 0
    early = problem(s, ["energy"], now=at(7, "08:00"))
    assert cost(early, {"item:1": (0, 1)}, "energy") == round(2 * 1 * 0.25 * 100)  # hour 8 costs 1 pt/h


def test_cluster_counts_extra_days():
    s = [spec("project", 1, duration_min=120, due=at(8, "23:59"), min_chunk_min=15)]
    st = __import__("fr.core.settings", fromlist=["Settings"]).Settings(horizon_days=2, fine_days=2)
    from fr.core.builder import build_problem
    from fr.core.defaults import only
    p = build_problem(s, [], at(7, "10:00"), st, only(["cluster"]))
    g, ok = p.grid, p.items["item:1"].allowed_set
    d0 = [x for x in g.day_slots[0] if x in ok]
    d1 = [x for x in g.day_slots[1] if x in ok]
    # two days used: one extra day * per_day 2 * weight 3 -> round(3*2*100)=600
    assert evaluate(p, {"item:1": (d0[0], d1[0])}).rule_totals["cluster"] == 600
    assert evaluate(p, {"item:1": (d0[0], d0[1])}).rule_totals["cluster"] == 0
