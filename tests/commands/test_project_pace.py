"""A project's pace changes how it's planned (17 Nov, the user: "when changing the pace of a project, the user can see a
change in the actual way that it plans because i did it and i saw no change"). Front-loaded plans most of a project in
its first days, toward the end most in its last, evenly in between; never late for it, and its steps still in order.
With no pace set, as soon as there's time (test_as_soon_as_there_is_time.py).

Whole system, through the commands and the planner, from Monday 19 Oct 2026 9am with two weeks planned."""

from pathlib import Path

import pytest

from friday.core.time import parse_local, parse_utc, to_utc
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app

PACES = ("front", "linear", "back")
MONDAY_NIGHT = parse_utc("2026-10-20T08:00Z")  # Tuesday 20 Oct, 4am in New York
WEDNESDAY_NIGHT = parse_utc("2026-10-22T08:00Z")  # Thursday 22 Oct, 4am in New York: Wednesday's planning day is over
THURSDAY_NIGHT = parse_utc("2026-10-23T08:00Z")  # Friday 23 Oct, 4am in New York
SUNDAY_NIGHT = parse_utc("2026-10-26T08:00Z")  # the end of the first week (Monday 26 Oct, 4am in New York)


def planned(app: App) -> list[tuple[int, int, int]]:
    """The current plan's blocks as (item, start, end)."""
    plan = app.conn.execute("SELECT id FROM plans WHERE status = 'current'").fetchone()[0]
    found = app.conn.execute("SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ?", [plan])
    return [(r[0], parse_utc(r[1]), parse_utc(r[2])) for r in found]


def hours_by(app: App, steps: list[int], moment: int) -> float:
    return sum(min(end, moment) - start for item, start, end in planned(app) if item in steps and start < moment) / 60


def middle(app: App, steps: list[int]) -> float:
    """When the steps' planned work falls on average: the middle of each block, weighed by its length."""
    found = [(start, end) for item, start, end in planned(app) if item in steps]
    return sum((start + end) / 2 * (end - start) for start, end in found) / sum(end - start for start, end in found)


def steps_of(app: App, project: int) -> list[int]:
    [shown] = [p for p in app.do("projects") if p["item"]["id"] == project]
    return [c["id"] for c in shown["children"]]


def essay(app: App, due: str) -> tuple[int, list[int]]:
    made = app.do("template_apply", template="Essay", title="Essay", hours=6, due=due)["item"]["id"]
    return made, steps_of(app, made)


def paced(tmp_path: Path, due: str, moment: int) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Hours of a 6-hour essay planned before `moment`, in all, and when on average, for each pace, each on an empty
    calendar of its own."""
    out, whole, mean = {}, {}, {}
    for pace in PACES:
        (tmp_path / pace).mkdir()
        app = new_app(tmp_path / pace, horizon_days=14)
        made, steps = essay(app, due)
        app.do("project_set", id=made, pacing=pace)
        replan(app.conn, app.now_utc)
        out[pace] = hours_by(app, steps, moment)
        whole[pace] = hours_by(app, steps, parse_utc("2027-01-01T00:00Z"))
        mean[pace] = middle(app, steps)
    return out, whole, mean


def test_a_project_due_next_week_is_planned_by_its_pace(tmp_path: Path) -> None:
    # Due Monday week: every pace planned 1 hour on Monday, 3 on Friday and 2¼ on Saturday (the same plan)
    hours, whole, mean = paced(tmp_path, "2026-10-26T23:59", WEDNESDAY_NIGHT)
    assert all(planned >= 6 for planned in whole.values()), whole
    assert mean["front"] < mean["linear"] < mean["back"], mean
    assert hours["front"] > hours["back"] and hours["linear"] > hours["back"], hours


def test_a_project_due_in_three_weeks_is_planned_by_its_pace_in_the_first(tmp_path: Path) -> None:
    hours, _, _ = paced(tmp_path, "2026-11-09T23:59", SUNDAY_NIGHT)
    assert hours["front"] > hours["linear"] > hours["back"], hours


def test_changing_a_projects_pace_changes_the_plan_you_have(tmp_path: Path) -> None:
    # The plan you have held every block where it was (minimize_changes, above any pace): changing it showed nothing
    app = new_app(tmp_path, horizon_days=14)
    made, steps = essay(app, "2026-10-26T23:59")
    app.do("project_set", id=made, pacing="linear")
    replan(app.conn, app.now_utc)
    evenly = middle(app, steps)
    app.do("project_set", id=made, pacing="front")
    replan(app.conn, app.now_utc)
    early = middle(app, steps)
    app.do("project_set", id=made, pacing="back")
    replan(app.conn, app.now_utc)
    late = middle(app, steps)
    assert early < evenly < late, (early, evenly, late)


def test_a_project_begun_weeks_ago_is_paced_from_now(tmp_path: Path) -> None:
    # Made two weeks before with nothing done, it was behind every pace's line, so every pace planned most of it on
    # the first day (5 hours of 6.5 front-loaded, 4 toward the end)
    hours, first_day = {}, {}
    for pace in ("front", "back"):
        (tmp_path / pace).mkdir()
        app = new_app(tmp_path / pace, now="2026-10-05T09:00", horizon_days=14)
        _, steps = project(app, "2026-10-26T23:59", [("Research", 120), ("Draft", 180), ("Edit", 90)], pace)
        app.at("2026-10-19T09:00")
        replan(app.conn, app.now_utc)
        hours[pace] = hours_by(app, steps, THURSDAY_NIGHT)
        first_day[pace] = hours_by(app, steps, MONDAY_NIGHT)
    assert hours["front"] > hours["back"], hours
    assert first_day["back"] == 0, first_day


def project(app: App, due: str, steps: list[tuple[str, int]], pace: str) -> tuple[int, list[int]]:
    made = app.do("add", title="Report", preset="Project", due=due)["item"]["id"]
    ids = [app.do("add", title=t, preset="Assignment", duration_min=m, parent_id=made)["item"]["id"] for t, m in steps]
    app.do("project_set", id=made, pacing=pace)
    return made, ids


def busy(app: App, days: list[str]) -> None:
    for day in days:
        app.do("add", title="Shift", when="fixed", start=f"2026-10-{day}T07:30", end=f"2026-10-{day}T23:00",
               preset="Event")  # fmt: skip


@pytest.mark.parametrize(
    ("pace", "full", "due"),
    [
        ("front", ["19", "20", "21", "22", "23"], "2026-10-25T17:00"),  # front-loaded, with room only at the weekend
        ("back", ["21", "22", "23"], "2026-10-23T17:00"),  # toward the end, with room only on Monday and Tuesday
    ],
)
def test_a_pace_never_makes_work_late(tmp_path: Path, pace: str, full: list[str], due: str) -> None:
    app = new_app(tmp_path, horizon_days=14)
    busy(app, full)
    _, ids = project(app, due, [("Research", 120), ("Draft", 180), ("Edit", 90)], pace)
    replan(app.conn, app.now_utc)
    found = planned(app)
    for step, minutes in zip(ids, (120, 180, 90), strict=True):
        assert sum(end - start for item, start, end in found if item == step) >= minutes
    assert max(end for item, _, end in found if item in ids) <= to_utc(parse_local(due), TZ)
    assert app.do("projects")[0]["status"] == "on_track"


@pytest.mark.parametrize("pace", ["front", "back"])
def test_a_pace_keeps_the_steps_in_their_order(tmp_path: Path, pace: str) -> None:
    app = new_app(tmp_path, horizon_days=14)
    _, ids = project(app, "2026-10-27T17:00", [("Research", 120), ("Outline", 60), ("Draft", 240), ("Edit", 90)], pace)
    replan(app.conn, app.now_utc)
    found = planned(app)
    first = {i: min(start for item, start, _ in found if item == i) for i in ids}
    last = {i: max(end for item, _, end in found if item == i) for i in ids}
    for before, after in zip(ids, ids[1:], strict=False):
        assert first[after] >= last[before]
