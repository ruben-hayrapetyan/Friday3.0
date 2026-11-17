"""An event's three choices (12 Nov: "the work through it button should not be the same as the skip button"): going,
working through it (there, but its time is work's, drawn as it is) and skipping it (not going, crossed out)."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_utc
from friday.planner.service import replan
from friday.planner.snapshot import EVENTS_GOING
from friday.planner.store import kv_get
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def lecture(app: App) -> int:
    return app.do("add", title="Lecture", when="fixed", start="2026-10-20T10:00", end="2026-10-20T11:00")["item"]["id"]


def facts(app: App, item_id: int) -> dict:
    return app.do("item", id=item_id)["item"]


def test_working_through_frees_its_time_but_isnt_skipping(app: App) -> None:
    event = lecture(app)
    app.do("event_choice", id=event, choice="through")
    assert facts(app, event)["left_out"] == "through"
    assert app.conn.execute("SELECT blocks_time FROM items WHERE id = ?", [event]).fetchone()[0] == 0
    app.do("event_choice", id=event, choice="skip")
    assert facts(app, event)["left_out"] == "skipped"
    app.do("event_choice", id=event, choice="going")
    assert facts(app, event)["left_out"] is None
    assert app.conn.execute("SELECT blocks_time FROM items WHERE id = ?", [event]).fetchone()[0] == 1


def test_going_or_skipping_lets_go_of_the_to_do_its_time_was_for(app: App) -> None:
    event = lecture(app)
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("event_choice", id=event, choice="through")
    app.do("event_hold", id=event, task_id=essay)
    assert facts(app, event)["holds"]["id"] == essay
    app.do("event_choice", id=event, choice="skip")
    assert facts(app, event)["holds"] is None


def test_a_choice_is_undone_whole(app: App) -> None:
    event = lecture(app)
    made = app.full("event_choice", payload={"id": event, "choice": "through"})
    app.do("undo", command_id=made.command_id)
    assert facts(app, event)["left_out"] is None


def test_only_an_event_has_these_choices(app: App) -> None:
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    with pytest.raises(FieldError, match="isn't an event"):
        app.do("event_choice", id=essay, choice="skip")


# Marked free in its calendar (16 Nov, a client's note: free events had none of the three choices; worked through by
# default; one that takes your time comes first in the Now bar, even begun later)


def free_event(app: App, start: str = "2026-10-20T10:00", end: str = "2026-10-20T11:00") -> int:
    return app.do("add", title="Office hours", when="fixed", start=start, end=end, free=True)["item"]["id"]


def test_a_free_event_is_worked_through_until_you_choose(app: App) -> None:
    event = free_event(app)
    assert facts(app, event)["left_out"] == "free"  # the card reads it as Work through it


def test_going_to_a_free_event_makes_it_take_your_time_in_friday_only(app: App) -> None:
    event = free_event(app)
    app.do("event_choice", id=event, choice="going")
    assert facts(app, event)["left_out"] is None
    assert kv_get(app.conn, EVENTS_GOING, []) == [event]
    assert app.conn.execute("SELECT free FROM items WHERE id = ?", [event]).fetchone()[0] == 1  # still free there
    app.do("event_choice", id=event, choice="through")
    assert facts(app, event)["left_out"] == "through" and kv_get(app.conn, EVENTS_GOING, []) == []
    app.do("event_choice", id=event, choice="skip")
    assert facts(app, event)["left_out"] == "skipped"
    app.do("event_choice", id=event, choice="going")
    assert facts(app, event)["left_out"] is None


def test_going_to_a_busy_event_isnt_kept_as_going_to_a_free_one(app: App) -> None:
    app.do("event_choice", id=lecture(app), choice="going")
    assert kv_get(app.conn, EVENTS_GOING, []) in ([], None)


def test_the_plan_keeps_work_off_a_free_event_only_once_youre_going(app: App) -> None:
    app.at("2026-10-20T08:00")
    event = free_event(app, "2026-10-20T09:00", "2026-10-20T17:00")
    app.do("add", title="Essay", duration_min=120, due="2026-10-20T18:00")

    def work_inside() -> int:
        replan(app.conn, app.now_utc)
        plan_id = max(b["plan_id"] for b in app.table("blocks"))
        lo, hi = parse_utc("2026-10-20T13:00Z"), parse_utc("2026-10-20T21:00Z")  # 9am to 5pm, New York
        return sum(1 for b in app.table("blocks") if b["plan_id"] == plan_id and b["item_id"] != event
                   and parse_utc(b["start_utc"]) < hi and parse_utc(b["end_utc"]) > lo)  # fmt: skip

    assert work_inside() > 0  # worked through: its day is work's
    app.do("event_choice", id=event, choice="going")
    assert work_inside() == 0


def test_the_now_bar_shows_the_event_that_takes_your_time_even_begun_later(app: App) -> None:
    free = free_event(app, "2026-10-20T10:00", "2026-10-20T12:00")
    busy = app.do("add", title="Lab", when="fixed", start="2026-10-20T10:30", end="2026-10-20T11:30")["item"]["id"]
    app.at("2026-10-20T10:45")
    assert app.do("now")["current"]["item_id"] == busy
    app.do("event_choice", id=free, choice="going")
    assert app.do("now")["current"]["item_id"] == free  # going, it takes your time, and it began first


def test_a_free_event_shows_when_nothing_else_is_on_and_doesnt_end_your_free_time(app: App) -> None:
    free = free_event(app, "2026-10-20T10:00", "2026-10-20T11:00")
    later = free_event(app, "2026-10-20T13:00", "2026-10-20T14:00")
    busy = app.do("add", title="Lab", when="fixed", start="2026-10-20T15:00", end="2026-10-20T16:00")["item"]["id"]
    app.at("2026-10-20T10:15")
    now = app.do("now")
    assert now["current"]["item_id"] == free
    assert now["next"]["item_id"] == busy and later != busy  # the free one at 1pm isn't what ends your free time
