"""A pin holds (27 Oct: "my pinned timeslots keep moving"). A block pinned on the night before climbing club, with "no
work after 10pm the night before climbing club" (Always), was moved to another evening by the next replan, again each
time it was put back: a rule's forbid outranked the pin. Now no rule forbids a pin, and keeping one outweighs a
later evening; only work that would be late moves it."""

from pathlib import Path

import pytest

from friday.core.rule_text import read
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def blocks_of(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def test_a_pin_on_the_night_before_holds_against_the_rule(app: App) -> None:
    app.do("add", title="Climbing Club", when="fixed", start="2026-10-21T06:00", end="2026-10-21T08:00")
    said = "no work after 10pm the night before climbing club"
    app.do("rule_add", text=said, strength="Always")
    assert read(said)[0] is not None
    essay = app.do("add", text="essay due wed ~3h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-20T21:00", end="2026-10-21T00:00", kind="preferred")
    for _ in range(2):  # and again: it stays
        replan(app.conn, app.now_utc)
        assert blocks_of(app, essay) == [("2026-10-20T21:00", "2026-10-21T00:00")]


def test_a_late_pin_holds_against_a_later_evening(app: App) -> None:
    essay = app.do("add", text="essay due wed ~2h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T22:30", end="2026-10-20T00:30", kind="preferred")
    replan(app.conn, app.now_utc)
    assert blocks_of(app, essay) == [("2026-10-19T22:30", "2026-10-20T00:30")]


def test_a_pin_still_gives_way_to_work_being_late(app: App) -> None:
    essay = app.do("add", text="essay due mon 18:00 ~2h")["item"]["id"]
    report = app.do("add", text="report due mon 13:00 ~3h")["item"]["id"]  # needs 10–13, where the essay is pinned
    app.do("pin", id=essay, start="2026-10-19T10:00", end="2026-10-19T12:00", kind="preferred")
    replan(app.conn, app.now_utc)
    assert all(e <= "2026-10-19T13:00" for _, e in blocks_of(app, report))
