"""Tracking your sleep: off until you turn it on; taps, corrections, what's offered when, and what's learned."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_local, to_utc
from friday.planner.snapshot import take_snapshot
from friday.planner.solve import prepared_problem
from tests.commands.helpers import TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def on(app: App) -> None:
    app.do("settings_set", key="sleep_tracking", value={"on": True})


def test_it_is_off_until_you_turn_it_on(app: App) -> None:
    assert app.do("sleep") == app.do("sleep") | {"on": False, "nights": [], "next": None}
    with pytest.raises(FieldError, match="sleep tracking is off"):
        app.do("sleep_mark", kind="up")


def test_a_morning_tap_then_ready_then_bed(app: App) -> None:  # it's Monday 9am
    on(app)
    assert app.do("sleep")["next"] == "up"
    assert app.do("sleep_mark", kind="up", at="2026-10-19T08:10")["message"] == "Good morning: 8:10am"
    assert app.do("sleep")["next"] == "ready"
    app.do("sleep_mark", kind="ready")
    out = app.do("sleep")
    assert (out["up"], out["ready"], out["next"]) == ("2026-10-19T08:10", "2026-10-19T09:00", None)
    app.now_utc += 12 * 60 + 30  # 9:30pm, within four hours of an 11:30pm bedtime
    assert app.do("sleep")["next"] == "done"
    assert app.do("sleep_mark", kind="done")["message"] == "Done with work: 9:30pm"
    assert (app.do("sleep")["next"], app.do("sleep")["done"]) == ("bed", "2026-10-19T21:30")
    app.do("sleep_mark", kind="bed")
    assert app.do("sleep")["next"] is None


def test_a_tap_can_be_moved_or_taken_back_but_not_set_in_the_future(app: App) -> None:
    on(app)
    app.do("sleep_mark", kind="up")
    (night,) = app.do("sleep")["nights"]
    app.do("sleep_mark_edit", id=night["up_id"], at="2026-10-19T07:30")
    assert app.do("sleep")["nights"][0]["up"] == "2026-10-19T07:30"
    with pytest.raises(FieldError, match="later than now"):
        app.do("sleep_mark_edit", id=night["up_id"], at="2026-10-19T11:00")
    app.do("sleep_mark_remove", id=night["up_id"])
    assert app.do("sleep")["nights"] == []


def test_weeks_of_late_nights_are_offered_as_a_later_bedtime(app: App) -> None:
    on(app)
    first = date(2026, 10, 19) - timedelta(days=8)
    for n in range(8):
        evening = first + timedelta(days=n)
        morning = evening + timedelta(days=1)
        app.do("sleep_mark", kind="bed", at=f"{morning}T00:50")
        app.do("sleep_mark", kind="up", at=f"{morning}T08:30")
    out = app.do("sleep")
    bedtimes = [c for c in out["changes"] if c["field"] == "bedtime"]
    assert bedtimes and all(c["learned"] == "00:45" for c in bedtimes)
    assert out["suggested"]["tue"]["bedtime"] == "00:45" and out["average_slept_min"] == 7 * 60 + 40
    app.do("settings_set", key="sleep", value=out["suggested"])  # "Use these times"
    assert not [c for c in app.do("sleep")["changes"] if c["field"] == "bedtime"]


def problem_of(app: App):
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input
    from friday.planner.snapshot import take_snapshot

    return build_problem(build_input(take_snapshot(app.conn, app.now_utc)))


def slot_at(problem, local: str) -> int:
    return next(s for s, slot in enumerate(problem.grid.slots) if slot.start_utc == app_utc(problem, local))


def app_utc(problem, local: str) -> int:
    from friday.core.time import parse_local, to_utc

    return to_utc(parse_local(local), problem.grid.spec.timezone)


def test_a_learned_routine_keeps_the_morning_light_for_as_long_as_it_takes(app: App) -> None:
    on(app)
    app.do("add", text="essay ~2h due fri")
    for n in range(5):  # five weekday mornings: up at 7:30, ready at 9
        morning = date(2026, 10, 12) + timedelta(days=n)
        app.do("sleep_mark", kind="up", at=f"{morning}T07:30")
        app.do("sleep_mark", kind="ready", at=f"{morning}T09:00")
    assert app.do("sleep")["routine_min"]["tue"] == 90
    problem = problem_of(app)
    late = next(r for r in problem.rules if r.type == "late_night")
    essay = next(iter(problem.items.values()))
    assert late.price(essay, slot_at(problem, "2026-10-20T08:30")) > 0  # Tuesday 8:30, inside the 90 minutes
    assert late.price(essay, slot_at(problem, "2026-10-20T09:00")) == 0


def test_up_early_frees_the_morning(app: App) -> None:
    on(app)
    app.now_utc -= 3 * 60  # Monday 6am, an hour and a half before the 7:30 wake
    before = problem_of(app)
    assert before.core[slot_at(before, "2026-10-19T06:30")]
    app.do("sleep_mark", kind="up")
    after = problem_of(app)
    assert not after.core[slot_at(after, "2026-10-19T06:30")]


def test_a_short_night_makes_the_next_nights_dearer(app: App) -> None:
    on(app)
    assert problem_of(app).nights[date(2026, 10, 19)].debt_hours == 0
    app.do("sleep_mark", kind="bed", at="2026-10-19T03:00")  # Sunday night: four hours of a seven-hour night
    app.do("sleep_mark", kind="up", at="2026-10-19T07:00")  # (12:30am to 7:30am)
    assert problem_of(app).nights[date(2026, 10, 19)].debt_hours == 3.0


def test_the_brief_offers_an_easy_day_after_a_short_night(app: App) -> None:
    on(app)
    assert app.do("brief")["sleep"] is None
    app.do("sleep_mark", kind="bed", at="2026-10-19T03:00")
    app.do("sleep_mark", kind="up", at="2026-10-19T07:00")
    assert app.do("brief")["sleep"].startswith("You slept 4h last night")


def test_the_review_asks_for_the_taps_you_forgot_and_a_skip_stops_it(app: App) -> None:
    assert app.do("review", date="2026-10-18")["sleep"] == []  # off: nothing asked
    on(app)
    asks = {a["kind"]: a for a in app.do("review", date="2026-10-18")["sleep"]}  # yesterday, Sunday
    assert set(asks) == {"up", "ready", "done", "bed"} and asks["up"]["at"] == "2026-10-18T09:00"  # usual Sunday wake
    assert asks["done"]["at"] == "2026-10-18T23:30"  # an hour before a 12:30am Sunday-night bedtime
    app.do("sleep_mark", kind="up", at="2026-10-18T09:40")
    app.do("sleep_skip", date="2026-10-18", kind="ready")
    assert [a["kind"] for a in app.do("review", date="2026-10-18")["sleep"]] == ["done", "bed"]
    assert [a["kind"] for a in app.do("review")["sleep"]] == ["up", "ready"]  # today: tonight isn't over


def test_done_with_work_is_not_offered_while_a_timer_runs(app: App) -> None:
    on(app)
    app.now_utc += 11 * 60  # 8pm
    chore = app.do("add", text="laundry ~1h")["item"]["id"]
    app.do("start", id=chore)
    assert app.do("sleep")["next"] is None
    app.do("stop")
    assert app.do("sleep")["next"] == "done"


def test_after_done_with_work_nothing_more_is_planned_tonight_unless_it_is_due(app: App) -> None:
    on(app)
    app.now_utc += 11 * 60  # Monday 8pm
    app.do("add", text="reading ~2h due fri 5pm")

    def nine_pm() -> float:  # what an hour of work at 9pm tonight costs
        _, problem, _ = prepared_problem(take_snapshot(app.conn, app.now_utc))
        rule = next(r for r in problem.rules if r.type == "late_night")
        at = to_utc(parse_local("2026-10-19T21:00"), TZ)
        slot = next(s for s in range(problem.grid.S) if problem.grid.slots[s].start_utc == at)
        return rule.price(next(iter(problem.items.values())), slot)

    assert nine_pm() == 0
    app.do("sleep_mark", kind="done")
    assert nine_pm() >= 20  # as an hour past bedtime: only a deadline brings work back
    urgent = app.do("add", title="Quiz corrections", duration_min=45, due="2026-10-19T23:00")["item"]["id"]
    app.do("replan")
    tonight = app.do("plan", start="2026-10-19T20:00", end="2026-10-20T04:00")["blocks"]
    assert any(b["item_id"] == urgent for b in tonight)
    assert all(b["item_id"] == urgent for b in tonight if not b.get("fixed"))


def test_the_wind_down_is_learned_from_done_to_bed(app: App) -> None:
    on(app)
    first = date(2026, 10, 19) - timedelta(days=8)
    for n in range(8):
        evening = first + timedelta(days=n)
        app.do("sleep_mark", kind="done", at=f"{evening}T22:00")
        app.do("sleep_mark", kind="bed", at=f"{evening}T23:15")
    out = app.do("sleep")
    assert out["nights"][0]["wind_down_min"] == 75 and out["nights"][0]["done"].endswith("T22:00")
    assert out["wind_down_min"]["mon"] == 75


def test_a_night_less_than_an_hour_short_offers_nothing(app: App) -> None:
    on(app)
    app.do("sleep_mark", kind="bed", at="2026-10-19T00:45")  # Sunday night: 6h45 of a seven-hour night
    app.do("sleep_mark", kind="up", at="2026-10-19T07:30")
    assert app.do("brief")["sleep"] is None


def test_moving_a_tap_that_isnt_there_says_so(app: App) -> None:
    on(app)
    with pytest.raises(FieldError, match="no sleep mark 99"):
        app.do("sleep_mark_edit", id=99, at="2026-10-19T07:30")


def test_learned_times_that_break_your_sleep_rule_say_so(app: App) -> None:
    on(app)
    app.do("rule_add", text="at least 8 hours of sleep")
    first = date(2026, 10, 19) - timedelta(days=8)
    for n in range(8):
        morning = first + timedelta(days=n + 1)
        app.do("sleep_mark", kind="bed", at=f"{morning}T00:50")
        app.do("sleep_mark", kind="up", at=f"{morning}T08:30")
    out = app.do("sleep")
    assert out["suggested"] and out["against"]
    assert all("under your 8 h rule" in said for said in out["against"])
