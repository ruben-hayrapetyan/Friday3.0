"""What the "won't make it" window offers (20 Nov, a user's notes: "2.0 h of work won't make it ... Pick what gives"
with nothing to pick: "friday is not actually suggesting that I sleep later/whatever other option like it proposes";
your answer: "there should be stuff that is offered (eg skipping events that you usually skip, making another event
late, going to sleep later/waking up earlier)"). Each option is tried on a copy of the plan and offered when it helps.
Whole system, a scratch Friday, Monday 19 October 2026 at 11:20pm; you sleep 11:30pm to 7:30am."""

from pathlib import Path

import pytest

from friday.core.time import format_local, to_local
from friday.planner.prepare import build_input
from friday.planner.service import quick_late, replan
from friday.planner.snapshot import take_snapshot
from friday.planner.views import candidate_actions
from tests.commands.helpers import TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-10-19T23:20")
    exam = app.do("add", title="CHEM 2090 Prelim 3", preset="Exam", start="2026-10-20T19:00", end="2026-10-20T20:30")
    app.do("add", title="CHEM 2090 Lecture", when="fixed", start="2026-10-20T10:10", end="2026-10-20T11:25")
    app.do("add", title="brain dump study", preset="Exam prep", due="2026-10-20T19:00", duration_min=780,
           before=[exam["item"]["id"]])  # fmt: skip
    return app


def offered(app: App) -> dict[str, dict]:
    replan(app.conn, app.now_utc)
    return {o["action"]: o for o in app.do("triage")["options"]}


def test_the_notes_case_late_at_night_with_only_classes_left_it_offers_more_awake_hours(app: App) -> None:
    options = offered(app)
    assert "Stay up an hour later tonight, until 12:30am" in options
    assert "Get up an hour earlier tomorrow, at 6:30am" in options
    assert not any(a.startswith("Skip CHEM 2090 Lecture") for a in options)  # a class is never offered


def test_staying_up_later_is_tonights_bedtime_an_hour_on_and_saves_time(app: App) -> None:
    replan(app.conn, app.now_utc)
    before = app.do("triage")["late"]["brain dump study"]
    option = offered(app)["Stay up an hour later tonight, until 12:30am"]
    assert option["steps"] == [{"command": "day_override", "input": {"date": "2026-10-19", "bedtime": "00:30"}}]
    for step in option["steps"]:
        app.do(step["command"], **step["input"])
    replan(app.conn, app.now_utc)
    after = app.do("triage")["late"].get("brain dump study", 0)
    assert after < before


def test_getting_up_earlier_is_tomorrows_wake_an_hour_sooner(app: App) -> None:
    option = offered(app)["Get up an hour earlier tomorrow, at 6:30am"]
    assert option["steps"] == [{"command": "day_override", "input": {"date": "2026-10-20", "wake": "06:30"}}]


def test_other_less_important_work_due_first_is_tried_with_one_more_day(app: App) -> None:
    """Glass box: the option is made and tried; it's offered when the trial saves time (here the day's room is what
    holds the prep back, so it isn't)."""
    reading = app.do(
        "add", title="HIST reading response", preset="Reading", due="2026-10-20T12:00", duration_min=180, importance=2
    )  # less important than the prep: what may give way
    snapshot = take_snapshot(app.conn, app.now_utc)
    inp = build_input(snapshot)
    _, late = quick_late(inp, with_fallback=False)
    made = {action: steps for action, steps, *_ in candidate_actions(snapshot, inp, late)}
    [step] = made["Give HIST reading response one more day"]
    due = app.do("item", id=reading["item"]["id"])["item"]["due"]
    assert step[0] == "edit" and step[1]["id"] == reading["item"]["id"]
    assert format_local(to_local(step[1]["due_utc"], TZ)) == "2026-10-21T12:00" and due == "2026-10-20T12:00"
