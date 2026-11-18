"""Nothing that fits is left unplanned when there's time (17 Nov, the user: "friday had tasks but wasn't planning them
even if there was time. this was the core bug"). Assignments, a project's steps and an ongoing project's hours a week,
on a week with time free: in long runs, and in hour-long gaps between events only. Each gets all the time it has left,
before its due, in the plan's days. Before a new sitting could open shorter than its first piece (moves.insert_chunk),
an ongoing project opened only at two hours, and with free time only in shorter gaps it got nothing (Guitar, 3 hours a
week).

Whole system, through the commands and the planner, from Monday 9 Nov 2026 9am with two weeks planned."""

from collections import defaultdict
from pathlib import Path

import pytest

from friday.core.time import parse_local, parse_utc, to_utc
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app

MONDAY = "2026-11-09T09:00"


def planned(app: App) -> dict[int, list[tuple[int, int]]]:
    plan = app.conn.execute("SELECT id FROM plans WHERE status = 'current'").fetchone()[0]
    out: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for item, start, end in app.conn.execute(
        "SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ?", [plan]
    ):
        out[item].append((parse_utc(start), parse_utc(end)))
    return out


def classes_every_other_hour(app: App) -> None:
    """An hour on, an hour off from 9am to 10pm every day, and a late event on weekend nights: free time comes only in
    hour-long gaps, no two-hour run free anywhere in the day."""
    for hour in range(9, 22, 2):
        app.do("add", title=f"Class {hour}", when="fixed", start=f"2026-11-09T{hour:02d}:00",
               end=f"2026-11-09T{hour + 1:02d}:00", every="day")  # fmt: skip
    app.do("add", title="Band", when="fixed", start="2026-11-14T23:00", end="2026-11-15T00:30", every="week")
    app.do("add", title="Band", when="fixed", start="2026-11-15T23:00", end="2026-11-16T00:30", every="week")


def a_few_classes(app: App) -> None:
    """Classes on weekday mornings and a lab on Tuesday and Thursday afternoons: long runs free."""
    app.do("add", title="Lecture", when="fixed", start="2026-11-09T10:00", end="2026-11-09T11:15", every="weekday")
    for day in ("10", "12"):
        app.do("add", title="Lab", when="fixed", start=f"2026-11-{day}T14:00", end=f"2026-11-{day}T16:00",
               every="week")  # fmt: skip


@pytest.mark.parametrize("week", [a_few_classes, classes_every_other_hour], ids=["long runs", "short gaps"])
def test_everything_that_fits_before_its_due_is_planned(tmp_path: Path, week) -> None:
    app = new_app(tmp_path, now=MONDAY, horizon_days=14)
    week(app)
    work = {}  # item → (title, minutes, due)
    for title, minutes, due in [
        ("Problem set 7", 180, "2026-11-12T23:59"),
        ("Reading response", 60, "2026-11-13T17:00"),
        ("Lab report", 150, "2026-11-16T09:00"),
        ("Essay draft", 240, "2026-11-19T23:59"),
    ]:
        made = app.do("add", title=title, preset="Assignment", duration_min=minutes, due=due)["item"]["id"]
        work[made] = (title, minutes, due)
    report = app.do("add", title="Report", preset="Project", due="2026-11-20T17:00")["item"]["id"]
    for title, minutes in [("Research", 120), ("Outline", 60), ("Write", 180)]:
        step = app.do("add", title=title, preset="Assignment", duration_min=minutes, parent_id=report)["item"]["id"]
        work[step] = (title, minutes, "2026-11-20T17:00")
    series = app.do("ongoing_add", title="Guitar", hours_per_week=3)["id"]
    replan(app.conn, app.now_utc)

    found = planned(app)
    for item, (title, minutes, due) in work.items():
        got = sum(end - start for start, end in found.get(item, []))
        assert got >= minutes, (title, got, minutes)
        assert max(end for _, end in found[item]) <= to_utc(parse_local(due), TZ)
    guitar_weeks = app.conn.execute(
        "SELECT id, occurrence_date FROM items WHERE series_id = ? ORDER BY occurrence_date", [series]
    ).fetchall()
    for week_item, starts in guitar_weeks[:2]:  # this week's 3 hours, and next week's
        got = sum(end - start for start, end in found.get(week_item, []))
        assert got >= 180, (starts, got)
    assert app.do("changes")["late_hours"] == {}
