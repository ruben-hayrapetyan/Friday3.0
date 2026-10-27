"""The plan view between a change and its replan (27 Oct): the quick placement made with the change stands for what's
ahead, so a pinned block stays where you put it and work moves out from under an event you just added, until the
solve lands. A change that doesn't place (a job, the command line) leaves the saved plan showing."""

from pathlib import Path

import pytest

from friday.planner.service import plan_snapshot, replan, save_plan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def blocks_of(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def planned(app: App, text: str) -> tuple[int, tuple[str, str]]:
    item_id = app.do("add", text=text)["item"]["id"]
    replan(app.conn, app.now_utc)
    return item_id, blocks_of(app, item_id)[0]


def test_a_pinned_block_stays_where_you_put_it_until_the_replan(app: App) -> None:
    essay, (start, end) = planned(app, "essay due wed ~2h")
    app.full("pin", payload={"id": essay, "start": "2026-10-20T15:00", "end": "2026-10-20T17:00", "from_start": start,
                             "from_end": end})  # fmt: skip
    view = app.do("plan")
    assert view["provisional"]
    assert blocks_of(app, essay) == [("2026-10-20T15:00", "2026-10-20T17:00")]
    replan(app.conn, app.now_utc)
    assert not app.do("plan")["provisional"]
    assert blocks_of(app, essay) == [("2026-10-20T15:00", "2026-10-20T17:00")]


def test_a_dragged_block_is_where_you_put_it_and_gone_from_where_it_was(app: App) -> None:
    essay, (start, end) = planned(app, "essay due wed ~2h")
    app.full("pin", payload={"id": essay, "start": "2026-10-20T15:00", "end": "2026-10-20T17:00", "kind": "preferred",
                             "from_start": start, "from_end": end})  # fmt: skip  # what a drag sends
    assert app.do("plan")["provisional"]
    assert blocks_of(app, essay) == [("2026-10-20T15:00", "2026-10-20T17:00")]


def test_one_block_of_several_dragged_leaves_the_others(app: App) -> None:
    essay = app.do("add", text="essay due wed ~6h")["item"]["id"]
    replan(app.conn, app.now_utc)
    before = blocks_of(app, essay)
    assert len(before) >= 2
    start, end = before[-1]
    length = minutes(start, end)
    to = "2026-10-20T07:30" if not before[0][0].startswith("2026-10-20T07") else "2026-10-21T07:30"
    to_end = f"{to[:11]}{(450 + length) // 60:02d}:{(450 + length) % 60:02d}"
    app.full("pin", payload={"id": essay, "start": to, "end": to_end, "kind": "preferred", "from_start": start,
                             "from_end": end})  # fmt: skip
    shown = blocks_of(app, essay)
    assert (to, to_end) in shown
    assert (start, end) not in shown
    assert [b for b in before[:-1] if b in shown] == before[:-1]  # the others stay as they were
    assert sum(minutes(s, e) for s, e in shown) == 360


def test_a_to_do_dropped_on_the_calendar_is_all_there(app: App) -> None:
    essay, _ = planned(app, "essay due wed ~2h")
    app.full("pin", payload={"id": essay, "start": "2026-10-20T15:00", "kind": "preferred"})  # a to-do row dropped
    assert blocks_of(app, essay) == [("2026-10-20T15:00", "2026-10-20T17:00")]


def test_work_moves_out_from_under_an_event_you_just_added(app: App) -> None:
    essay, (start, end) = planned(app, "essay due wed ~2h")
    app.full("add", payload={"title": "Coffee", "when": "fixed", "start": start, "end": end})
    shown = blocks_of(app, essay)
    assert shown, "the essay is still on the calendar"
    assert all(e <= start or s >= end for s, e in shown)
    assert sum(minutes(s, e) for s, e in shown) == 120
    assert all(s[:10] == start[:10] for s, _ in shown)  # it stepped aside, not off to the first free time days away
    assert len(shown) == 1  # in one piece, where there's room for it


def test_a_change_that_doesnt_place_shows_the_saved_plan(app: App) -> None:
    essay, (start, end) = planned(app, "essay due wed ~2h")
    app.do("pin", id=essay, start="2026-10-20T15:00", end="2026-10-20T17:00", from_start=start, from_end=end)
    assert not app.do("plan")["provisional"]
    assert blocks_of(app, essay) == [(start, end)]


def test_an_older_solve_landing_after_a_change_doesnt_undo_it_on_the_calendar(app: App) -> None:
    essay, (start, end) = planned(app, "essay due wed ~2h")
    app.do("add", text="reading due thu ~1h")  # a change whose solve is under way...
    older = take_snapshot(app.conn, app.now_utc)
    app.full("pin", payload={"id": essay, "start": "2026-10-20T15:00", "end": "2026-10-20T17:00", "from_start": start,
                             "from_end": end})  # fmt: skip  # ...when you pin
    assert save_plan(app.conn, older, plan_snapshot(older, warm=True), "test") is not None
    assert app.do("plan")["provisional"]
    assert blocks_of(app, essay) == [("2026-10-20T15:00", "2026-10-20T17:00")]


def test_a_block_under_way_stays_as_planned(app: App) -> None:
    essay, (start, end) = planned(app, "essay due wed ~2h")
    app.at(start).now_utc += 30  # half an hour into it
    app.full("add", payload={"title": "Call", "when": "fixed", "start": "2026-10-21T10:00", "end": "2026-10-21T11:00"})
    shown = blocks_of(app, essay)
    assert shown[0][0] == start
    assert not any(s < shown[0][1] and e > shown[0][0] for s, e in shown[1:])


def minutes(start: str, end: str) -> int:
    def at(t: str) -> int:
        return int(t[8:10]) * 1440 + int(t[11:13]) * 60 + int(t[14:16])

    return at(end) - at(start)
