"""A gap only keeping the plan steady held, through the planner and its database (5 Nov: the reading left at 12:30am
after a problem set ending at 12:15): your pins, a replan, the reading let go, and the next replan closing the gap."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def blocks(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def test_a_reading_let_go_a_quarter_hour_after_the_essay_moves_up_to_meet_it(app: App) -> None:
    essay = app.do("add", title="Essay", preset="Assignment", duration_min=60, due="2026-10-22T09:00")["item"]["id"]
    reading = app.do("add", title="Reading", preset="Reading", duration_min=45, release="2026-10-21T15:00",
                     due="2026-10-21T16:00")["item"]["id"]  # fmt: skip
    app.do("pin", id=essay, start="2026-10-21T14:00", end="2026-10-21T15:00", kind="preferred")
    app.do("pin", id=reading, start="2026-10-21T15:15", end="2026-10-21T16:00", kind="preferred")
    app.do("replan")
    assert blocks(app, reading) == [("2026-10-21T15:15", "2026-10-21T16:00")]
    app.do("unpin", id=reading)
    app.do("replan")
    assert blocks(app, reading) == [("2026-10-21T15:00", "2026-10-21T15:45")]
    assert blocks(app, essay) == [("2026-10-21T14:00", "2026-10-21T15:00")]
    app.do("replan")  # and it stays: nothing pulls it back
    assert blocks(app, reading) == [("2026-10-21T15:00", "2026-10-21T15:45")]
