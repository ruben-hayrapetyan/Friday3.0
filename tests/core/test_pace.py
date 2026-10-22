from datetime import date

import pytest
from pydantic import ValidationError

from friday.core.pace import (
    DEFAULT_PACES,
    DayScales,
    Dials,
    PacePeriod,
    adjust_dials,
    dials_on,
    pace_label,
    scales,
    switch_pace,
)

EASY, NORMAL = DEFAULT_PACES["Easy"], DEFAULT_PACES["Normal"]
MON = date(2026, 10, 19)


def day(n: int) -> date:
    return date.fromordinal(MON.toordinal() + n)


def test_normal_dials_scale_nothing() -> None:
    assert scales(NORMAL) == DayScales()


def test_each_dial_reaches_its_factors() -> None:
    s = scales(Dials(capacity=0.6, rest=2.0, spread=3.0, growth=0.0))
    assert (s.daily_load_threshold, s.deep_run_threshold, s.utilization) == (0.6, 0.6, 0.6)
    assert (s.reserve_free, s.late_night_weight, s.debt_factor) == (2.0, 2.0, 2.0)
    assert s.even_load_weight == 3.0
    assert (s.open_value_slopes, s.target_weight, s.target_amount) == (0.0, 0.0, 0.0)


def test_dials_outside_their_range_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Dials(capacity=2.0)


def test_days_without_a_period_use_the_default_pace() -> None:
    periods = switch_pace([], MON, EASY, "Easy", day(4), "Normal")
    assert dials_on(MON, periods, DEFAULT_PACES, "Normal") == EASY
    assert dials_on(day(4), periods, DEFAULT_PACES, "Normal") == EASY
    assert dials_on(day(5), periods, DEFAULT_PACES, "Normal") == NORMAL


def test_switching_replaces_the_active_period_from_today() -> None:
    periods = switch_pace([], MON, EASY, "Easy", None, "Normal")
    periods = switch_pace(periods, day(2), DEFAULT_PACES["Push"], "Push", None, "Normal")
    assert periods == [
        PacePeriod("Easy", EASY, MON, day(1)),
        PacePeriod("Push", DEFAULT_PACES["Push"], day(2), None),
    ]


def test_switching_to_the_default_pace_ends_the_period() -> None:
    periods = switch_pace([], MON, EASY, "Easy", None, "Normal")
    periods = switch_pace(periods, day(3), NORMAL, "Normal", None, "Normal")
    assert periods == [PacePeriod("Easy", EASY, MON, day(2))]
    assert dials_on(day(3), periods, DEFAULT_PACES, "Normal") == NORMAL


def test_switching_on_the_day_a_period_starts_replaces_it_entirely() -> None:
    periods = switch_pace([], MON, EASY, "Easy", None, "Normal")
    assert switch_pace(periods, MON, NORMAL, "Normal", None, "Normal") == []


def test_direct_dials_change_only_what_you_give() -> None:
    custom = adjust_dials(EASY, growth=0.5)
    assert custom == Dials(capacity=0.6, rest=2.0, spread=3.0, growth=0.5)
    assert pace_label(custom, DEFAULT_PACES) == "Custom"
    assert pace_label(EASY, DEFAULT_PACES) == "Easy"
