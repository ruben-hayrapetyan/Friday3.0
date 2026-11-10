"""Other ways are made afresh (C89; the system test had failed since C64): a way, its pick and "Which should win?"
let go of where your blocks are. Held there before (minimize_changes, in the wellbeing stage, above every
preference), no reweighing could move them: on a roomy week every seed came out as your plan, or a way paid in
wellbeing for each hour it moved and looked worse than it was. Your pins and what you're timing still hold."""

import dataclasses
from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.planner.prepare import build_input
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from friday.planner.views import other_way, signature
from tests.commands.helpers import App, new_app

MONDAY = date(2026, 10, 19)


@pytest.fixture
def app(tmp_path: Path) -> App:
    """The system test's week (tests/system/test_one_way_system.py): five 5-hour essays and three readings."""
    app = new_app(tmp_path, horizon_days=14)
    for n in range(1, 6):
        app.do("add", title=f"Essay {n}", preset="Assignment", due=f"{MONDAY + timedelta(days=n + 2)}T23:59",
               duration_min=300)  # fmt: skip
    for n in range(1, 4):
        app.do("add", title=f"Reading {n}", preset="Reading", due=f"{MONDAY + timedelta(days=n + 1)}T23:59",
               duration_min=90)  # fmt: skip
    replan(app.conn, app.now_utc)
    return app


def blocks(app: App) -> set[tuple[int, str]]:
    return {(b["item_id"], b["start"]) for b in app.do("plan")["blocks"] if b["item_id"]}


# Glass box: what the planner is given


def test_a_plan_made_afresh_holds_none_of_your_blocks_where_they_are(app: App) -> None:
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    assert build_input(snapshot).minimize_changes_scale == 1.0  # an ordinary replan keeps your plan
    afresh = dataclasses.replace(snapshot, cold_once=True)
    assert build_input(afresh).minimize_changes_scale == 0.0
    assert build_input(afresh).current == build_input(snapshot).current  # still known, just not held


def test_a_rule_change_s_loosening_still_applies_when_not_made_afresh(app: App) -> None:
    snapshot = dataclasses.replace(take_snapshot(app.conn, app.now_utc, 1), next_stability=0.3)
    assert build_input(snapshot).minimize_changes_scale == 0.3


def test_a_preferred_pin_still_holds_in_a_way(app: App) -> None:
    """A lock can't move anyway; a preferred pin is held by the same rule, by its own part (×10), which stays."""
    essay = next(b for b in app.do("plan")["blocks"] if b["title"] == "Essay 1")
    app.do("pin", id=essay["item_id"], start=essay["start"], end=essay["end"], kind="preferred")
    replan(app.conn, app.now_utc)
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    for seed in (1, 2, 3):
        _, plan = other_way(snapshot, seed)
        held = [b for b in plan.blocks if b.item_id == essay["item_id"]]
        assert any(b.start_utc <= snapshot.pins[0].start_utc and b.end_utc >= snapshot.pins[0].end_utc for b in held)


# Black box: what you see


def test_every_seed_on_a_roomy_week_is_a_way_of_its_own_and_none_is_worse_on_deadlines_or_wellbeing(app: App) -> None:
    mine = app.do("plan")["blocks"]
    snapshot = take_snapshot(app.conn, app.now_utc, 1)
    found = [other_way(snapshot, seed)[1] for seed in range(1, 7)]
    assert all(signature(p.blocks) != signature(snapshot.plan_blocks) for p in found)
    assert len({signature(p.blocks) for p in found}) >= 2
    assert all(p.report["stage_values"]["deadlines"] == 0 and p.report["stage_values"]["wellbeing"] == 0 for p in found)
    assert sum(b["end"] > b["start"] for b in mine) and all(p.blocks for p in found)


def test_the_dialog_finds_two_ways_and_the_one_picked_becomes_the_plan(app: App) -> None:
    ways = [w for seed in range(1, 7) if (w := app.do("other_way", seed=seed)["way"])]
    assert len({w["signature"] for w in ways}) >= 2
    way = ways[0]
    app.do("other_way_pick", weights=way["weights"], seed=way["seed"], rule_totals=way["rule_totals"])
    replan(app.conn, app.now_utc)
    assert blocks(app) == {(b["item_id"], b["start"]) for b in way["blocks"]}


def test_after_the_pick_your_plan_is_held_again(app: App) -> None:
    way = next(w for seed in range(1, 7) if (w := app.do("other_way", seed=seed)["way"]))
    app.do("other_way_pick", weights=way["weights"], seed=way["seed"], rule_totals=way["rule_totals"])
    replan(app.conn, app.now_utc)
    picked = blocks(app)
    replan(app.conn, app.now_utc + 15)  # an ordinary replan a quarter-hour on: nothing changed, so the pick stands
    assert len(blocks(app) & picked) >= 0.9 * len(picked)
