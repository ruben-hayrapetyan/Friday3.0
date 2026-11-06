"""Inside the timer's say over planned time (planner/timed.py) and the Review's joined spans: which sittings cover a
block, how much of it, and what counts."""

from friday.commands.progress import joined
from friday.planner.timed import OTHER, OWN, covered_minutes, timed_over, with_running

ESSAY, EMAIL, LAUNDRY = 1, 2, 3


def test_a_sitting_of_the_blocks_own_task_over_any_of_it_replaces_it() -> None:
    assert timed_over(ESSAY, 540, 600, [(ESSAY, 590, 700)]) == OWN


def test_other_things_timed_over_half_or_more_of_it_mean_it_wasnt_done() -> None:
    assert timed_over(EMAIL, 600, 660, [(ESSAY, 600, 630)]) == OTHER
    assert timed_over(EMAIL, 600, 660, [(ESSAY, 600, 629)]) is None


def test_two_things_timed_at_once_cover_each_minute_once() -> None:
    assert covered_minutes(600, 660, [(600, 620), (610, 625), (650, 700)]) == 35
    assert timed_over(EMAIL, 600, 660, [(ESSAY, 600, 620), (LAUNDRY, 610, 625)]) is None


def test_something_that_runs_by_itself_covers_nothing_and_isnt_covered() -> None:
    assert timed_over(EMAIL, 600, 660, [(LAUNDRY, 600, 660)], background={LAUNDRY}) is None
    assert timed_over(LAUNDRY, 600, 615, [(ESSAY, 590, 700)], background={LAUNDRY}) is None
    assert timed_over(LAUNDRY, 600, 615, [(LAUNDRY, 600, 605)], background={LAUNDRY}) == OWN


def test_a_running_timer_is_a_sitting_so_far() -> None:
    assert with_running([(ESSAY, 0, 30)], [(EMAIL, 60), (ESSAY, 200)], 120) == [(ESSAY, 0, 30), (EMAIL, 60, 120)]


def test_touching_pieces_a_replan_cut_read_as_one_span() -> None:
    pieces = [{"start": s, "end": s + 15} for s in (570, 540, 555, 600)]
    assert joined(pieces) == [(540, 585), (600, 615)]
