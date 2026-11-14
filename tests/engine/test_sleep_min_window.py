"""The 7 hours are asleep, from sleep to waking (29 Oct: "don't count wind down inside [the] hours, it should be from
sleep to wakeup"): the evening's learned wind-down comes before them, so work ends that much earlier."""

from friday.engine.rules.prices import SleepMin
from tests.engine.helpers import at, item, problem

SEVEN = [{"type": "sleep_min", "name": "seven", "params": {"hours": 7.0}}]  # weekdays: bed 23:30, up 07:30


def kept_between(wind: dict[str, int], start: str, end: str) -> list[bool]:
    """Whether each slot from Monday night's `start` to `end` (after midnight) is kept for sleep."""
    p = problem([item("chore", 1, duration_units=4)], extra=SEVEN, now=at(0, "22:00"), slots=None, days=2,
                wind_down_min=wind)  # fmt: skip
    rule = next(r for r in p.rules if isinstance(r, SleepMin))
    lo, hi = at(1, start), at(1, end)
    return [bool(rule.kept[s]) for s in range(p.grid.S) if lo <= p.grid.start[s] < hi]


def test_without_a_wind_down_the_seven_hours_start_seven_before_waking() -> None:
    assert kept_between({}, "00:00", "00:30") == [False, False]  # 00:30–07:30 is the seven hours


def test_a_learned_wind_down_comes_before_the_seven_hours() -> None:
    assert kept_between({"mon": 30}, "00:00", "00:30") == [True, True]  # winding down 00:00–00:30, asleep by 00:30
    assert kept_between({"mon": 15}, "00:00", "00:30") == [False, True]
    assert kept_between({"tue": 30}, "00:00", "00:30") == [False, False]  # Tuesday evening's, not Monday's


# The sleep a night loses runs from asleep-by to the end of its last work there, empty time between included (14 Nov:
# a half hour at 1:45am after work that ended at midnight cost what it would have right after it). 8.5 hours before a
# 7:30 wake is 11pm; bedtime's margin (an hour) is the wall from 00:30.
LONG = [{"type": "sleep_min", "name": "long", "params": {"hours": 8.5, "price": 40.0}}]
HOUR = 40 * 100  # 40 points an hour, at the scale of 100


def night(more=()):  # noqa: ANN001, ANN201
    """Monday from 22:00 to 00:30, a problem set and a reading due Tuesday."""
    problem_set = item("assignment", 1, duration_units=2, due_utc=at(1, "09:00"))
    reading = item("reading", 2, duration_units=2, due_utc=at(1, "09:00"))
    return problem([problem_set, reading, *more], extra=LONG, now=at(0, "22:00"), slots=10)


def lost(p, **placed) -> int:  # noqa: ANN001
    from friday.engine.evaluate import evaluate  # noqa: PLC0415
    from tests.engine.helpers import plan  # noqa: PLC0415

    return evaluate(p, plan(**placed)).rule_totals["long"]


def test_work_straight_on_into_the_kept_hours_costs_the_hours_it_takes() -> None:
    p = night()  # slot 4 is 23:00
    assert lost(p, item_1=(2, 3), item_2=(4, 5)) == HOUR // 2  # 22:30–23:30: half an hour past 11pm
    assert lost(p, item_1=(4, 5), item_2=(6, 7)) == HOUR  # 23:00–00:00


def test_a_gap_in_the_kept_hours_is_sleep_lost_as_well() -> None:
    p = night()
    assert lost(p, item_1=(4, 5), item_2=(7, 8)) == 5 * HOUR // 4  # 23:00–23:30, then 23:45–00:15: awake to 00:15
    assert lost(p, item_1=(4, 5), item_2=(8, 9)) == 3 * HOUR // 2


def test_work_that_starts_late_in_the_kept_hours_loses_the_sleep_before_it() -> None:
    p = night()
    assert lost(p, item_1=(0, 1), item_2=(8, 9)) == 3 * HOUR // 2  # 00:00–00:30: not asleep from 11pm


def test_an_event_s_own_time_in_the_kept_hours_isn_t_work_s_to_pay_for() -> None:
    call = item("commitment", 3, title="Call", when="fixed", start_utc=at(0, "23:00"), end_utc=at(0, "23:30"))
    p = night([call])
    taken = sum(1 for s in range(4, 10) if p.blocked[s])
    assert taken >= 2  # the call's half hour, and its gap if it has one
    assert lost(p, item_1=(0, 1), item_2=(8, 9)) == (6 - taken) * HOUR // 4


def test_nothing_in_the_kept_hours_costs_nothing() -> None:
    assert lost(night(), item_1=(0, 1), item_2=(2, 3)) == 0
