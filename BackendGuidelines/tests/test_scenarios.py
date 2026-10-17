"""ENGINE_REFERENCE 12.1 scenario tests against the v2 CP-SAT baseline (each with its own small rule set).

#10 (daylight saving) is not testable: wall-clock time is a documented simplification. #19 needs the allocator.
"""
import numpy as np
import pytest

from fr.baseline.cpsat import GridModel, solve
from fr.baseline.whatif import lock_conflicts
from fr.core.builder import Pin, spec
from fr.core.evaluate import check, evaluate
from fr.core.generate import Scenario
from fr.core.problem import EASY, PUSH
from fr.core.settings import Settings
from helpers import at, blocks, hours, scn

MON = 7
SAT, SUN = 12, 13


def run(p, **kw):
    res = solve(p, workers=1, **kw)
    assert check(p, res.plan) == [], check(p, res.plan)
    return res


def wall(date, a="07:00", b="23:59"):
    return spec("commitment", 900 + date, "wall", start=at(date, a), end=at(date, b))


def test_01_rest_day_is_used_when_it_is_the_only_free_time():
    s = [wall(SAT - 1, "04:00", "23:59"), wall(SAT, "04:00", "23:59"),
         spec("assignment", 1, "ps", duration_min=120, due=at(SUN, "23:00"), min_chunk_min=15)]
    rest = dict(type="time_preference", name="rest", weight=3, params=dict(days=["sun"], price=5))
    p = scn(s, ["late_work"], [rest], days=3, now=at(SAT - 1, "06:00"))
    res = run(p)
    assert res.evaluation.stage_values["deadlines"] == 0
    assert hours(p, res.plan, "item:1") == 2 and res.evaluation.rule_totals["rest"] > 0


def test_02_overload_returns_a_plan_with_overflow_never_infeasible():
    s = [spec("assignment", 1, "huge", duration_min=60 * 40, due=at(MON + 1, "12:00"), min_chunk_min=15)]
    p = scn(s, ["late_work", "unscheduled"], days=2)
    res = run(p)
    assert res.evaluation.over_units["item:1"] > 0 and res.evaluation.stage_values["deadlines"] > 0


def test_03_a_lock_that_makes_another_item_late_is_named():
    a = spec("assignment", 1, "PS4", duration_min=180, due=at(MON, "18:00"), min_chunk_min=15)
    walls = [spec("commitment", 50, "meeting", start=at(MON, "09:30"), end=at(MON, "15:00")),
             spec("commitment", 51, "dinner", start=at(MON, "18:00"), end=at(MON, "23:00"))]
    gym = spec("chore", 2, "Gym", duration_min=90, shape="one_sitting")
    pin = Pin(2, at(MON, "16:00"), at(MON, "17:30"), "locked")
    sc = Scenario("lock", [a, gym] + walls, [pin], at(MON, "09:00"),
                  Settings(horizon_days=2, fine_days=2, workers=1, det_time=(10, 10, 10)),
                  rule_specs=[dict(type="late_work", name="late_work", weight=10)])
    found = lock_conflicts(sc, workers=1)
    assert found and found[0][0] == pin and found[0][1]["item:1"] > 0


def test_04_replan_with_nothing_changed_moves_nothing():
    s = [spec("assignment", 1, "a", duration_min=90, due=at(MON + 1, "17:00"), min_chunk_min=15, chunk_cost=0.1),
         spec("reading", 2, "r", duration_min=60, due=at(MON + 1, "12:00"), min_chunk_min=15)]
    names = ["late_work", "soft_late", "energy", "chunk_cost", "minimize_changes", "late_night"]
    first = run(scn(s, names, days=2))
    p2 = scn(s, names, days=2, current=first.plan)
    second = run(p2, hint=first.plan)
    assert second.plan == first.plan
    assert second.evaluation.rule_totals["minimize_changes"] == 0


def test_05_preferred_pin_resists_a_slightly_cheaper_slot():
    s = [spec("assignment", 1, "a", duration_min=60, due=at(MON + 1, "17:00"), min_chunk_min=60)]
    energy_pref = dict(type="time_preference", name="dear_afternoon", weight=1, params=dict(start="13:00", end="14:00", price=3))
    pin = Pin(1, at(MON, "13:00"), at(MON, "14:00"), "preferred")
    names = ["late_work", "minimize_changes"]
    base = scn(s, names, [energy_pref], pins=[pin], days=2)
    current = {"item:1": tuple(base.grid.slots_in(at(MON, "13:00"), at(MON, "14:00")))}
    p = scn(s, names, [energy_pref], pins=[pin], days=2, current=current)
    res = run(p, hint=current)
    assert res.plan == current  # moving saves 3 pt but a preferred-pin move costs 10 pt
    # without the preferred pin a move costs 1 pt < 3 pt saved, so the solver moves
    free = scn(s, names, [energy_pref], pins=[], days=2, current=current)
    assert run(free, hint=current).plan != current


def test_06_one_sitting_item_is_one_block_or_all_overflow():
    s = [wall(MON, "11:00", "12:00"), spec("chore", 1, "two hours", duration_min=120)]
    p = scn(s, ["unscheduled", "energy"], [dict(type="time_preference", name="gap", weight=1, params=dict(start="09:00", end="11:00", price=0))], days=1, now=at(MON, "09:00"))
    res = run(p)
    assert len(blocks(p, res.plan, "item:1")) == 1 and hours(p, res.plan, "item:1") == 2
    # no 2 h gap anywhere: everything busy except 1 h slices
    cuts = [spec("commitment", 800 + i, "cut", start=at(MON, f"{h:02d}:00"), end=at(MON, f"{h:02d}:30"))
            for i, h in enumerate(range(9, 23, 2))]
    cuts += [spec("commitment", 850, "cut", start=at(MON, "23:00"), end=at(MON, "23:59"))]
    q = scn([*cuts, spec("chore", 1, "two hours", duration_min=120)], ["unscheduled"], days=1, now=at(MON, "09:00"),
            buffers={"other": (5, 5)})
    r2 = run(q)
    assert r2.plan["item:1"] == () and r2.evaluation.over_units["item:1"] == 8


def test_07_target_is_placed_only_where_the_shortfall_slope_beats_the_slot_price():
    s = [spec("goal", 1, "guitar", target_min=240, release=at(MON, "09:00"), due=at(MON + 1, "04:00"),
              min_chunk_min=15, neglect_carry=0, cap_min=600)]
    price = dict(type="time_preference", name="dear", weight=1, params=dict(price=6))
    p = scn(s, ["target_shortfall"], [price], days=1)
    res = run(p)
    # target 16 units: slope 11 pt/h below ceil(.4*16)=7 units, 3 pt/h above; slot price 6 pt/h -> exactly 7 units
    assert sum(int(p.grid.units[x]) for x in res.plan["item:1"]) == 7


def test_08_batch_by_day_pulls_three_chores_to_saturday():
    s = [spec("chore", i, f"chore{i}", duration_min=60, release=at(SAT - 4, "06:00"), due=at(SUN + 1, "04:00"))
         for i in (1, 2, 3)]
    extra = [dict(type="time_preference", name="sat", weight=1, params=dict(days_except=["sat"], price=1)),
             dict(type="batch_by_day", name="batch", weight=5, params=dict(by="preset"))]
    p = scn(s, ["unscheduled"], extra, days=4, now=at(SAT - 3, "09:00"))
    res = run(p)
    days = {p.grid.slots[x].weekday for k in res.plan for x in res.plan[k]}
    assert days == {5}  # Saturday


def test_09_late_night_pushes_work_before_bedtime_unless_a_deadline_needs_otherwise():
    open_window = [wall(MON, "04:30", "21:00")]
    s1 = open_window + [spec("assignment", 1, "a", duration_min=60, due=at(MON + 1, "04:00"), min_chunk_min=15)]
    p = scn(s1, ["late_work", "late_night"], days=1, now=at(MON, "09:00"))
    res = run(p)
    end = max(p.grid.end[x] for x in res.plan["item:1"])
    assert end <= at(MON, "22:00") + 15  # free evening slots before the gradient start are preferred (buffer 5)
    s2 = open_window + [spec("assignment", 1, "a", duration_min=150, due=at(MON + 1, "00:00"), min_chunk_min=15)]
    q = scn(s2, ["late_work", "late_night"], days=1, now=at(MON, "09:00"))
    r2 = run(q)
    assert r2.evaluation.stage_values["deadlines"] == 0  # deadline met even though it needs the gradient


def test_11_every_rule_total_equals_the_stage_objective():
    s = [spec("assignment", 1, "a", duration_min=90, due=at(MON + 1, "17:00"), min_chunk_min=30, chunk_cost=0.2),
         spec("reading", 2, "r", duration_min=60, due=at(MON + 1, "12:00"), min_chunk_min=15),
         spec("goal", 3, "g", target_min=120, release=at(MON, "09:00"), due=at(MON + 1, "04:00"), min_chunk_min=15),
         spec("side_project", 4, "sp", ceiling_min=60, min_chunk_min=15),
         spec("routine", 5, "lunch", min_min=20, ideal_min=30, max_min=45, release=at(MON, "11:30"), due=at(MON, "14:30"))]
    from fr.core.defaults import REFERENCE_RULES
    p = scn(s, days=2, rule_dicts=[r for r in REFERENCE_RULES if r["name"] != "quota"])
    res = run(p)
    ev = res.evaluation
    for sr in res.stages:
        if sr.status == "OPTIMAL":
            assert sr.cp_objective == sr.true_value
    assert sum(ev.stage_values.values()) == sum(ev.rule_totals.values())


def test_12_dependency_orders_the_work():
    a = spec("assignment", 1, "A", duration_min=60, due=at(MON, "12:00"), min_chunk_min=15)
    b = spec("assignment", 2, "B", duration_min=60, due=at(MON, "12:00"), min_chunk_min=15)
    b.deps = ((1, 1.0, 0),)
    s = [wall(MON, "04:00", "09:50"), wall(MON, "11:20", "23:59"), a, b]  # free: 09:50-11:20, so A then B fit only in that order
    p = scn(s, ["late_work"], days=1, now=at(MON, "09:00"))
    res = run(p)
    assert max(p.grid.end[x] for x in res.plan["item:1"]) <= min(p.grid.start[x] for x in res.plan["item:2"])


def test_13_fraction_and_lag():
    a = spec("assignment", 1, "A", duration_min=120, due=at(MON + 3, "12:00"), min_chunk_min=15)
    b = spec("assignment", 2, "B", duration_min=60, due=at(MON + 3, "12:00"), min_chunk_min=15)
    b.deps = ((1, 0.5, 1440),)
    p = scn([a, b], ["late_work", "finish_early"], [dict(type="finish_early", name="fe", weight=3, params=dict(days=3))],
            days=4)
    res = run(p)
    a_half = sorted(res.plan["item:1"])
    done, t_half = 0, None
    for x in a_half:
        done += int(p.grid.units[x])
        if done >= 4 and t_half is None:
            t_half = int(p.grid.end[x])
    assert min(p.grid.start[x] for x in res.plan["item:2"]) >= t_half + 1440 - 15


def test_14_no_isolated_fifteen_minute_pieces():
    cuts = [spec("commitment", 800 + i, "cut", start=at(MON, f"{h:02d}:15"), end=at(MON, f"{h:02d}:45"), event_kind="shove")
            for i, h in enumerate(range(9, 12))]
    big = wall(MON, "13:00", "23:59")
    a = spec("assignment", 1, "a", duration_min=60, due=at(MON, "13:00"), min_chunk_min=30)
    p = scn([*cuts, big, a], ["late_work"], days=1, now=at(MON, "09:00"))
    res = run(p)
    from fr.core.evaluate import runs
    assert all(int(p.grid.units[x0:x1 + 1].sum()) >= 2 for x0, x1 in runs(res.plan["item:1"]))


def test_15_chunk_cost_keeps_a_three_hour_item_in_one_chunk():
    a = spec("assignment", 1, "a", duration_min=180, due=at(MON + 1, "17:00"), min_chunk_min=15, chunk_cost=0.2)
    p = scn([a], ["late_work", "chunk_cost"], days=2)
    res = run(p)
    assert len(blocks(p, res.plan, "item:1")) == 1


def test_16_deep_run_splits_five_hours_of_deep_work_around_a_class():
    cls = spec("class", 9, "class", start=at(MON, "11:00"), end=at(MON, "12:00"))
    a = spec("assignment", 1, "deep", duration_min=300, due=at(MON, "17:00"), min_chunk_min=15)
    s = [cls, a, wall(MON, "04:00", "07:55")]
    p = scn(s, ["late_work", "deep_run"], days=1, now=at(MON, "08:00"))
    res = run(p)
    assert res.evaluation.rule_totals["deep_run"] == 0
    g = p.grid
    placed = set(res.plan["item:1"])
    for a0 in range(g.S):  # no 3h15 window holds more than 3h of deep work
        u, b = 0, a0
        while b < g.S and u < 13:
            u += int(g.units[b]); b += 1
        if u >= 13:
            assert sum(int(g.units[x]) for x in range(a0, b) if x in placed) <= 12


def test_17_reserve_keeps_two_free_weekday_evening_hours():
    s = [spec("assignment", i, f"a{i}", duration_min=90, due=at(MON + 2, "04:00"), min_chunk_min=15) for i in (1, 2, 3, 4)]
    rule = dict(type="reserve", name="evenings", weight=2, params=dict(days_except=["sat", "sun"], start="18:00", end="23:00", free="2h"))
    p = scn(s, ["late_work"], [rule], days=2)
    res = run(p)
    g = p.grid
    for d in range(2):
        win = [x for x in g.day_slots[d] if 18 * 60 <= g.slots[x].local_minute < 23 * 60]
        busy = sum(int(g.units[x]) for x in win if any(x in res.plan[k] for k in res.plan))
        assert 20 - busy >= 8  # 5 h window, at least 2 h (8 units) free


def test_18_lunch_fits_the_gap_between_classes():
    s = [spec("class", 9, "c1", start=at(MON, "10:00"), end=at(MON, "11:30")),
         spec("class", 10, "c2", start=at(MON, "12:15"), end=at(MON, "14:30")),
         spec("commitment", 11, "c3", start=at(MON, "14:30"), end=at(MON, "23:00")),
         spec("routine", 1, "lunch", min_min=20, ideal_min=30, max_min=45, release=at(MON, "11:30"), due=at(MON, "14:30"))]
    p = scn(s, ["elastic_shortfall"], days=1, now=at(MON, "09:00"))
    res = run(p)
    h = hours(p, res.plan, "item:1")
    assert h >= 20 / 60 and all(at(MON, "11:30") <= a and b <= at(MON, "14:30") for a, b in blocks(p, res.plan, "item:1"))


def test_20_same_snapshot_twice_gives_the_same_plan():
    s = [spec("assignment", i, f"a{i}", duration_min=90, due=at(MON + 1, "17:00"), min_chunk_min=15, chunk_cost=0.1)
         for i in (1, 2, 3)]
    names = ["late_work", "energy", "chunk_cost", "late_night", "daily_load"]
    r1, r2 = run(scn(s, names, days=2)), run(scn(s, names, days=2))
    assert r1.plan == r2.plan and r1.evaluation.stage_values == r2.evaluation.stage_values


def _paces():
    open_item = spec("side_project", 1, "book", ceiling_min=180, min_chunk_min=45)
    hard = [spec("assignment", 10 + i, f"h{i}", duration_min=300, due=at(MON + 3, "12:00"), min_chunk_min=30) for i in range(3)]
    return open_item, hard


NAMES = ["late_work", "late_night", "reserve", "daily_load", "even_load", "open_value", "weekday_evenings", "weekends"]


def _open_hours(p, res):
    return hours(p, res.plan, "item:1")


def test_21_22_23_open_item_follows_the_pace():
    open_item, _ = _paces()
    weekday = [wall(MON, "04:00", "09:00"), wall(MON + 1, "04:00", "09:00")]
    normal = scn([open_item, *weekday], NAMES, days=2, now=at(MON, "09:00"))
    r_normal = run(normal)
    easy = scn([open_item, *weekday], NAMES, days=2, now=at(MON, "09:00"), scales=[EASY, EASY])
    r_easy = run(easy)
    push = scn([open_item, *weekday], NAMES, days=2, now=at(MON, "09:00"), scales=[PUSH, PUSH])
    r_push = run(push)
    ceiling = 12
    assert 0 < _open_hours(normal, r_normal) <= 3 * 2
    assert _open_hours(easy, r_easy) == 0
    assert _open_hours(push, r_push) >= _open_hours(normal, r_normal)
    for p, r in ((normal, r_normal), (push, r_push)):
        for d in range(2):
            assert sum(int(p.grid.units[x]) for x in r.plan["item:1"] if p.grid.slots[x].day == d) <= ceiling
        assert not any(p.core[x] for x in r.plan["item:1"])  # the sleep core is untouched


def test_24_easy_pace_still_meets_deadlines_it_cannot_make_light():
    _, hard = _paces()
    p = scn(hard, NAMES, days=4, now=at(MON, "09:00"), scales=[EASY] * 4)
    res = run(p)
    assert res.evaluation.stage_values["deadlines"] == 0


def _project_scenario():
    from fr.core.generate import Scenario
    proj = spec("project", 1, "thesis", duration_min=30 * 60, due=at(MON + 42, "23:59"))
    return Scenario("proj", [proj], [], at(MON, "09:00"), Settings(workers=4, det_time=(10, 10, 10)))


def test_19_quota_places_about_a_linear_share_this_week_and_next():
    from fr.baseline.allocator import allocate, apply_quotas
    sc = _project_scenario()
    p = sc.build()
    alloc = allocate(sc, p)
    q = alloc.quota["item:1"]
    weeks = sorted(q)
    assert len(weeks) == 2
    for w in weeks:  # linear: 30 h over 6 weeks = 5 h = 20 units a week
        assert 16 <= q[w] <= 24, q
    apply_quotas(p, alloc)
    res = solve(p, workers=4)
    assert check(p, res.plan) == []
    got = {}
    for x in res.plan["item:1"]:
        got[p.grid.slots[x].week] = got.get(p.grid.slots[x].week, 0) + int(p.grid.units[x])
    for w in weeks:
        assert got.get(w, 0) >= q[w] - 2  # the quota rule asks for it in the deadlines stage


def test_19b_the_reference_earliest_tiebreak_front_loads_the_project():
    """Documents a discrepancy in the reference: epsilon-earlier ties plus free surplus pacing front-load work."""
    from fr.baseline.allocator import allocate
    sc = _project_scenario()
    alloc = allocate(sc, sc.build(), tiebreak="earliest")
    first_two_weeks = sum(alloc.quota["item:1"].values())
    assert first_two_weeks > 80  # nearly everything in the first fortnight instead of 40 units
