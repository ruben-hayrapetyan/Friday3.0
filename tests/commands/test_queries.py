"""What the app asks for (commands/queries.py), at the edges: the timed block now, what fits a gap, an optional event
you said you'd go to, a past block of a finished task, items of one tag, and an event's next or last time.
Monday 2026-10-19 in New York."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def test_the_task_being_timed_runs_until_its_own_block_ends(app: App) -> None:
    essay = app.do("add", text="essay due wed ~4h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T09:00", end="2026-10-19T10:30", kind="locked")
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    now = app.do("now")
    assert now["current"]["item_id"] == essay and now["current"]["end"] == "2026-10-19T10:30"


def test_what_fits_a_gap_is_what_can_be_done_in_it(app: App) -> None:
    app.do("add", title="Laundry", duration_min=30)
    app.do("add", title="Thesis", duration_min=600, due="2026-10-21T17:00")
    replan(app.conn, app.now_utc)
    assert [(f["title"], f["minutes"]) for f in app.do("fits", minutes=30)] == [("Laundry", 30)]


def test_an_optional_event_you_said_you_go_to_is_drawn_as_going(app: App) -> None:
    gym = app.do("add", title="Gym", when="fixed", start="2026-10-19T13:00", end="2026-10-19T14:00")["item"]["id"]
    app.do("rule_add", text="gym is optional")
    app.do("event_keep", id=gym, going=True)
    replan(app.conn, app.now_utc)
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    (shown,) = [f for f in plan["fixed"] if f["id"] == gym]
    assert (shown["optional"], shown["going"]) == (True, True)


def test_a_past_block_of_a_task_ticked_done_is_drawn_done(app: App) -> None:
    essay = app.do("add", text="essay due wed ~4h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T09:00", end="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00").do("done", id=essay)
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    assert [b["state"] for b in plan["blocks"] if b["item_id"] == essay and b["start"] == "2026-10-19T09:00"] == [
        "done"
    ]


def test_items_are_found_by_their_tag(app: App) -> None:
    app.do("add", text="PS5 #cs1110 ~1h")
    app.do("add", text="Lab #chem ~1h")
    assert [i["title"] for i in app.do("items", area="CS1110")] == ["PS5"]


def test_an_event_that_repeats_shows_its_next_time_over_ones_gone(app: App) -> None:
    app.do("add", title="Salsa", when="fixed", start="2026-10-19T19:00", end="2026-10-19T20:00", every="every day")
    app.at("2026-10-21T21:00")
    (salsa,) = app.do("events", text="salsa")
    assert salsa["start"] == "2026-10-22T19:00"
