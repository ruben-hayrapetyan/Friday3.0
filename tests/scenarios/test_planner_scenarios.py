"""Scenarios 3, 4, 21, 22, 24 and 29 of DESIGN §24.2: the planner and commands around the scheduler.

Monday 2026-10-19 in New York, with the test settings of tests/commands/helpers.py (sleep 23:30–07:30).
"""

from pathlib import Path

import pytest

from friday.core.time import parse_local, to_utc
from friday.planner.prepare import build_input, day_scales
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import TZ, App, new_app
from tests.commands.test_registry import state


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def utc(local: str) -> int:
    return to_utc(parse_local(local), TZ)


def plan_blocks(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["item_id"] == item_id]


def wall(app: App, start: str, end: str) -> None:
    app.do("add", title="busy", when="fixed", start=start, end=end)


def lock_asks(app: App) -> list[tuple[int | None, str, str | None]]:
    return [(d["pin_id"], d["title"], d["start"]) for d in app.do("status")["decisions"] if d["kind"] == "lock"]


def test_03_a_lock_that_makes_other_work_late_is_kept_and_asked_about_in_the_inbox(app: App) -> None:
    """27 Oct: the plan no longer waits on a lock; it keeps it and the Inbox asks."""
    essay = app.do("add", text="essay due mon 12:00 ~3h one-sitting")["item"]["id"]
    wall(app, "2026-10-19T12:00", "2026-10-19T23:30")
    chore = app.do("add", text="call bank ~1h")["item"]["id"]
    pin = app.full("pin", payload={"id": chore, "start": "2026-10-19T10:00", "end": "2026-10-19T11:00"},
                   provisional=False)  # fmt: skip
    answer = app.do("replan")
    assert answer["status"] == "current" and "call bank" in answer["message"]
    assert plan_blocks(app, chore) == [("2026-10-19T10:00", "2026-10-19T11:00")]  # kept meanwhile
    pin_id = app.table("pins")[0]["id"]
    assert lock_asks(app) == [(pin_id, "Keep call bank where you locked it?", "2026-10-19T10:00")]
    app.do("resolve", unlock_pin_ids=[pin_id])
    assert app.table("pins")[0]["kind"] == "preferred"
    assert app.do("replan")["status"] == "current"
    assert lock_asks(app) == []
    assert plan_blocks(app, essay) == [("2026-10-19T09:00", "2026-10-19T12:00")]
    assert pin.command_id is not None


def test_03b_a_lock_you_keep_isnt_asked_about_again(app: App) -> None:
    app.do("add", text="essay due mon 12:00 ~3h one-sitting")
    wall(app, "2026-10-19T12:00", "2026-10-19T23:30")
    chore = app.do("add", text="call bank ~1h")["item"]["id"]
    app.full("pin", payload={"id": chore, "start": "2026-10-19T10:00", "end": "2026-10-19T11:00"}, provisional=False)
    app.do("replan")
    pin_id = app.table("pins")[0]["id"]
    assert app.do("lock_keep", pin_ids=[pin_id])["message"] == "Kept call bank"
    app.do("replan")
    assert lock_asks(app) == [] and app.table("pins")[0]["kind"] == "locked"
    assert plan_blocks(app, chore) == [("2026-10-19T10:00", "2026-10-19T11:00")]


def test_04_shoving_today_returns_the_must_do_list_and_changes_nothing(app: App) -> None:
    essay = app.do("add", text="essay due tue 09:00 ~8h")["item"]["id"]
    wall(app, "2026-10-20T04:00", "2026-10-20T09:00")
    replan(app.conn, app.now_utc)
    before = state(app)
    answer = app.do("shove", range="day today")
    assert [m["item_id"] for m in answer["must_do"]] == [essay] and answer["created"] == []
    assert answer["must_do"][0]["extra_late_hours"] > 0 and answer["must_do"][0]["planned_hours_in_range"] == 8
    assert state(app) == before


def test_21_a_timer_running_past_its_block_extends_it_and_later_blocks_reflow(app: App) -> None:
    first = app.do("add", text="tidy desk ~1h")["item"]["id"]
    second = app.do("add", text="email ~1h")["item"]["id"]
    wall(app, "2026-10-19T11:30", "2026-10-20T04:00")
    app.do("pin", id=first, start="2026-10-19T09:00", kind="preferred")
    replan(app.conn, app.now_utc)
    assert plan_blocks(app, second)[0][0] == "2026-10-19T10:00"
    app.do("start", id=first)
    app.at("2026-10-19T10:15")
    replan(app.conn, app.now_utc)
    assert ("2026-10-19T10:15", "2026-10-19T10:45") in plan_blocks(app, first)
    assert plan_blocks(app, second)[0][0] >= "2026-10-19T10:45"


def test_22_an_unreviewed_past_block_counts_until_the_review_says_not_done(app: App) -> None:
    essay = app.do("add", text="essay due tue 17:00 ~2h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T09:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(essay) == 8
    app.do("review_submit", entries=[{"block_key": f"T{essay}@2026-10-19T09:00", "status": "not_done"}])
    assert build_input(take_snapshot(app.conn, app.now_utc)).progress_units.get(essay, 0) == 0


def test_24_a_command_then_undo_leaves_the_rows_exactly_as_before(app: App) -> None:
    app.do("add", text="gym every mon,wed ~1h")
    essay = app.do("add", text="essay due wed ~3h")["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T15:00")
    before = state(app)
    edited = app.full("series_edit", payload={"id": 1, "from_date": "2026-10-21", "duration_min": 90},
                      provisional=False)  # fmt: skip
    assert state(app) != before
    app.do("undo", command_id=edited.command_id)
    assert state(app) == before


def test_29_a_pace_for_three_days_ends_on_the_fourth_and_undo_restores_the_earlier_period(app: App) -> None:
    app.do("pace", name="push")
    app.at("2026-10-21T09:00")
    easy = app.full("pace", payload={"name": "easy", "for_days": 3}, provisional=False)
    assert easy.result["end_date"] == "2026-10-23"
    app.at("2026-10-24T09:00")
    assert app.do("paces")["now_label"] == "Normal"
    scales = day_scales(take_snapshot(app.conn, app.now_utc))
    assert scales[0].daily_load_threshold == 1.0
    app.do("undo", command_id=easy.command_id)
    assert app.do("paces")["now_label"] == "Push"
