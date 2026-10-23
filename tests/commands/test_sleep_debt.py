"""Sleep debt (DESIGN §12.3, COMBINED.md 67): work recorded inside the margin after bedtime makes working late dearer
on each of the three nights after it. The test week's weekday bedtime is 23:30 with an hour's margin; the weekend's is
00:30, so Sunday night's margin runs from 00:30 to 01:30 on Monday."""

from datetime import date
from pathlib import Path

import pytest

from friday.planner.build import build_problem
from friday.planner.prepare import build_input, debt_hours
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app

MON, TUE, WED, THU = date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 October, 09:00


def essay(app: App) -> int:
    return app.do("add", text="essay ~6h due fri")["item"]["id"]


def worked(app: App, item_id: int, start: str, end: str) -> None:
    app.do("log", id=item_id, start=start, end=end)


def debt(app: App) -> dict[date, float]:
    return debt_hours(take_snapshot(app.conn, app.now_utc))


def test_nothing_owed_without_late_work(app: App) -> None:
    worked(app, essay(app), "2026-10-18T20:00", "2026-10-18T22:00")  # Sunday evening, before bedtime
    assert debt(app) == {}


def test_an_hour_in_last_nights_margin_is_owed_on_the_next_three_nights(app: App) -> None:
    worked(app, essay(app), "2026-10-19T00:30", "2026-10-19T01:30")
    assert debt(app) == {MON: 1.0, TUE: 1.0, WED: 1.0}


def test_only_the_part_inside_the_margin_counts(app: App) -> None:
    worked(app, essay(app), "2026-10-19T01:00", "2026-10-19T02:30")  # past the margin is the core: not planned, so
    assert debt(app) == {MON: 0.5, TUE: 0.5, WED: 0.5}  # only the half hour in the margin is debt


def test_nights_add_up_and_the_oldest_drop_off(app: App) -> None:
    item = essay(app)
    worked(app, item, "2026-10-18T00:30", "2026-10-18T01:30")  # Saturday night
    worked(app, item, "2026-10-19T00:30", "2026-10-19T01:30")  # Sunday night
    worked(app, item, "2026-10-15T23:30", "2026-10-16T00:30")  # Thursday night: four nights ago, paid off
    assert debt(app) == {MON: 2.0, TUE: 2.0, WED: 1.0}


def test_a_timer_running_past_bedtime_counts_for_the_nights_after(app: App) -> None:
    item = essay(app)
    app.at("2026-10-19T23:00").do("start", id=item)
    app.at("2026-10-19T23:50")
    assert debt(app) == pytest.approx({TUE: 20 / 60, WED: 20 / 60, THU: 20 / 60})


def test_tonights_finished_session_counts_too(app: App) -> None:
    item = essay(app)
    app.at("2026-10-20T00:45")  # still Monday's planning day (the day starts at 04:00)
    worked(app, item, "2026-10-19T23:30", "2026-10-20T00:15")
    assert debt(app) == {TUE: 0.75, WED: 0.75, THU: 0.75}


def test_the_debt_reaches_the_engines_nights(app: App) -> None:
    worked(app, essay(app), "2026-10-19T00:30", "2026-10-19T01:30")
    problem = build_problem(build_input(take_snapshot(app.conn, app.now_utc)))
    assert problem.nights[MON].debt_hours == 1.0
    assert problem.nights[THU].debt_hours == 0.0


def test_a_later_bedtime_moves_the_margin(app: App) -> None:
    app.do("day_override", date="2026-10-18", bedtime="02:00")  # Sunday night, bedtime 02:00
    worked(app, essay(app), "2026-10-19T00:30", "2026-10-19T01:30")  # before that bedtime now
    assert debt(app) == {}
