"""Fixing timed work (28 Oct: "how to manually edit the time that i spent on something (like what if i forgot to
turn the timer off)"): stopping as of when you really stopped, and changing or taking away a sitting afterwards, so the
time counted as done, and what Friday learns of how long things take, are what you really did."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def essay(app: App) -> int:
    return app.do("add", text="essay due fri 5pm ~3h")["item"]["id"]


def done_min(app: App, item: int) -> int:
    return app.do("item", id=item)["item"]["done_min"]


def timer_rows(app: App) -> list[tuple[str, str, int]]:
    return [(r["start_utc"], r["end_utc"], r["minutes"]) for r in app.table("progress") if r["source"] == "timer"]


def test_a_timer_left_running_is_stopped_as_of_when_you_stopped(app: App) -> None:
    item = essay(app)
    app.do("start", id=item)
    app.at("2026-10-19T14:00")  # forgot it: five hours later
    out = app.do("stop", at="2026-10-19T10:15")
    assert out["minutes"] == 75 and "75 min" in out["message"]
    assert timer_rows(app) == [("2026-10-19T13:00Z", "2026-10-19T14:15Z", 75)]
    assert done_min(app, item) == 75


def test_a_stop_time_before_the_start_or_after_now_is_refused(app: App) -> None:
    app.do("start", id=essay(app))
    app.at("2026-10-19T10:00")
    with pytest.raises(FieldError, match="after you started"):
        app.do("stop", at="2026-10-19T08:30")
    with pytest.raises(FieldError, match="later than now"):
        app.do("stop", at="2026-10-19T11:00")
    assert app.do("stop", at="2026-10-19T09:30")["minutes"] == 30


def test_a_sitting_is_changed_afterwards_and_counts_as_changed(app: App) -> None:
    item = essay(app)
    app.do("start", id=item)
    app.at("2026-10-19T13:00")
    app.do("stop")
    assert done_min(app, item) == 240
    app.do("sitting_edit", id=item, start="2026-10-19T09:00", end="2026-10-19T13:00",
           new_start="2026-10-19T09:10", new_end="2026-10-19T10:40")  # fmt: skip
    assert timer_rows(app) == [("2026-10-19T13:10Z", "2026-10-19T14:40Z", 90)]
    assert done_min(app, item) == 90
    # What the calendar draws is the corrected sitting.
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    drawn = plan["sessions"]
    assert [(b["start"], b["end"]) for b in drawn] == [("2026-10-19T09:10", "2026-10-19T10:40")]


def test_a_sitting_shown_as_one_but_timed_in_pieces_is_changed_as_one(app: App) -> None:
    item = essay(app)
    app.do("start", id=item)
    app.at("2026-10-19T09:30")
    app.do("stop")
    app.do("start", id=item)  # resumed at once: the calendar shows 9:00 to 10:00 as one sitting
    app.at("2026-10-19T10:00")
    app.do("stop")
    assert len(timer_rows(app)) == 2
    app.do("sitting_edit", id=item, start="2026-10-19T09:00", end="2026-10-19T10:00",
           new_start="2026-10-19T09:00", new_end="2026-10-19T09:45")  # fmt: skip
    assert timer_rows(app) == [("2026-10-19T13:00Z", "2026-10-19T13:45Z", 45)]


def test_a_sitting_is_taken_away_and_undone(app: App) -> None:
    item = essay(app)
    app.do("start", id=item)
    app.at("2026-10-19T10:00")
    app.do("stop")
    said = app.full("sitting_delete", payload={"id": item, "start": "2026-10-19T09:00", "end": "2026-10-19T10:00"})
    assert said.result["message"].startswith("Removed 60 min")
    assert timer_rows(app) == [] and done_min(app, item) == 0
    app.do("undo", command_id=said.command_id)
    assert done_min(app, item) == 60


def test_a_changed_sitting_must_be_in_the_past_and_forward(app: App) -> None:
    item = essay(app)
    app.do("start", id=item)
    app.at("2026-10-19T10:00")
    app.do("stop")
    span = {"id": item, "start": "2026-10-19T09:00", "end": "2026-10-19T10:00"}
    with pytest.raises(FieldError, match="after the start"):
        app.do("sitting_edit", **span, new_start="2026-10-19T09:30", new_end="2026-10-19T09:10")
    with pytest.raises(FieldError, match="later than now"):
        app.do("sitting_edit", **span, new_start="2026-10-19T09:30", new_end="2026-10-19T11:00")
    with pytest.raises(FieldError, match="no timed sitting"):
        app.do("sitting_delete", id=item, start="2026-10-19T07:00", end="2026-10-19T08:00")
