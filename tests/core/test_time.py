from datetime import date, datetime

import pytest

from friday.core.time import (
    GridSpec,
    format_utc,
    make_grid,
    night_utc,
    parse_utc,
    planning_date,
    to_local,
    to_utc,
    wake_utc,
)

UTC_SPEC = GridSpec(timezone="UTC")


def utc(text: str, tz: str = "UTC") -> int:
    return to_utc(datetime.fromisoformat(text), tz)


def day_slots(grid, day: int) -> list:
    return [s for s in grid.slots if s.day == day]


def test_grid_has_fine_and_coarse_zones_and_no_gaps() -> None:
    grid = make_grid(utc("2026-10-19T09:07"), UTC_SPEC)  # a Monday; rounds up to 09:15
    assert grid.slots[0].start_utc == utc("2026-10-19T09:15")
    assert grid.n_days == 14
    assert all(a.end_utc == b.start_utc for a, b in zip(grid.slots, grid.slots[1:], strict=False))
    assert all(s.units == 1 for s in grid.slots if s.day < 7)
    assert all(s.units == 2 for s in grid.slots if s.day >= 7)
    assert len(day_slots(grid, 1)) == 96
    assert len(day_slots(grid, 8)) == 48
    assert grid.slots[-1].end_utc == grid.horizon_end


def test_one_in_the_morning_belongs_to_the_night_before() -> None:
    grid = make_grid(utc("2026-10-19T01:00"), UTC_SPEC)
    first = grid.slots[0]
    assert first.date == date(2026, 10, 18) and first.weekday == 6 and first.day == 0
    assert first.day_minute == 25 * 60
    assert first.local_minute == 60
    tomorrow = day_slots(grid, 1)[0]
    assert tomorrow.start_utc == utc("2026-10-19T04:00") and tomorrow.weekday == 0


def test_week_index_changes_at_the_week_start() -> None:
    grid = make_grid(utc("2026-10-19T09:00"), UTC_SPEC)
    assert len({s.week for s in grid.slots}) == 2
    second_week = max(s.week for s in grid.slots)
    assert min(s.start_utc for s in grid.slots if s.week == second_week) == utc("2026-10-26T04:00")


def test_truncated_grid_stops_at_the_end() -> None:
    grid = make_grid(utc("2026-10-19T02:00"), UTC_SPEC, end_utc=utc("2026-10-19T04:00"))
    assert grid.S == 8 and grid.horizon_end == utc("2026-10-19T04:00")


def test_spring_forward_day_has_four_fewer_fine_slots() -> None:
    tz = "America/New_York"
    grid = make_grid(utc("2026-03-05T09:00", tz), GridSpec(timezone=tz))
    saturday = day_slots(grid, 2)  # Sat Mar 7 04:00 to Sun Mar 8 04:00 contains the 02:00 change
    assert saturday[0].date == date(2026, 3, 7)
    assert len(saturday) == 92
    before, after = [s for s in saturday if s.local_minute in (105, 180)]
    assert before.end_utc == after.start_utc  # 01:45 EST is followed by 03:00 EDT
    assert after.day_minute == 1440 + 180
    assert to_local(after.start_utc, tz) == datetime(2026, 3, 8, 3, 0)


def test_fall_back_day_has_four_more_coarse_slots() -> None:
    tz = "America/New_York"
    grid = make_grid(utc("2026-10-22T09:00", tz), GridSpec(timezone=tz))
    saturday = day_slots(grid, 9)  # Sat Oct 31, in the 30-minute zone
    assert saturday[0].date == date(2026, 10, 31)
    assert len(saturday) == 50
    assert all(s.units == 2 for s in saturday)
    one_thirty = [s for s in saturday if s.local_minute == 90]
    assert len(one_thirty) == 2 and one_thirty[1].start_utc - one_thirty[0].start_utc == 60


def test_london_spring_forward_in_the_fine_zone() -> None:
    tz = "Europe/London"
    grid = make_grid(utc("2026-03-27T12:00", tz), GridSpec(timezone=tz))
    saturday = day_slots(grid, 1)
    assert saturday[0].date == date(2026, 3, 28) and len(saturday) == 92


def test_zone_boundary_falls_at_day_start() -> None:
    grid = make_grid(utc("2026-10-19T09:00"), UTC_SPEC)
    first_coarse = next(s for s in grid.slots if s.units == 2)
    assert first_coarse.start_utc == utc("2026-10-26T04:00")


def test_timezone_with_an_odd_offset_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        make_grid(utc("1971-06-01T12:00"), GridSpec(timezone="Africa/Monrovia"))  # UTC−00:44:30 then


def test_local_time_inside_a_gap_moves_forward() -> None:
    tz = "America/New_York"
    assert to_local(to_utc(datetime(2026, 3, 8, 2, 30), tz), tz) == datetime(2026, 3, 8, 3, 30)


def test_ambiguous_local_time_takes_the_first_occurrence() -> None:
    tz = "America/New_York"
    assert format_utc(to_utc(datetime(2026, 11, 1, 1, 30), tz)) == "2026-11-01T05:30Z"


def test_planning_date_starts_at_day_start() -> None:
    assert planning_date(utc("2026-10-19T03:59"), "UTC", 240) == date(2026, 10, 18)
    assert planning_date(utc("2026-10-19T04:00"), "UTC", 240) == date(2026, 10, 19)


def test_night_and_wake_of_a_planning_date() -> None:
    tz = "Europe/London"
    night = date(2026, 3, 28)
    assert night_utc(night, 24 * 60 + 30, tz) == utc("2026-03-29T00:30", tz)
    assert wake_utc(night, 8 * 60, tz) == utc("2026-03-29T08:00", tz)
    assert wake_utc(night, 8 * 60, tz) - night_utc(night, 24 * 60 + 30, tz) == 6.5 * 60


def test_stored_times_round_trip() -> None:
    assert format_utc(parse_utc("2026-10-18T09:05Z")) == "2026-10-18T09:05Z"
    with pytest.raises(ValueError):
        parse_utc("2026-10-18T09:05")
