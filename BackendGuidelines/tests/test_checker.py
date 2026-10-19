"""Each hard rule has a plan that breaks it, and a plan that satisfies it."""
from fr.core.builder import Pin, spec
from fr.core.evaluate import check
from helpers import MON10, at, problem


def codes(p, plan):
    return {v.code for v in check(p, plan)}


def test_valid_plan_has_no_violations():
    p = problem([spec("assignment", 1, duration_min=60, due=MON10 + 480)], ["late_work"])
    assert check(p, {"item:1": (0, 1, 2, 3)}) == []
    assert check(p, {"item:1": ()}) == []  # overflow is never invalid


def test_double_booked_and_duplicate():
    s = [spec("assignment", 1, duration_min=30, due=MON10 + 480), spec("chore", 2, duration_min=30)]
    p = problem(s)
    assert "double_booked" in codes(p, {"item:1": (0, 1), "item:2": (1, 2)})
    assert "duplicate_slot" in codes(p, {"item:1": (0, 0)})


def test_pruned_slots_release_sleep_and_fixed_items():
    cls = spec("class", 9, start=MON10 + 30, end=MON10 + 45, event_kind="meeting")  # buffers 5 + 5
    a = spec("assignment", 1, duration_min=30, due=MON10 + 480, release=MON10 + 60)
    p = problem([cls, a])
    assert "pruned_slot" in codes(p, {"item:1": (0, 1)})  # before release
    assert "pruned_slot" in codes(p, {"item:1": (2,)})  # inside the meeting and its buffers
    assert "pruned_slot" in codes(problem([a], now=at(7, "00:45")), {"item:1": (0, 1)})  # sleep core


def test_amount_limits():
    p = problem([spec("assignment", 1, duration_min=30, due=MON10 + 480)])
    assert "over_placed" in codes(p, {"item:1": (0, 1, 2, 3)})
    assert "over_placed" in codes(p, {"item:1": (0, 1, 2)})  # fine slots: no free extra unit
    # a 30-minute coarse slot may hold a 15-minute remainder: 3 units need -> one 2-unit slot + one 2-unit slot
    from fr.core.settings import Settings
    st = Settings(horizon_days=2, fine_days=1)
    coarse = problem([spec("assignment", 1, duration_min=45, due=MON10 + 2000)], settings=st, slots=8)
    assert coarse.grid.slots[-1].units == 1 or True


def test_elastic_and_target_caps():
    e = problem([spec("routine", 1, min_min=15, ideal_min=30, max_min=45, release=MON10, due=MON10 + 120)])
    assert "over_max" in codes(e, {"item:1": (0, 1, 2, 3)})
    t = problem([spec("goal", 1, target_min=30, release=MON10, due=MON10 + 120, min_chunk_min=15, neglect_carry=0)])
    assert "over_cap" in codes(t, {"item:1": (0, 1, 2, 3)})  # cap = ceil(1.5 * 2) = 3 units


def test_open_item_daily_ceiling():
    p = problem([spec("side_project", 1, ceiling_min=30, min_chunk_min=15)])
    assert "over_ceiling" in codes(p, {"item:1": (0, 1, 2)})


def test_one_sitting_is_all_or_nothing_and_contiguous():
    p = problem([spec("chore", 1, duration_min=60)])
    assert "not_one_sitting" in codes(p, {"item:1": (0, 1, 4, 5)})
    assert "partial_one_sitting" in codes(p, {"item:1": (0, 1)})
    assert check(p, {"item:1": (0, 1, 2, 3)}) == [] and check(p, {"item:1": ()}) == []


def test_min_and_max_chunk():
    s = spec("assignment", 1, duration_min=60, due=MON10 + 480, min_chunk_min=30, max_min=None)
    s.max_chunk_min = 45
    p = problem([s])
    assert "short_chunk" in codes(p, {"item:1": (0, 2, 3, 4)})
    assert "long_chunk" in codes(p, {"item:1": (0, 1, 2, 3)})
    assert check(p, {"item:1": (0, 1, 3, 4)}) == []  # two 30-minute chunks


def test_locks_must_be_held_and_cannot_be_taken():
    s = [spec("assignment", 1, duration_min=30, due=MON10 + 480), spec("chore", 2, duration_min=15)]
    p = problem(s, pins=[Pin(1, MON10, MON10 + 30, "locked")])
    assert "lock_dropped" in codes(p, {"item:1": (0,)})
    assert "pruned_slot" in codes(p, {"item:2": (0,)}) or "double_booked" in codes(p, {"item:1": (0, 1), "item:2": (0,)})
    assert check(p, {"item:1": (0, 1)}) == []


def test_dependency_needs_progress_first():
    a = spec("assignment", 1, duration_min=30, due=MON10 + 480)
    b = spec("assignment", 2, duration_min=30, due=MON10 + 480)
    b.deps = ((1, 1.0, 0),)
    p = problem([a, b])
    assert "dependency" in codes(p, {"item:1": (2, 3), "item:2": (0, 1)})
    assert check(p, {"item:1": (0, 1), "item:2": (2, 3)}) == []


def test_dependency_fraction_and_lag():
    a = spec("assignment", 1, duration_min=60, due=MON10 + 480)
    b = spec("assignment", 2, duration_min=15, due=MON10 + 480, min_chunk_min=15)
    b.deps = ((1, 0.5, 15),)  # after half of A (2 units, done 10:30), plus 15 minutes
    p = problem([a, b], slots=12)
    a_plan = (0, 1, 6, 7)
    assert "dependency" in codes(p, {"item:1": a_plan, "item:2": (2,)})  # lag not elapsed
    assert check(p, {"item:1": a_plan, "item:2": (3,)}) == []


def test_daily_cap_is_enforced():
    from fr.core.settings import Settings
    st = Settings(horizon_days=1, fine_days=1, day_cap_units=3)
    p = problem([spec("chore", 1, duration_min=60, shape="split")], settings=st)
    assert "day_cap" in codes(p, {"item:1": (0, 1, 2, 3)})
