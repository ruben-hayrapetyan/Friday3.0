"""A one-sitting task whose length is an odd quarter hour, where only half-hour slots are (past the plan's first
week), can be put back once taken off: it fills a slot a unit over, as the start plan places it and the walls allow.
17 Nov: a 45-minute errand taken off week two by the search was never put back, and was left unplanned."""

import numpy as np

from friday.engine.compile import compile_problem
from friday.engine.kernel import init_state, item_violations, new_state, seed_rng
from friday.engine.moves import insert_chunk
from tests.engine.helpers import at, item, zone_problem


def test_an_odd_quarter_hour_in_half_hour_slots_can_be_inserted() -> None:
    # Tuesday from 04:00 is 30-minute slots; the errand may only go there
    errand = item("errand", 1, duration_units=3, release_utc=at(1, "04:00"), due_utc=at(1, "12:00"))
    c = compile_problem(zone_problem([errand], ["late_work"]))
    assert all(int(c.m.units[s]) == 2 for s in np.flatnonzero(c.m.allowed[0, : c.m.S]))
    st = new_state(c.m)
    init_state(c.m, st, np.full(c.m.S, -1, dtype=np.int16))
    seed_rng(0)
    touched = np.zeros(4, dtype=np.int64)
    for _ in range(50):
        if insert_chunk(c.m, st, np.zeros(c.m.I, dtype=bool), touched):
            break
    assert st.placed[0] == 4  # two half-hour slots
    assert item_violations(c.m, st, 0) == 0
