from fr.core.grid import make_grid
from fr.core.settings import Settings
from conftest import at


def test_grid_zones_and_contiguity():
    st = Settings()
    g = make_grid(at(7, "09:07"), st)  # a Monday, rounds up to 09:15
    assert g.slots[0].start == at(7, "09:15")
    assert g.n_days == 14
    for a, b in zip(g.slots, g.slots[1:]):
        assert a.end == b.start
    # fine days: 15-minute slots; coarse days: 30-minute slots
    assert all(s.units == 1 for s in g.slots if s.day < 7)
    assert all(s.units == 2 for s in g.slots if s.day >= 7)
    assert sum(1 for s in g.slots if s.day == 1) == 96
    assert sum(1 for s in g.slots if s.day == 8) == 48
    assert g.slots[-1].end == g.horizon_end


def test_planning_day_and_weekday():
    st = Settings()
    g = make_grid(at(7, "01:00"), st)  # 01:00 Monday belongs to Sunday's planning day
    assert g.slots[0].date == 6 and g.slots[0].weekday == 6 and g.slots[0].day == 0
    assert g.slots[0].day_minute == 25 * 60
    assert g.slots[0].local_minute == 60
    nxt = [s for s in g.slots if s.day == 1][0]
    assert nxt.start == at(7, "04:00") and nxt.weekday == 0


def test_week_index_changes_on_week_start():
    st = Settings()
    g = make_grid(at(7, "09:00"), st)
    weeks = {s.week for s in g.slots}
    assert weeks == {1, 2}
    first_week2 = min(s.start for s in g.slots if s.week == 2)
    assert first_week2 == at(14, "04:00")


def test_truncated_grid():
    st = Settings()
    g = make_grid(at(7, "02:00"), st, end=at(7, "04:00"))
    assert g.S == 8 and g.horizon_end == at(7, "04:00")
