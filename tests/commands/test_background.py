"""Tasks that run by themselves (a task's "Runs by itself" switch): laundry, a long simulation, a download. The plan
holds only the first quarter hour, early enough to finish by the due, plans other work on top of the rest, and draws
the whole run on the calendar; once started, nothing more is planned for it."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    return new_app(tmp_path)


def afternoon_only(app: App) -> None:
    """Only 2 to 5pm is free today; tomorrow is free again."""
    for start, end in (("2026-10-19T09:00", "2026-10-19T14:00"), ("2026-10-19T17:00", "2026-10-19T23:30")):
        app.do("add", title="Lab", when="fixed", start=start, end=end)


def blocks(app: App, title: str) -> list[dict]:
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-21T00:00")
    return [b for b in plan["blocks"] if b["title"] == title]


def test_work_goes_on_top_of_a_task_that_runs_by_itself(app: App) -> None:
    afternoon_only(app)
    laundry = app.do("add", title="Laundry", duration_min=120, due="2026-10-19T17:00")["item"]["id"]
    app.do("add", title="Essay", duration_min=150, due="2026-10-19T17:00")
    replan(app.conn, app.now_utc)
    assert app.do("status")["late"]  # 4.5 hours of work in 3 free hours
    assert app.do("edit", id=laundry, background=True)["item"]["background"]
    replan(app.conn, app.now_utc)
    assert not app.do("status")["late"]  # a quarter hour to start the laundry, then the essay while it runs
    (run,) = blocks(app, "Laundry")
    assert run["background"] and run["start"] <= "2026-10-19T15:00"  # started early enough to finish by 5pm
    assert run["end"] == f"{run['start'][:11]}{int(run['start'][11:13]) + 2:02d}{run['start'][13:]}"  # all two hours
    day = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    essay = sum(1 for b in day["blocks"] if b["title"] == "Essay")
    assert essay and day["day_hours"]["2026-10-19"] == 2.5 + 0.25  # the essay, and the laundry's quarter hour
    held = app.table("blocks")
    mine = [b for b in held if b["item_id"] == laundry and b["plan_id"] == max(r["plan_id"] for r in held)]
    assert len(mine) == 1  # the plan holds only the start


def test_once_started_it_is_not_planned_again(app: App) -> None:
    laundry = app.do("add", title="Laundry", duration_min=90, due="2026-10-20T20:00", background=True)["item"]["id"]
    replan(app.conn, app.now_utc)
    assert blocks(app, "Laundry")
    app.do("log", id=laundry, start="2026-10-19T08:30", end="2026-10-19T08:45")
    replan(app.conn, app.now_utc)
    assert blocks(app, "Laundry") == []
