"""Setup: the questions Friday asks when it first opens. They start from what Friday does now, and each answer sets
what it's about, in one change you can undo."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from friday.commands.fetching import sync
from friday.commands.setup import tuned
from friday.core.settings import REFERENCE_RULES
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import SINCE, UNTIL, calendar, mac_event


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # weekdays 07:30 to 23:30, weekends 09:00 to 00:30


def answers(app: App, **change: Any) -> dict[str, Any]:
    return app.do("setup")["answers"] | change


def settings(app: App) -> dict[str, Any]:
    return take_snapshot(app.conn, app.now_utc).settings


def rule(app: App, name: str) -> Any:
    return next(r for r in settings(app)["rules"] if r.name == name)


def test_the_questions_start_from_what_friday_does_now(app: App) -> None:
    out = app.do("setup")
    assert out["done"] is False
    assert out["answers"] == {
        "wake": "07:30",
        "bedtime": "23:30",
        "weekend_wake": "09:00",
        "weekend_bedtime": "23:30",  # Friday night is a weekday's in the test week
        "normal_hours": 8.0,
        "most_hours": 10.0,
        "focus_hours": 3.0,
        "evening_free": 2.0,
        "evening_from": "18:00",
        "weekend_free": 4.0,
        "finish_early_days": 1,
        "brief": True,
        "calendars": [],
    }


def test_answers_set_sleep_load_focus_free_time_and_the_brief(app: App) -> None:
    app.do(
        "setup_save",
        **answers(
            app,
            wake="08:00",
            bedtime="00:30",
            weekend_wake="10:30",
            weekend_bedtime="02:00",
            normal_hours=5,
            most_hours=7.5,
            focus_hours=1.5,
            evening_free=3,
            evening_from="19:00",
            weekend_free=6,
            finish_early_days=2,
            brief=False,
        ),
    )
    s = settings(app)
    assert {d: (s["sleep"][d].wake, s["sleep"][d].bedtime) for d in ("mon", "thu", "fri", "sat", "sun")} == {
        "mon": ("08:00", "00:30"),
        "thu": ("08:00", "00:30"),
        "fri": ("08:00", "02:00"),  # Friday night is the weekend's, Friday morning isn't
        "sat": ("10:30", "02:00"),
        "sun": ("10:30", "00:30"),
    }
    assert s["sleep"]["mon"].margin_min == 60  # what wasn't asked stays
    assert set(s["daily_cap"].values()) == {7.5}
    assert rule(app, "daily_load").params["threshold"] == "5h"
    assert rule(app, "deep_run").params["threshold"] == "1.5h"
    evenings = rule(app, "weekday_evenings").params
    assert (evenings["start"], evenings["end"], evenings["free"]) == ("19:00", "23:00", "3h")
    assert rule(app, "weekends").params["free"] == "6h"
    assert rule(app, "finish_early").params["days"] == 2
    assert s["notify"].types["morning_brief"] is False
    assert s["notify"].types["evening_review"] is True
    out = app.do("setup")
    assert out["done"] is True
    assert out["answers"]["focus_hours"] == 1.5 and out["answers"]["weekend_bedtime"] == "02:00"


def test_none_of_it_switches_a_rule_off_and_some_switches_it_back_on(app: App) -> None:
    app.do("setup_save", **answers(app, evening_free=0, weekend_free=0, finish_early_days=0))
    assert not rule(app, "weekday_evenings").enabled and not rule(app, "weekends").enabled
    assert not rule(app, "finish_early").enabled
    assert rule(app, "weekday_evenings").params["free"] == "2h"  # kept for when it's back
    assert answers(app)["evening_free"] == 0 and answers(app)["finish_early_days"] == 0
    app.do("setup_save", **answers(app, evening_free=1, finish_early_days=1))
    assert rule(app, "weekday_evenings").enabled and rule(app, "weekday_evenings").params["free"] == "1h"
    assert rule(app, "finish_early").enabled and not rule(app, "weekends").enabled


def test_a_heavy_day_is_never_less_than_a_normal_one(app: App) -> None:
    app.do("setup_save", **answers(app, normal_hours=9, most_hours=6))
    assert set(settings(app)["daily_cap"].values()) == {9}


def test_your_calendars_shown_or_hidden_and_counted_or_not(app: App) -> None:
    home, rooms, work = calendar("home", "Home"), calendar("rooms", "Library Rooms"), calendar("work", "Work")
    app.do(
        "mac_sync",
        calendars=[home, rooms, work],
        events=[
            mac_event("a", "home", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00"),
            mac_event("b", "home", "Haircut", "2026-10-21T10:00", "2026-10-21T11:00"),
            mac_event("c", "rooms", "Room 3", "2026-10-22T10:00", "2026-10-22T11:00"),
            mac_event("d", "home", "Next month", "2026-11-20T10:00", "2026-11-20T11:00"),  # past two weeks
        ],
        since=SINCE,
        until=UNTIL,
    )
    sync(app.conn, app.now_utc)
    out = app.do("setup")
    assert out["events"] == {"Home": 2, "Library Rooms": 1}
    assert out["answers"]["calendars"] == [  # most events first; room bookings start out not counted
        {"name": "Home", "shown": True, "busy": True},
        {"name": "Library Rooms", "shown": True, "busy": False},
        {"name": "Work", "shown": True, "busy": True},
    ]
    app.do("settings_set", key="calendar_look", value={"toolbar": ["Old feed"]})
    picked = [
        {"name": "Home", "shown": False, "busy": False},
        {"name": "Library Rooms", "shown": False, "busy": False},
        {"name": "Work", "shown": True, "busy": True},
    ]
    app.do("setup_save", **answers(app, calendars=picked))
    s = settings(app)
    assert list(s["calendar_look"].toolbar) == ["Old feed", "Home", "Library Rooms"]  # one not asked about stays
    assert s["busy"].calendars == {"Home": False, "Library Rooms": False, "Work": True}
    assert answers(app)["calendars"] == picked
    app.do("setup_save", **answers(app, calendars=[{"name": "Home", "shown": True, "busy": True}]))
    assert list(settings(app)["calendar_look"].toolbar) == ["Old feed", "Library Rooms"]


def test_one_undo_takes_back_every_answer(app: App) -> None:
    before = settings(app)
    said = app.full("setup_save", payload=answers(app, wake="06:00", focus_hours=1, brief=False), provisional=False)
    app.do("undo", command_id=said.command_id)
    after = settings(app)
    assert after["sleep"] == before["sleep"] and after["rules"] == before["rules"]
    assert after["notify"] == before["notify"] and after["daily_cap"] == before["daily_cap"]
    assert app.do("setup")["done"] is False


def test_a_removed_built_in_rule_comes_back_when_an_answer_needs_it() -> None:
    without = [r for r in REFERENCE_RULES if r.name != "weekends"]
    assert tuned(without, "weekends", {"free": "0h"}, enabled=False) == without
    back = next(r for r in tuned(without, "weekends", {"free": "3h"}) if r.name == "weekends")
    assert back.enabled and back.params["free"] == "3h" and back.params["start"] == "10:00"


def test_answers_out_of_range_are_refused(app: App) -> None:
    with pytest.raises(ValidationError):
        app.do("setup_save", **answers(app, normal_hours=0))
    with pytest.raises(ValidationError):
        app.do("setup_save", **answers(app, wake="7am"))
    assert app.do("setup")["done"] is False
