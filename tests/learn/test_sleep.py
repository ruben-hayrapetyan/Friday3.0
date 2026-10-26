"""Learning from tracked sleep: which night a tap belongs to, what a night says, and the times and routine learned."""

from datetime import date, datetime, timedelta

from friday.learn.sleep import Change, Mark, Night, changes, learn, nights_from, shortfall_hours

DAY_START = 4 * 60


def mark(kind: str, at: str, n: list[int] = [0]) -> Mark:  # noqa: B006  (a counter for ids)
    n[0] += 1
    return Mark(n[0], kind, datetime.fromisoformat(at))


def test_a_bedtime_after_midnight_is_the_night_before() -> None:
    nights = nights_from([mark("bed", "2026-10-20T01:10"), mark("up", "2026-10-20T08:40")], [], DAY_START)
    (night,) = nights.values()
    assert night.date == date(2026, 10, 19) and night.slept_min == 7 * 60 + 30


def test_ready_is_the_tap_else_the_first_timer_after_waking() -> None:
    up = mark("up", "2026-10-20T08:00")
    timed = nights_from([up], [datetime(2026, 10, 20, 7, 0), datetime(2026, 10, 20, 9, 15)], DAY_START)
    assert timed[date(2026, 10, 19)].routine_min == 75  # the 7am timer was before waking: not this morning's
    tapped = nights_from([up, mark("ready", "2026-10-20T08:45")], [datetime(2026, 10, 20, 9, 15)], DAY_START)
    assert tapped[date(2026, 10, 19)].routine_min == 45


def test_done_with_work_is_the_tap_else_the_last_timer_stopped_before_bed() -> None:
    bed = mark("bed", "2026-10-20T00:30")
    ends = [datetime(2026, 10, 19, 18, 0), datetime(2026, 10, 19, 22, 45)]
    timed = nights_from([bed], [], DAY_START, ends)[date(2026, 10, 19)]
    assert (timed.done_from_timer, timed.wind_down_min) == (datetime(2026, 10, 19, 22, 45), 105)
    long_before = nights_from([bed], [], DAY_START, [datetime(2026, 10, 19, 18, 0)])[date(2026, 10, 19)]
    assert long_before.wind_down_min is None  # six hours before bed: not the end of the evening's work
    tapped = nights_from([mark("done", "2026-10-19T23:30"), bed], [], DAY_START, ends)[date(2026, 10, 19)]
    assert (tapped.done_from_timer, tapped.wind_down_min) == (None, 60)


def test_the_wind_down_is_learned_by_the_evenings_group() -> None:
    marks = []
    for n in range(5):  # Sunday to Thursday nights: done at 10:30pm, bed at 11:30pm
        evening = date(2026, 10, 18) + timedelta(days=n)
        marks += [mark("done", f"{evening}T22:30"), mark("bed", f"{evening}T23:30")]
    learned = learn(nights_from(marks, [], DAY_START).values(), least=4)
    assert learned.wind_down_min == {d: 60 for d in ("sun", "mon", "tue", "wed", "thu")}


def week(start: date, bed: str, up: str, ready: str | None = None, days: int = 7) -> list[Mark]:
    out = []
    for n in range(days):
        evening = start + timedelta(days=n)
        morning = evening + timedelta(days=1)
        bed_day = morning if bed < "12:00" else evening
        out += [mark("bed", f"{bed_day}T{bed}"), mark("up", f"{morning}T{up}")]
        if ready:
            out.append(mark("ready", f"{morning}T{ready}"))
    return out


def test_bedtimes_and_wake_times_are_learned_by_weekday_with_their_group_to_fall_back_on() -> None:
    marks = week(date(2026, 10, 18), "00:40", "08:10", "08:55")  # Sunday night to Saturday night
    learned = learn(nights_from(marks, [], DAY_START).values(), least=4)
    assert learned.bedtime["mon"] == "00:45" and learned.wake["tue"] == "08:15"  # to the quarter hour
    assert learned.routine_min["wed"] == 45 and learned.nights == 7
    # Two Friday and Saturday nights: under the four a weekend group needs, so nothing learned for them
    assert "fri" not in learned.bedtime and "sat" not in learned.wake


def test_learned_times_half_an_hour_off_are_offered_grouped() -> None:
    learned = learn(nights_from(week(date(2026, 10, 18), "00:40", "07:05"), [], DAY_START).values(), least=4)
    sleep = {d: {"bedtime": "23:30", "wake": "07:00"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    found = changes(learned, sleep)
    assert found == [Change(("mon", "tue", "wed", "thu", "sun"), "bedtime", "23:30", "00:45")]  # wake is 5 min off


def test_a_short_night_owes_what_it_fell_short_by() -> None:
    night = Night(date(2026, 10, 19), mark("bed", "2026-10-20T02:00"), mark("up", "2026-10-20T07:00"))
    assert shortfall_hours(night, 8 * 60) == 3.0
    assert shortfall_hours(Night(date(2026, 10, 19)), 8 * 60) == 0.0
