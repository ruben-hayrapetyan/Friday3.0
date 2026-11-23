"""Insights: estimates against actual time by kind, and when work gets done."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_insights_compare_estimates_by_kind_and_map_working_hours(app: App) -> None:
    for title, worked in (("PS1", ("09:00", "11:00")), ("PS2", ("09:00", "10:00"))):
        item = app.do("add", title=title, preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
        app.at("2026-10-19T12:00").do("log", id=item, start=f"2026-10-19T{worked[0]}", end=f"2026-10-19T{worked[1]}")
        app.do("done", id=item)
    out = app.do("insights", weeks=4)
    (kind,) = out["by_kind"]
    assert (kind["kind"], kind["n"], kind["low"], kind["high"]) == ("Assignment", 2, 1.0, 2.0)
    assert out["heat"][0][1] == 60 and out["heat"][0][2] == 60  # Monday 09:00 (two at once: one hour) and 10:00
    assert out["best_hours"] == "You get the most done on Mondays, 9am to 11am."


def test_a_projects_steps_keep_the_order_you_give_them(app: App) -> None:
    project = app.do("template_apply", template="Essay", title="History essay", hours=6)["item"]["id"]
    steps = [c["id"] for c in app.do("projects")[0]["children"]]
    app.do("reorder", parent_id=project, ids=list(reversed(steps)))
    assert [c["id"] for c in app.do("projects")[0]["children"]] == list(reversed(steps))


def test_under_two_hours_of_work_says_no_best_hours_yet(app: App) -> None:
    item = app.do("add", title="PS1", preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
    app.at("2026-10-19T12:00").do("log", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00")
    app.do("done", id=item)
    out = app.do("insights", weeks=4)
    assert out["heat"][0][1] == 60 and out["best_hours"] is None


# 16 Nov ("why does it say 357 min on my insights"): three timers running at once made one hour three, and the map's
# cells add up the weeks shown


def assignment(app: App, title: str) -> int:
    return app.do("add", title=title, preset="Assignment", duration_min=60, due="2026-10-30T17:00")["item"]["id"]


def test_work_timed_at_once_on_several_things_fills_an_hour_once(app: App) -> None:
    for title in ("PS1", "PS2", "Errand run"):
        item = assignment(app, title)
        app.at("2026-10-19T12:00").do("log", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00")
    assert app.do("insights", weeks=4)["heat"][0][1] == 60


def test_a_session_counts_the_minutes_it_recorded_not_its_span(app: App) -> None:
    item = assignment(app, "PS1")
    app.conn.execute(
        "INSERT INTO progress (user_id, item_id, start_utc, end_utc, minutes, source, created_utc) "
        "VALUES (1, ?, '2026-10-19T13:00Z', '2026-10-19T14:00Z', 30, 'review', '2026-10-19T15:00Z')",
        [item],
    )  # a review's "30 minutes" between 9am and 10am, New York time
    assert app.do("insights", weeks=4)["heat"][0][1] == 30


def test_the_same_hour_in_different_weeks_adds_up(app: App) -> None:
    item = assignment(app, "PS1")
    app.at("2026-10-26T12:00")
    for monday in ("2026-10-19", "2026-10-26"):
        app.do("log", id=item, start=f"{monday}T09:00", end=f"{monday}T09:45")
    assert app.do("insights", weeks=4)["heat"][0][1] == 90


def test_hours_worked_before_8am_or_past_midnight_show_on_the_evening_they_belong_to(app: App) -> None:
    """20 Nov, a user's notes: "if your work typically starts before 8 or ends after midnight I feel like it should show
    up" (only 8am to 11pm did). Monday 6am and Monday night's 11:30pm to 1:30am (Tuesday 1am, before the day's 4am
    start, is Monday night's)."""
    item = app.do("add", title="Essay", preset="Assignment", duration_min=240, due="2026-10-23T17:00")["item"]["id"]
    app.at("2026-10-20T12:00").do("log", id=item, start="2026-10-19T06:00", end="2026-10-19T07:00")
    app.do("log", id=item, start="2026-10-19T23:30", end="2026-10-20T01:30")
    out = app.do("insights", weeks=4)
    hours = out["heat_hours"]
    assert hours == [6, 7, *range(8, 24), 0, 1]  # 6am first, past midnight last
    monday = dict(zip(hours, out["heat"][0], strict=True))
    assert (monday[6], monday[23], monday[0], monday[1]) == (60, 30, 60, 30)
    assert sum(out["heat"][1]) == 0  # nothing on Tuesday's row


def test_without_early_or_late_work_the_hours_are_8am_to_11pm(app: App) -> None:
    item = app.do("add", title="PS1", preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
    app.at("2026-10-19T12:00").do("log", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00")
    out = app.do("insights", weeks=4)
    assert out["heat_hours"] == list(range(8, 24)) and all(len(row) == 16 for row in out["heat"])


# 22 Nov: "31 things finished" over rows made of 14: "it is very unclear where the discrepancy is between the two".
# Insights says how many of the finished things were timed (the rows are only those).
def test_it_counts_how_many_finished_things_were_timed(app: App) -> None:
    timed = app.do("add", title="PS1", preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
    app.at("2026-10-19T12:00").do("log", id=timed, start="2026-10-19T09:00", end="2026-10-19T10:00")
    app.do("done", id=timed)
    ticked = app.do("add", title="PS2", preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
    app.do("done", id=ticked)  # checked off without a time
    out = app.do("insights", weeks=4)
    assert (out["done"], out["timed"]) == (2, 1)
