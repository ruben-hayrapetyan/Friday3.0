"""Naps and snacks (29 Oct: "add functionality for adding naps (same with snacks in the meal section)"): a nap tapped
or logged after the fact, put right or taken back; the plan kept clear while you nap or snack; how long you usually
nap; a nap paying back the night before. Monday 2026-10-19, 9am; nights 11:30pm to 7:30am."""

from datetime import date
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.core.time import parse_local, to_utc
from friday.planner.build import build_problem
from friday.planner.prepare import build_input
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import TZ, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="sleep_tracking", value={"on": True})
    return app


def utc(local: str) -> int:
    return to_utc(parse_local(local), TZ)


def naps(app: App) -> list[tuple[str, str | None, int | None]]:
    return [(n["start"], n["end"], n["minutes"]) for n in app.do("sleep")["naps"]]


def three_naps(app: App, minutes: int = 20) -> None:
    for day in (14, 15, 16):
        app.do("nap_log", start=f"2026-10-{day}T15:00", end=f"2026-10-{day}T15:{minutes:02d}")


def test_naps_need_sleep_tracking(tmp_path: Path) -> None:
    with pytest.raises(FieldError, match="sleep tracking is off"):
        new_app(tmp_path).do("nap_start")


def test_taking_a_nap_then_up(app: App) -> None:
    app.at("2026-10-19T14:10")
    assert app.do("nap_start")["message"] == "Napping since 2:10pm"
    out = app.do("sleep")
    assert out["napping"]["start"] == "2026-10-19T14:10" and out["next"] is None  # no other tap while you nap
    with pytest.raises(FieldError, match="napping since 2:10pm"):
        app.do("nap_start")
    app.at("2026-10-19T14:35")
    assert app.do("nap_end")["message"] == "Nap: 25 min"
    out = app.do("sleep")
    assert out["napping"] is None and naps(app) == [("2026-10-19T14:10", "2026-10-19T14:35", 25)]
    with pytest.raises(FieldError, match="aren't napping"):
        app.do("nap_end")


def test_up_tapped_hours_later_counts_your_usual_nap(app: App) -> None:
    three_naps(app)
    assert app.do("sleep")["usual_nap_min"] == 20
    app.at("2026-10-19T13:00")
    app.do("nap_start")
    app.at("2026-10-19T17:30")
    assert app.do("nap_end")["message"].startswith("Nap: counted as your usual 20 min")
    assert naps(app)[0] == ("2026-10-19T13:00", "2026-10-19T13:20", 20)


def test_half_an_hour_until_three_naps_say_otherwise(app: App) -> None:
    app.do("nap_log", start="2026-10-18T15:00", end="2026-10-18T15:20")
    assert app.do("sleep")["usual_nap_min"] is None
    app.at("2026-10-19T13:00")
    app.do("nap_start")
    assert take_snapshot(app.conn, app.now_utc).away == ("Nap", utc("2026-10-19T13:00"), utc("2026-10-19T13:30"))


def test_going_to_bed_ends_a_nap_left_running(app: App) -> None:
    app.at("2026-10-19T22:00")
    app.do("nap_start")
    app.at("2026-10-19T23:40")
    app.do("sleep_mark", kind="bed")
    assert naps(app) == [("2026-10-19T22:00", "2026-10-19T23:40", 100)]


def test_one_running_since_the_afternoon_ends_at_your_usual_length(app: App) -> None:
    app.at("2026-10-19T15:00")
    app.do("nap_start")
    app.at("2026-10-19T23:30")
    app.do("sleep_mark", kind="bed")
    assert naps(app) == [("2026-10-19T15:00", "2026-10-19T15:30", 30)]


def test_a_nap_logged_after_the_fact_put_right_and_taken_back(app: App) -> None:
    assert app.do("nap_log", start="2026-10-18T15:00", end="2026-10-18T15:40")["message"] == (
        "Logged a nap, 3pm to 3:40pm"
    )
    (nap,) = app.do("sleep")["naps"]
    assert nap["date"] == "2026-10-18"
    with pytest.raises(FieldError, match="napping from 3pm"):
        app.do("nap_log", start="2026-10-18T15:30", end="2026-10-18T16:00")
    with pytest.raises(FieldError, match="within four hours"):
        app.do("nap_log", start="2026-10-17T12:00", end="2026-10-17T17:00")
    with pytest.raises(FieldError, match="later than now"):
        app.do("nap_log", start="2026-10-19T08:00", end="2026-10-19T09:30")
    assert app.do("nap_edit", id=nap["id"], end="2026-10-18T15:25")["message"] == "Nap now 3pm to 3:25pm"
    assert naps(app) == [("2026-10-18T15:00", "2026-10-18T15:25", 25)]
    assert app.do("nap_remove", id=nap["id"])["message"] == "Removed the nap at 3pm"
    assert naps(app) == []


def test_a_nap_after_midnight_is_the_night_before_s(app: App) -> None:
    app.do("nap_log", start="2026-10-19T01:00", end="2026-10-19T01:30")
    assert app.do("sleep")["naps"][0]["date"] == "2026-10-18"


def test_no_work_is_planned_while_you_nap(app: App) -> None:
    app.do("add", text="essay due mon 6pm ~3h")
    replan(app.conn, app.now_utc)
    assert app.do("plan")["blocks"][0]["start"] == "2026-10-19T09:00"
    app.do("nap_start")
    replan(app.conn, app.now_utc)
    work = [b for b in app.do("plan")["blocks"] if b["start"].startswith("2026-10-19")]
    assert work and all(b["start"] >= "2026-10-19T09:30" for b in work)  # half an hour: no naps learned yet
    app.at("2026-10-19T09:20")
    app.do("nap_end")
    replan(app.conn, app.now_utc)
    assert app.do("plan")["blocks"][0]["start"] == "2026-10-19T09:30"  # the plan's next quarter hour


def test_a_nap_left_running_for_hours_holds_nothing(app: App) -> None:
    app.at("2026-10-19T09:00")
    app.do("nap_start")
    app.at("2026-10-19T12:30")
    assert take_snapshot(app.conn, app.now_utc).away is None


def test_a_nap_pays_back_the_night_before(app: App) -> None:
    def owed() -> float:
        return build_problem(build_input(take_snapshot(app.conn, app.now_utc))).nights[date(2026, 10, 19)].debt_hours

    app.do("sleep_mark", kind="bed", at="2026-10-19T03:00")  # Sunday night: four hours of seven
    app.do("sleep_mark", kind="up", at="2026-10-19T07:00")
    assert owed() == 3.0
    app.at("2026-10-19T15:00")
    app.do("nap_log", start="2026-10-19T13:00", end="2026-10-19T14:00")
    assert owed() == 2.0


class TestSnacks:
    @pytest.fixture
    def app(self, tmp_path: Path) -> App:
        app = new_app(tmp_path)
        app.do("settings_set", key="meal_tracking", value={"on": True})
        return app

    def test_a_snack_keeps_the_plan_clear_for_a_quarter_hour(self, app: App) -> None:
        app.do("add", text="essay due mon 6pm ~3h")
        app.do("meal_start", kind="snack")
        assert take_snapshot(app.conn, app.now_utc).away == ("Snack", utc("2026-10-19T09:00"), utc("2026-10-19T09:15"))
        replan(app.conn, app.now_utc)
        assert app.do("plan")["blocks"][0]["start"] == "2026-10-19T09:15"

    def test_as_long_as_your_snacks_take(self, app: App) -> None:
        for day in (14, 15, 16):
            app.do("meal_log", kind="snack", start=f"2026-10-{day}T16:00", end=f"2026-10-{day}T16:40")
        app.do("meal_start", kind="snack")
        assert take_snapshot(app.conn, app.now_utc).away == ("Snack", utc("2026-10-19T09:00"), utc("2026-10-19T09:40"))

    def test_a_meal_with_a_routine_is_held_by_its_routine_not_twice(self, app: App) -> None:
        app.do("series_add", title="Breakfast", preset="Routine", every="day", release_offset_min=240,
               due_offset_min=420, min_min=30, ideal_min=30, max_min=30)  # fmt: skip
        app.do("meal_start", kind="breakfast")
        assert take_snapshot(app.conn, app.now_utc).away is None
