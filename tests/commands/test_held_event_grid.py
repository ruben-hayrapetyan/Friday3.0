"""An event held for a task gives the task its time, whatever minute it starts (23 Nov, a test user's screenshot: LING
1100 9:05–10:00, "Work through it", "Time for Final Presentations: Planned here first", yet the plan put Final
Presentations the next afternoon and called it late). The hold took the task's minutes from 9:05, and the planner
kept only grid slots lying wholly inside that span: a week out, on half-hour slots, 9:05–9:50 held none, so a 45-minute
task was planned a week early, and a 2-hour one got 9:30–10:00 only. Now the hold takes whole slots inside the event,
as many as the task needs, from the first. Monday 19 Oct 2026 9am; the class a week later."""

from pathlib import Path

import pytest

from friday.core.time import parse_utc, to_local
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-10-19T09:00", horizon_days=14)


def held_class(app: App, minutes: int, due: str, start: str = "2026-10-26T09:05") -> int:
    event = app.do("add", title="LING 1100", when="fixed", start=start, end="2026-10-26T10:00")["item"]["id"]
    task = app.do("add", title="Final Presentations", duration_min=minutes, due=due, firmness="hard")["item"]["id"]
    app.do("event_hold", id=event, task_id=task)
    replan(app.conn, app.now_utc)
    return task


def times(app: App, item: int) -> list[str]:
    plan = app.table("plans")[-1]["id"]
    mine = [b for b in app.table("blocks") if b["plan_id"] == plan and b["item_id"] == item]
    out = sorted((b["start_utc"], b["end_utc"]) for b in mine)
    return [f"{to_local(parse_utc(a), TZ):%a %H:%M}–{to_local(parse_utc(b), TZ):%H:%M}" for a, b in out]


def test_a_short_task_is_planned_in_the_class(app: App) -> None:
    """A week out the grid is half-hourly: 9:30–10:00 is the class's whole slot, and the task is there."""
    task = held_class(app, 45, "2026-10-26T17:00")
    assert "Mon 09:30–10:00" in times(app, task)


def test_a_long_task_has_the_class_and_the_rest_around_it(app: App) -> None:
    task = held_class(app, 120, "2026-10-26T17:00")
    assert "Mon 09:30–10:00" in times(app, task)


def test_on_quarter_hours_the_class_holds_all_the_task_needs(app: App) -> None:
    """Within the plan's first days slots are quarter hours: 9:15–10:00 lies inside 9:05–10:00."""
    app.now_utc += 6 * 1440  # Sunday 25 Oct: the class is tomorrow
    task = held_class(app, 45, "2026-10-26T17:00")
    assert times(app, task) == ["Mon 09:15–10:00"]


def event_of(app: App, title: str = "LING 1100") -> dict:
    [found] = [i for i in app.table("items") if i["title"] == title]
    return app.do("item", id=found["id"])["item"]


def test_the_event_says_the_plan_s_time_for_the_task_in_it(app: App) -> None:
    """The event's panel said "Planned here first" whatever the plan did; now it carries the plan's time there."""
    held_class(app, 45, "2026-10-26T17:00")
    holds = event_of(app)["holds"]
    assert holds["here"][1] == "2026-10-26T10:00" and holds["here"][0] in ("2026-10-26T09:05", "2026-10-26T09:30")
    assert "elsewhere" not in holds


def test_the_event_says_where_the_task_is_when_it_is_not_in_it(app: App) -> None:
    """A task you can only start after the class can't be in it: the event says where the plan has it instead."""
    event = app.do("add", title="LING 1100", when="fixed", start="2026-10-26T09:05", end="2026-10-26T10:00")["item"]
    task = app.do("add", title="Final Presentations", duration_min=45, release="2026-10-26T11:00",
                  due="2026-10-28T17:00", firmness="hard")["item"]["id"]  # fmt: skip
    app.do("event_hold", id=event["id"], task_id=task)
    replan(app.conn, app.now_utc)
    holds = event_of(app)["holds"]
    plan = app.table("plans")[-1]["id"]
    first = min(b["start_utc"] for b in app.table("blocks") if b["item_id"] == task and b["plan_id"] == plan)
    assert "here" not in holds
    assert holds["elsewhere"] == f"{to_local(parse_utc(first), TZ):%Y-%m-%dT%H:%M}"
