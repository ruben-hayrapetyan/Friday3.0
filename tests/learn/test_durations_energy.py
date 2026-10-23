"""Learned durations and the learned energy map (DESIGN §21.7) on data where the answer is known."""

import numpy as np

from friday.learn.durations import Done, abs_log_error, fit
from friday.learn.energy import Seen, prices


def history(rng: np.random.Generator) -> list[Done]:
    """CS work runs 3 h, essays 2 h; problem sets in CS run long (4 h), seen 20 times; one rare kind seen twice."""
    out = []
    for _ in range(20):
        out.append(Done(float(np.exp(rng.normal(np.log(240), 0.45))), "CS", "Assignment", "problem set"))
    for _ in range(15):
        out.append(Done(float(np.exp(rng.normal(np.log(180), 0.45))), "CS", "Reading", "chapter"))
    for _ in range(15):
        out.append(Done(float(np.exp(rng.normal(np.log(120), 0.45))), "Writing", "Assignment", "essay"))
    out += [Done(30.0, "CS", "Assignment", "quiz review"), Done(30.0, "CS", "Assignment", "quiz review")]
    return out


def test_a_kind_seen_often_stands_on_its_own_and_one_seen_twice_is_pulled_toward_the_rest() -> None:
    model = fit(history(np.random.default_rng(1)))
    assert abs(model.minutes("CS", "Assignment", "problem set", cautious=False) - 240) < 50
    rare = model.minutes("CS", "Assignment", "quiz review", cautious=False)
    assert 30 < rare < 120  # above its two 30-minute samples; how far depends on how much kinds differ


def test_cautious_estimates_are_longer_and_unknown_kinds_fall_back_to_area_and_preset() -> None:
    model = fit(history(np.random.default_rng(2)))
    assert model.minutes("CS", "Reading", "chapter", True) > model.minutes("CS", "Reading", "chapter", False)
    new_kind = model.minutes("Writing", "Assignment", "poem", cautious=False)
    assert 60 < new_kind < 240


def test_it_predicts_better_than_one_median_for_everything() -> None:
    rng = np.random.default_rng(3)
    seen, unseen = history(rng), history(rng)
    model = fit(seen)
    median = float(np.median([d.minutes for d in seen]))
    learned = [model.minutes(d.area, d.preset, d.kind, False) for d in unseen]
    actual = [d.minutes for d in unseen]
    assert abs_log_error(learned, actual) < abs_log_error([median] * len(unseen), actual)


def test_hours_where_work_keeps_slipping_get_a_price_and_unseen_ones_none() -> None:
    seen = [Seen(0, 30, happened=False, speed=None) for _ in range(6)]  # Monday 15:00: skipped every time
    seen += [Seen(1, 18, happened=True, speed=1.0) for _ in range(6)]  # Tuesday 09:00: always happens on time
    seen += [Seen(2, 20, happened=False, speed=None) for _ in range(2)]  # Wednesday: too little to judge
    seen += [Seen(d, c, happened=True, speed=1.0) for d in range(3, 7) for c in range(20, 30)]  # most work happens
    grid = prices(seen)
    assert grid[0][30] > 1 and grid[1][18] == 0 and grid[2][20] == 0 and grid[4][10] == 0


def test_work_that_slips_everywhere_alike_prices_no_hour() -> None:
    rng = np.random.default_rng(5)
    seen = [Seen(d, c, bool(rng.random() > 0.3), None) for d in range(7) for c in range(16, 40) for _ in range(6)]
    assert max(max(row) for row in prices(seen)) < 1
