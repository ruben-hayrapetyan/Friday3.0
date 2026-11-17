"""Ongoing projects: hours a week with no deadline (commands/ongoing.py, planner/ongoing.py).

Glass box: a priority's share of a pace (budget_factor), a rhythm as pieces (sittings), a short week's carry
(carried_minutes), a goal's first sitting never past its rhythm (compile.first_chunk_units), and a target's most a day
in the checker. Black box through the commands: add, change, pause, resume, delete and the shelf's query. The whole
system, the planner: a rhythm's week in pieces on separate days, a short week carried into the next, and a Goal repeat
made the old way planned as before."""

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from friday.commands.ongoing import sittings
from friday.core.items import FieldError
from friday.core.pace import budget_factor, priority_weight
from friday.core.time import parse_utc, to_local
from friday.engine.compile import first_chunk_units
from friday.engine.problem import EngineItem
from friday.planner.ongoing import ONGOING, carried_minutes, priorities
from friday.planner.service import replan
from friday.planner.store import kv_get
from tests.commands.helpers import TZ, App, new_app

MONDAY = "2026-11-09T09:00"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now=MONDAY, horizon_days=14)


def guitar(app: App, hours: float = 4, **options: object) -> int:
    series = app.do("ongoing_add", title="Guitar", hours_per_week=hours)["id"]
    if options:
        app.do("ongoing_set", id=series, **options)
    return series


def weeks(app: App, series: int) -> list[dict]:
    return sorted((r for r in app.table("items") if r["series_id"] == series), key=lambda r: r["occurrence_date"])


def planned_by_day(app: App, item_id: int) -> dict[str, int]:
    out: Counter[str] = Counter()
    for b in app.table("blocks"):
        if b["item_id"] == item_id:
            day = to_local(parse_utc(b["start_utc"]), TZ).date().isoformat()
            out[day] += parse_utc(b["end_utc"]) - parse_utc(b["start_utc"])
    return dict(out)


# Glass box


def test_the_middle_priority_is_the_pace_as_it_is() -> None:
    for scale in (0.0, 0.5, 1.0, 2.0, 3.0):
        assert budget_factor(scale, priority_weight(3)) == scale
    assert priority_weight(None) == 1.0


def test_a_high_priority_takes_more_of_a_push_and_less_of_a_cut() -> None:
    high, low = priority_weight(5), priority_weight(1)
    assert budget_factor(2.0, high) > 2.0 > budget_factor(2.0, low) > 1.0
    assert budget_factor(0.5, high) > 0.5 > budget_factor(0.5, low) >= 0.0
    assert budget_factor(0.0, low) == 0.0  # an easy week's cut never goes below nothing


def test_a_rhythm_is_the_week_in_that_many_pieces_at_most_one_a_day() -> None:
    four_hours = {"target_units": 16}
    assert sittings(four_hours, 4) == {"daily_ceiling_units": 4, "max_chunk_units": 4, "min_chunk_units": 2}
    assert sittings(four_hours, 3) == {"daily_ceiling_units": 6, "max_chunk_units": 6, "min_chunk_units": 3}
    assert sittings({"target_units": 2}, 7)["min_chunk_units"] == 1  # never longer than a piece
    assert sittings(four_hours, None) == {"daily_ceiling_units": None, "max_chunk_units": None}


def test_a_goals_first_sitting_is_never_past_its_rhythm_or_longest_piece() -> None:
    goal = EngineItem(key="g", amount="target", target=16, min_chunk=2)
    assert first_chunk_units(goal) == 8  # two hours, as a weekly goal opens
    assert first_chunk_units(replace(goal, day_most=4)) == 4  # it was 8: over a day's most, it fit nowhere
    assert first_chunk_units(replace(goal, max_chunk=3)) == 3
    assert first_chunk_units(replace(goal, day_most=1)) == 2  # still its shortest sitting


def test_only_ongoing_projects_carry_and_only_once_their_week_closed(app: App) -> None:
    series = guitar(app)
    plain = app.do("series_add", title="Read", preset="Goal", amount="target", target_min=120, every="week",
                   start_date="2026-11-09")["id"]  # fmt: skip
    first, second = weeks(app, series)[:2]
    assert carried_minutes(app.conn, app.now_utc) == {}  # this week can still be made up
    app.at("2026-11-11T09:00").do("log", id=first["id"], start="2026-11-10T19:00", end="2026-11-10T20:00")
    closed = parse_utc(first["due_utc"]) + 60
    assert carried_minutes(app.conn, closed) == {second["id"]: round(0.5 * (240 - 60))}
    assert not any(r["series_id"] == plain for r in app.table("items") if r["id"] in carried_minutes(app.conn, closed))


def test_a_paused_week_isnt_short(app: App) -> None:
    series = guitar(app)
    first, second = weeks(app, series)[:2]
    app.do("drop", id=first["id"])
    assert carried_minutes(app.conn, parse_utc(first["due_utc"]) + 60) == {}
    assert second["id"]  # still there to plan


def test_priorities_leave_out_the_middle_one(app: App) -> None:
    low, normal = guitar(app, priority=1), guitar(app)
    assert priorities(app.conn) == {low: priority_weight(1)}
    assert normal not in priorities(app.conn)


# Black box, through the commands


def test_added_from_this_weeks_first_day_with_its_hours_a_week(app: App) -> None:
    series = guitar(app, hours=3.5)
    first = weeks(app, series)[0]
    assert first["occurrence_date"] == "2026-11-09" and first["target_units"] == 14 and first["amount"] == "target"
    [shown] = app.do("ongoing_projects")
    assert shown["hours_per_week"] == 3.5 and shown["priority"] == 3 and shown["rhythm_days"] is None
    assert shown["week"]["target_min"] == 210 and shown["week"]["item_id"] == first["id"]


def test_a_change_reaches_this_week_and_the_ones_to_come(app: App) -> None:
    series = guitar(app)
    app.do("ongoing_set", id=series, hours_per_week=2, carry=1, rhythm_days=2, priority=4, title="Bass")
    for week in weeks(app, series):
        assert (week["title"], week["target_units"], week["neglect_carry"], week["daily_ceiling_units"]) == (
            "Bass", 8, 1.0, 4,
        )  # fmt: skip
    [shown] = app.do("ongoing_projects")
    assert (shown["title"], shown["carry"], shown["rhythm_days"], shown["priority"]) == ("Bass", 1.0, 2, 4)
    app.do("ongoing_set", id=series, rhythm_days=0)
    assert {w["daily_ceiling_units"] for w in weeks(app, series)} == {None}
    assert app.do("ongoing_projects")[0]["rhythm_days"] is None


def test_paused_until_a_date_and_back_that_morning(app: App) -> None:
    series = guitar(app)
    with pytest.raises(FieldError, match="after today"):
        app.do("ongoing_set", id=series, paused_until="2026-11-09")
    app.do("ongoing_set", id=series, paused_until="2026-11-23")
    [shown] = app.do("ongoing_projects")
    assert not shown["active"] and shown["week"] is None and shown["paused_until"] == "2026-11-23"
    app.at("2026-11-23T05:00").do("materialize")  # the nightly job, that morning
    [shown] = app.do("ongoing_projects")
    assert shown["active"] and shown["paused_until"] is None and shown["week"]["start"].startswith("2026-11-23")


def test_paused_and_resumed_now(app: App) -> None:
    series = guitar(app)
    app.do("series_stop", id=series)
    assert not app.do("ongoing_projects")[0]["active"]
    app.do("ongoing_set", id=series, paused_until="")
    assert app.do("ongoing_projects")[0]["active"]


def test_deleted_its_weeks_to_come_go_and_the_hours_stay(app: App) -> None:
    series = guitar(app)
    first = weeks(app, series)[0]
    app.do("log", id=first["id"], start="2026-11-09T07:00", end="2026-11-09T08:00")
    app.do("ongoing_delete", id=series)
    assert app.do("ongoing_projects") == []
    assert str(series) not in (kv_get(app.conn, ONGOING, {}) or {})
    assert sum(r["minutes"] for r in app.table("progress")) == 60


def test_a_repeat_that_isnt_a_weekly_goal_is_refused(app: App) -> None:
    daily = app.do("series_add", title="Stretch", preset="Habit", every="day")["id"]
    monthly = app.do("series_add", title="Budget", preset="Goal", amount="target", target_min=120, every="month")["id"]
    for other in (daily, monthly):
        with pytest.raises(FieldError, match="isn't an ongoing project"):
            app.do("ongoing_set", id=other, hours_per_week=3)
    assert app.do("ongoing_projects") == []


# A weekly goal made before 0.5.0 (or as a repeating Goal elsewhere): on the shelf, planned as before (16 Nov: "Show
# them, plan unchanged")


def old_goal(app: App) -> int:
    return app.do("series_add", title="Read", preset="Goal", amount="target", target_min=120, every="week")["id"]


def test_a_weekly_goal_made_the_old_way_is_on_the_shelf_marked_as_before(app: App) -> None:
    plain = old_goal(app)
    [shown] = app.do("ongoing_projects")
    assert (shown["id"], shown["title"], shown["hours_per_week"], shown["as_before"]) == (plain, "Read", 2, True)
    assert shown["active"] and shown["week"] is not None and shown["priority"] == 3


def current_blocks(app: App) -> list[tuple[int, str, str]]:
    plan_id = max(b["plan_id"] for b in app.table("blocks"))
    return sorted((b["item_id"], b["start_utc"], b["end_utc"]) for b in app.table("blocks") if b["plan_id"] == plan_id)


def test_listing_it_changes_nothing_the_planner_reads(app: App) -> None:
    plain = old_goal(app)
    replan(app.conn, app.now_utc)
    before = current_blocks(app)
    assert any(item in {r["id"] for r in weeks(app, plain)} for item, _, _ in before)  # its week is planned
    app.do("ongoing_projects")
    assert kv_get(app.conn, ONGOING, {}) in ({}, None)  # a query writes nothing
    assert plain not in priorities(app.conn) and carried_minutes(app.conn, app.now_utc) == {}
    replan(app.conn, app.now_utc)
    assert current_blocks(app) == before


def test_a_setting_changed_on_the_shelf_makes_it_an_ongoing_project(app: App) -> None:
    plain = old_goal(app)
    app.do("ongoing_set", id=plain, priority=4)
    [shown] = app.do("ongoing_projects")
    assert (shown["as_before"], shown["priority"]) == (False, 4)
    assert kv_get(app.conn, ONGOING, {})[str(plain)]["priority"] == 4
    assert priorities(app.conn) == {plain: priority_weight(4)}


def test_paused_until_resumed_it_stays_on_the_shelf(app: App) -> None:
    plain = old_goal(app)
    app.do("ongoing_set", id=plain, paused_until="resume")
    [shown] = app.do("ongoing_projects")
    assert (shown["active"], shown["paused_until"], shown["week"], shown["as_before"]) == (False, None, None, False)
    app.do("ongoing_set", id=plain, paused_until="")
    assert app.do("ongoing_projects")[0]["active"]


def test_an_old_goal_stopped_before_isnt_brought_back(app: App) -> None:
    plain = old_goal(app)
    app.do("series_stop", id=plain)
    assert app.do("ongoing_projects") == []


def test_an_old_goal_can_be_deleted_from_the_shelf(app: App) -> None:
    plain = old_goal(app)
    app.do("ongoing_delete", id=plain)
    assert app.do("ongoing_projects") == []
    assert not any(r["series_id"] == plain and r["status"] == "todo" for r in app.table("items"))


def test_the_shelf_shows_the_weeks_before_and_the_days_touched(app: App) -> None:
    series = guitar(app)
    first = weeks(app, series)[0]
    app.at("2026-11-11T09:00").do("log", id=first["id"], start="2026-11-10T19:00", end="2026-11-10T20:30")
    later = app.at("2026-11-17T09:00")
    [shown] = later.do("ongoing_projects")
    assert [w["done_min"] for w in shown["past"]] == [90]
    assert shown["week"]["carried_min"] == round(0.5 * (240 - 90))  # half of the short week, carried
    assert shown["week"]["target_min"] == 240 + shown["week"]["carried_min"]
    assert shown["touched"] == ["2026-11-10"]


def test_priority_and_pace_make_this_weeks_aim(app: App) -> None:
    series = guitar(app, priority=5)
    app.do("pace", name="Push")
    [shown] = app.do("ongoing_projects")
    assert shown["aim_min"] == round(240 * budget_factor(2.0, priority_weight(5)))
    app.do("ongoing_set", id=series, priority=3)
    assert app.do("ongoing_projects")[0]["aim_min"] == 480  # Push doubles a budget, as it does any Goal's


# The whole system, the planner


def test_a_rhythm_plans_its_week_in_pieces_on_separate_days(app: App) -> None:
    series = guitar(app, rhythm_days=4)
    replan(app.conn, app.now_utc)
    days = planned_by_day(app, weeks(app, series)[0]["id"])
    # An hour a day at most, on days apart. Before first_chunk_units kept to it, a weekly goal opened at two hours, over
    # the day's most, and nothing was planned at all.
    assert len(days) >= 2 and max(days.values()) <= 60


def test_without_a_rhythm_a_day_may_hold_more(app: App) -> None:
    series = guitar(app, hours=2)
    replan(app.conn, app.now_utc)
    days = planned_by_day(app, weeks(app, series)[0]["id"])
    assert days and max(days.values()) > 60  # no rhythm: more than a 2-days-a-week piece in one sitting


def test_a_short_week_carries_into_the_plan_of_the_next(app: App) -> None:
    series = guitar(app, hours=2, carry=1)
    later = app.at("2026-11-16T09:00")  # the first week went by with nothing done
    replan(later.conn, later.now_utc)
    from friday.planner.prepare import build_input
    from friday.planner.snapshot import take_snapshot

    second = weeks(app, series)[1]
    inp = build_input(take_snapshot(later.conn, later.now_utc))
    assert inp.carried_units == {second["id"]: 8}  # the two hours missed, all of them


def test_an_ongoing_projects_week_isnt_called_slipping_but_a_plain_goals_still_is(tmp_path: Path) -> None:
    # Late on Sunday night: this week's hours can't be planned before the week closes. An ongoing project's short week
    # carries into the next, so the header mustn't say it "isn't planned before it's due"; a Goal repeat made the old
    # way says so as before.
    app = new_app(tmp_path, now="2026-11-15T23:30", horizon_days=14)
    guitar(app)
    app.do("series_add", title="Read", preset="Goal", amount="target", target_min=120, every="week",
           start_date="2026-11-09")  # fmt: skip
    replan(app.conn, app.now_utc)
    slipping = {s["title"] for s in app.do("status")["slipping"]}
    assert "Guitar" not in slipping
    assert "Read" in slipping
