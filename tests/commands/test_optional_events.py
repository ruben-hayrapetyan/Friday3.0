"""Optional events the plan gives to work (27 Oct: tasks went over gym and climbing club, which stayed on the calendar
as if you were going, a bad overlay). The plan view says which work takes an optional event's time, so the calendar
draws it as skipped; once the plan gives an event to work, all of its time is work's (a second pass), not a corner of
it; and "Go anyway" (`event_keep`) walls one occurrence off, until you leave it to Friday again."""

from dataclasses import replace
from pathlib import Path

import pytest

from friday.core.time import parse_local, to_utc
from friday.engine.rules.prices import Skippable
from friday.planner.build import build_problem, key_of
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from friday.planner.solve import given_to_work, prepared_problem, solve, with_kept
from tests.commands.helpers import TZ, App, new_app

GYM = ("2026-10-19T12:00", "2026-10-19T13:30")


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=3)
    app.do("rule_add", text="gym is optional")
    return app


def gym(app: App) -> int:
    return app.do("add", title="Gym", when="fixed", start=GYM[0], end=GYM[1])["item"]["id"]


def shown(app: App, item_id: int) -> dict:
    (found,) = [f for f in app.do("plan")["fixed"] if f["id"] == item_id]
    return found


def over_gym(app: App, item_id: int) -> list[tuple[str, str]]:
    return [(b["start"], b["end"]) for b in app.do("plan")["blocks"]
            if b["item_id"] == item_id and b["start"] < GYM[1] and b["end"] > GYM[0]]  # fmt: skip


def test_an_optional_event_left_alone_says_so(app: App) -> None:
    event = gym(app)
    app.do("add", text="reading due fri ~1h")
    replan(app.conn, app.now_utc)
    found = shown(app, event)
    assert found["optional"] and not found["gives_way_to"] and not found["going"]


def test_an_optional_event_work_needs_is_drawn_as_skipped_for_that_work(app: App) -> None:
    event = gym(app)
    essay = app.do("add", text="essay due mon 17:00 ~7h")["item"]["id"]  # 8 hours to 5pm, less 1h30 of gym
    replan(app.conn, app.now_utc)
    assert over_gym(app, essay), "the work needs the gym's time"
    assert shown(app, event)["gives_way_to"] == "essay"


def test_given_to_work_all_of_its_time_is_works(app: App) -> None:
    gym(app)
    app.do("add", text="essay due mon 17:00 ~7h")
    solved = solve(take_snapshot(app.conn, app.now_utc), warm=False)
    (rule,) = [r for r in solved.problem.rules if isinstance(r, Skippable)]
    assert to_utc(parse_local(GYM[0]), TZ) in rule.p.given  # its time costs nothing more: skipped either way
    assert not rule.covered.any()


def test_go_anyway_keeps_work_off_it_until_left_to_friday(app: App) -> None:
    event = gym(app)
    essay = app.do("add", text="essay due mon 17:00 ~7h")["item"]["id"]
    replan(app.conn, app.now_utc)
    assert over_gym(app, essay)
    app.do("event_keep", id=event, going=True)
    replan(app.conn, app.now_utc)
    assert not over_gym(app, essay)
    found = shown(app, event)
    assert found["going"] and not found["gives_way_to"]
    app.do("event_keep", id=event, going=False)
    replan(app.conn, app.now_utc)
    assert over_gym(app, essay)
    assert not shown(app, event)["going"]


def test_a_corner_of_an_event_is_told_from_most_of_it(app: App) -> None:
    gym(app)
    essay = app.do("add", text="essay due wed ~4h")["item"]["id"]
    _, problem, _ = prepared_problem(take_snapshot(app.conn, app.now_utc))
    lo, hi = (to_utc(parse_local(t), TZ) for t in GYM)
    inside = problem.grid.slots_overlapping(lo, hi)
    corner = {key_of(essay): (inside[0],)}  # a quarter hour of the gym's hour and a half
    most = {key_of(essay): tuple(inside[:4])}
    given, corners = given_to_work(problem, corner)
    (name,) = given
    assert given == {name: {lo}} and corners == {name: {lo}}
    given, corners = given_to_work(problem, most)
    assert lo in next(iter(given.values())) and not corners


def test_a_kept_event_is_walled_off(app: App) -> None:
    gym(app)
    app.do("add", text="essay due wed ~4h")
    inp, _, _ = prepared_problem(take_snapshot(app.conn, app.now_utc))
    lo, hi = (to_utc(parse_local(t), TZ) for t in GYM)
    (rule,) = [r for r in inp.settings["rules"] if r.type == "skippable"]
    walled = with_kept(inp.settings["rules"], {rule.name: {lo}})
    problem = build_problem(replace(inp, settings=inp.settings | {"rules": walled}))
    inside = set(problem.grid.slots_overlapping(lo, hi))
    (item,) = problem.items.values()
    assert not inside & set(item.allowed)
