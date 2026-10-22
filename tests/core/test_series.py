from datetime import date

from friday.core.recurrence import ending_before
from friday.core.series import Series, materialize
from friday.core.time import parse_utc, to_local

TZ = "America/New_York"
MON = date(2026, 10, 19)


def series(**changes: object) -> Series:
    base = dict(
        id=7,
        template={"title": "Shower", "when": "window", "amount": "fixed", "duration_units": 1},
        rrule="FREQ=DAILY",
        dtstart_local="2026-10-19T04:00",
        created_utc="2026-10-19T08:00Z",
    )
    return Series(**base | changes)  # type: ignore[arg-type]


def local(text: str | None) -> str:
    assert text is not None
    return to_local(parse_utc(text), TZ).strftime("%a %H:%M")


def test_daily_series_makes_one_item_per_day_for_that_day() -> None:
    made = materialize(series(), MON, 7, TZ, set())
    assert len(made) == 7
    assert [m.occurrence_date for m in made][:2] == ["2026-10-19", "2026-10-20"]
    assert (local(made[0].release_utc), local(made[0].due_utc)) == ("Mon 04:00", "Tue 04:00")
    assert all(m.title == "Shower" and m.series_id == 7 for m in made)


def test_three_times_a_week_shares_the_weeks_window() -> None:
    made = materialize(series(rrule="FREQ=WEEKLY", per_window=3), MON, 14, TZ, set())
    assert [m.occurrence_n for m in made] == [1, 2, 3, 1, 2, 3]
    assert len({(m.release_utc, m.due_utc) for m in made[:3]}) == 1
    assert local(made[0].due_utc) == "Mon 04:00"


def test_existing_occurrences_are_never_regenerated() -> None:
    existing = {("2026-10-20", 1)}  # e.g. detached after an edit
    made = materialize(series(), MON, 3, TZ, existing)
    assert [m.occurrence_date for m in made] == ["2026-10-19", "2026-10-21"]


def test_no_backfilling_before_the_series_was_created() -> None:
    made = materialize(series(created_utc="2026-10-21T12:00Z"), MON, 4, TZ, set())
    assert [m.occurrence_date for m in made] == ["2026-10-21", "2026-10-22"]


def test_a_weekly_window_opened_before_today_still_comes_in() -> None:
    problem_set = series(rrule="FREQ=WEEKLY", dtstart_local="2026-10-20T04:00", created_utc="2026-10-21T12:00Z")
    made = materialize(problem_set, date(2026, 10, 21), 14, TZ, set())
    assert [(m.occurrence_date, local(m.due_utc)) for m in made] == [
        ("2026-10-20", "Tue 04:00"),
        ("2026-10-27", "Tue 04:00"),
        ("2026-11-03", "Tue 04:00"),
    ]


def test_yesterdays_daily_window_has_closed() -> None:
    made = materialize(series(), date(2026, 10, 21), 1, TZ, set())
    assert [m.occurrence_date for m in made] == ["2026-10-21"]


def test_offsets_set_the_window() -> None:
    lunch = series(dtstart_local="2026-10-19T00:00", release_offset_min=11 * 60 + 30, due_offset_min=14 * 60 + 30)
    made = materialize(lunch, MON, 1, TZ, set())
    assert (local(made[0].release_utc), local(made[0].due_utc)) == ("Mon 11:30", "Mon 14:30")


def test_fixed_series_keeps_its_local_time_across_dst() -> None:
    lecture = series(
        template={"title": "CS 1110", "when": "fixed", "length_min": 75, "event_kind": "class"},
        rrule="FREQ=WEEKLY;BYDAY=MO",
        dtstart_local="2026-10-26T10:10",
    )
    made = materialize(lecture, MON, 22, TZ, set())
    assert [local(m.start_utc) for m in made] == ["Mon 10:10"] * 3
    assert [local(m.end_utc) for m in made] == ["Mon 11:25"] * 3
    assert parse_utc(made[1].start_utc) - parse_utc(made[0].start_utc) == 7 * 1440 + 60  # Nov 1 fall back


def test_editing_from_a_date_splits_the_series_without_overlap() -> None:
    old = series(rrule=ending_before("FREQ=DAILY", date(2026, 10, 22)))
    new = series(
        id=8,
        dtstart_local="2026-10-22T04:00",
        template={"title": "Bath", "when": "window", "amount": "fixed", "duration_units": 2},
    )
    dates = [m.occurrence_date for m in materialize(old, MON, 7, TZ, set())]
    assert dates == ["2026-10-19", "2026-10-20", "2026-10-21"]
    assert materialize(new, MON, 7, TZ, set())[0].occurrence_date == "2026-10-22"
    assert local(materialize(old, MON, 7, TZ, set())[-1].due_utc) == "Thu 04:00"


def test_a_stopped_series_makes_nothing() -> None:
    assert materialize(series(active=False), MON, 7, TZ, set()) == []
