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
