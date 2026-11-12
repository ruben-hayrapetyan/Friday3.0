"""The planner's edges, through the commands where it can be: a project's step due with its project, work after an
event, a step of a finished project, learned weights switched off or moved by the state units, a plan older than the
one saved, a database without sleep times, a lock that isn't what makes work late, a pace that can't keep a day
light, and a timer on open-ended work. Monday 19 Oct 2026, 9am."""

import json
from pathlib import Path

import pytest

from friday.core.db import connect
from friday.core.time import parse_local, to_utc
from friday.planner.build import build_problem, key_of, nights
from friday.planner.prepare import build_input, debt_hours
from friday.planner.service import plan_snapshot, provisional, replan, save_plan
from friday.planner.snapshot import take_snapshot
from friday.planner.store import current_plan
from friday.planner.views import now_view
from tests.commands.helpers import MONDAY_9, TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def blocks(app: App, title: str) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"] if b["title"] == title]


def report(app: App) -> dict:
    return json.loads(current_plan(app.conn)["report"])


def due_planned(app: App, item_id: int) -> int | None:
    return build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items[key_of(item_id)].due_utc


def test_a_step_with_no_due_of_its_own_is_due_with_its_project(app: App) -> None:
    thesis = app.do("add", title="Thesis", due="2026-10-21T17:00", duration_min=60)["item"]["id"]
    outline = app.do("add", title="Outline", duration_min=60, parent_id=thesis)["item"]["id"]
    assert app.do("item", id=outline)["item"]["due"] is None
    assert due_planned(app, outline) == to_utc(parse_local("2026-10-21T17:00"), TZ)


def test_work_that_waits_for_an_event_starts_after_it_and_its_lag(app: App) -> None:
    talk = app.do("add", title="Talk", when="fixed", start="2026-10-19T14:00", end="2026-10-19T16:00")["item"]["id"]
    notes = app.do("add", title="Write up notes", duration_min=60, due="2026-10-20T20:00")["item"]["id"]
    app.do("depend", item_id=notes, depends_on_id=talk, lag_min=30)
    replan(app.conn, app.now_utc)
    (start, _), *_ = blocks(app, "Write up notes")
    assert start >= "2026-10-19T16:30"


def test_a_step_of_a_project_you_marked_done_is_still_planned(app: App) -> None:
    thesis = app.do("add", title="Thesis", due="2026-10-21T17:00", duration_min=60)["item"]["id"]
    app.do("add", title="Outline", duration_min=60, parent_id=thesis)
    app.do("done", id=thesis)
    snapshot = take_snapshot(app.conn, app.now_utc)
    assert {i.title: i.status for i in snapshot.items} == {"Thesis": "done", "Outline": "todo"}
    replan(app.conn, app.now_utc)
    assert blocks(app, "Outline")


def active_profile(app: App, theta: dict[str, float], state: dict | None) -> None:
    app.conn.execute(
        "INSERT INTO learned_profile (version, created_utc, theta, state, proposals, wall_decisions, evidence, status) "
        "VALUES (1, 'x', ?, ?, '{}', '{}', '{}', 'active')",
        [json.dumps(theta), json.dumps(state) if state else None],
    )
    app.conn.commit()


def test_learned_weights_switched_off_are_not_planned_with(app: App) -> None:
    active_profile(app, {"late_night": 1.4}, None)
    assert take_snapshot(app.conn, app.now_utc).multipliers == {"late_night": 1.4}
    app.do("settings_set", key="learn", value={"weights": "off"})
    snapshot = take_snapshot(app.conn, app.now_utc)
    assert snapshot.multipliers == {} and snapshot.profile_version == 0


def test_with_its_gate_open_the_state_units_move_the_learned_weights_unless_a_pace_is_picked(app: App) -> None:
    tired = {"h": [-1.0, 1.0, 0.0, -1.0], "on": True}  # less capacity, more rest
    active_profile(app, {"late_night": 1.0, "daily_load": 1.0, "even_load": 1.0}, tired)
    app.do("settings_set", key="learn", value={"state_inference": "on"})
    moved = take_snapshot(app.conn, app.now_utc).multipliers
    assert moved["late_night"] > 1.0 and moved["daily_load"] > 1.0 and moved["even_load"] == 1.0
    app.do("pace", name="easy")
    assert set(take_snapshot(app.conn, app.now_utc).multipliers.values()) == {1.0}


def test_a_plan_older_than_the_one_saved_is_not_saved(app: App) -> None:
    app.do("add", title="Essay", due="2026-10-21T17:00", duration_min=120)
    old = take_snapshot(app.conn, app.now_utc)
    planned = plan_snapshot(old, warm=True)
    app.do("add", title="Reading", due="2026-10-21T17:00", duration_min=60)
    newer = replan(app.conn, app.now_utc)
    assert save_plan(app.conn, old, planned, "replan") is None
    assert current_plan(app.conn)["id"] == newer


def test_a_save_that_fails_halfway_leaves_no_plan_and_no_open_transaction(app: App) -> None:
    app.do("add", title="Essay", due="2026-10-21T17:00", duration_min=120)
    snapshot = take_snapshot(app.conn, app.now_utc)
    with pytest.raises(AttributeError):
        save_plan(app.conn, snapshot, object(), "replan")  # type: ignore[arg-type]
    assert not app.conn.in_transaction and current_plan(app.conn) is None


def test_a_replan_a_newer_plan_beat_says_it_was_skipped(app: App) -> None:
    out = app.full("replan", provisional=False, solver=lambda reason: None)
    assert (out.result["status"], out.result["message"]) == ("skipped", "A newer plan was already saved")


@pytest.fixture
def no_sleep(tmp_path: Path) -> App:
    """Set up as far as the timezone: before `fridayd init` asks your sleep times."""
    conn = connect(tmp_path / "friday.db")
    fresh = App(conn, to_utc(parse_local(MONDAY_9), TZ))
    fresh.do("settings_set", key="time", value={"timezone": TZ, "horizon_days": 7})
    return fresh


def test_without_sleep_times_nothing_is_placed_at_once(no_sleep: App) -> None:
    out = no_sleep.full("add", payload={"title": "Essay", "duration_min": 60}, provisional=True)
    assert out.command_id and out.provisional is None
    assert provisional(no_sleep.conn, no_sleep.now_utc, 1, set()) is None


def test_without_sleep_times_there_are_no_nights_or_sleep_debt(no_sleep: App) -> None:
    snapshot = take_snapshot(no_sleep.conn, no_sleep.now_utc)
    assert debt_hours(snapshot) == {}
    with pytest.raises(ValueError, match="sleep: not set yet"):
        nights(build_input(snapshot), None, None, 1)  # type: ignore[arg-type]


def test_the_quick_placement_is_kept_as_ghosts_once_set_up(app: App) -> None:
    essay = app.do("add", title="Essay", due="2026-10-20T17:00", duration_min=60)["item"]["id"]
    ghosts = provisional(app.conn, app.now_utc, 1, {essay})
    assert ghosts and {g.title for g in ghosts} == {"Essay"}


def test_a_lock_that_isnt_what_makes_work_late_is_not_asked_about(app: App) -> None:
    app.do("add", title="Essay", due="2026-10-19T10:00", duration_min=180)  # late whatever happens
    reading = app.do("add", title="Reading", due="2026-10-23T17:00", duration_min=60)["item"]["id"]
    app.do("pin", id=reading, start="2026-10-22T14:00", kind="locked")
    replan(app.conn, app.now_utc)
    assert report(app).get("conflicts", []) == []


def test_a_lighter_pace_that_cant_keep_a_day_under_its_limit_says_what_is_due(app: App) -> None:
    app.do("pace", name="easy")
    app.do("add", title="Essay", due="2026-10-19T23:00", duration_min=420, preset="Assignment")
    replan(app.conn, app.now_utc)
    assert report(app)["pace_notices"] == ["Easy pace can't keep Mon under 4.8 h: Essay is due"]


def test_a_timer_on_open_ended_work_holds_nothing_back(app: App) -> None:
    piano = app.do("add", title="Practice piano", amount="open")["item"]["id"]
    app.do("start", id=piano)
    app.at("2026-10-19T10:00")
    replan(app.conn, app.now_utc)
    state, _ = now_view(take_snapshot(app.conn, app.now_utc))
    assert state.problem.items[key_of(piano)].amount == "open"
    assert blocks(app, "Practice piano")
