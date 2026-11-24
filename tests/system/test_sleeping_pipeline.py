"""Tracking your sleep, the whole pipeline (tests/features.toml: sleeping; 24 Nov, the user: "go through every single
functionality of the app and build an extensive test suite"): a real `fridayd serve` in its own folder, the taps
(`sleep_mark`), a tap moved (`sleep_mark_edit`) or taken back (`sleep_mark_remove`) and a review's missed tap skipped
(`sleep_skip`) sent over HTTP as the app sends them, and what they did read back through the sleep view (Insights →
Sleep), a day's review (the Inbox's sleep questions) and the nap the morning's tap ends.

Each test keeps to nights of its own, so they don't read one another's taps."""

import json
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("sleeping"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


@pytest.fixture
def tracking(friday: Friday) -> Iterator[None]:
    friday.c("settings_set", key="sleep_tracking", value={"on": True})
    yield
    friday.c("settings_set", key="sleep_tracking", value={"on": True})


def today() -> date:
    """Friday's day (it starts at 4am), as the server counts it."""
    return (datetime.now(ZoneInfo(TZ)) - timedelta(hours=4)).date()


def refused(friday: Friday, verb: str, **body: Any) -> str:
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    said = answer.json()
    return said.get("message") or json.dumps(said)


def night(friday: Friday, evening: date) -> dict | None:
    """The sleep view's row for the night of `evening`, if it has one."""
    return next((n for n in friday.q("sleep")["nights"] if n["date"] == str(evening)), None)


# ---- sleep_mark ------------------------------------------------------------------------------------------------------


def test_taps_are_refused_while_tracking_is_off_and_nothing_is_recorded(friday: Friday) -> None:
    friday.c("settings_set", key="sleep_tracking", value={"on": False})
    evening = today() - timedelta(days=9)
    said = refused(friday, "sleep_mark", kind="bed", at=f"{evening}T23:00")
    assert said == "kind: sleep tracking is off; turn it on in Settings → Schedule"
    assert friday.q("sleep")["on"] is False
    friday.c("settings_set", key="sleep_tracking", value={"on": True})
    assert night(friday, evening) is None  # the refused tap left nothing behind


def test_a_bed_and_an_up_tap_make_a_night_with_how_long_you_slept(friday: Friday, tracking: None) -> None:
    evening = today() - timedelta(days=3)
    morning = evening + timedelta(days=1)
    said = friday.c("sleep_mark", kind="bed", at=f"{evening}T23:45")["message"]
    assert said == "Good night: 11:45pm"
    assert friday.c("sleep_mark", kind="up", at=f"{morning}T07:15")["message"] == "Good morning: 7:15am"
    assert friday.c("sleep_mark", kind="ready", at=f"{morning}T08:05")["message"] == "Ready to work: 8:05am"
    assert friday.c("sleep_mark", kind="done", at=f"{evening}T22:30")["message"] == "Done with work: 10:30pm"
    found = night(friday, evening)
    assert found is not None
    assert (found["bed"], found["up"], found["ready"], found["done"]) == (
        f"{evening}T23:45", f"{morning}T07:15", f"{morning}T08:05", f"{evening}T22:30"
    )  # fmt: skip
    assert found["slept_min"] == 450  # 11:45pm to 7:15am
    assert found["routine_min"] == 50  # up to ready
    assert found["wind_down_min"] == 75  # done with work to bed
    assert found["planned_min"] == 8 * 60  # the night your settings plan: 11:30pm to 7:30am
    assert all(found[k] for k in ("bed_id", "up_id", "ready_id", "done_id"))


def test_a_bedtime_past_midnight_is_still_the_night_before(friday: Friday, tracking: None) -> None:
    evening = today() - timedelta(days=4)
    morning = evening + timedelta(days=1)
    friday.c("sleep_mark", kind="bed", at=f"{morning}T01:30")
    friday.c("sleep_mark", kind="up", at=f"{morning}T08:00")
    found = night(friday, evening)
    assert found is not None and found["bed"] == f"{morning}T01:30" and found["slept_min"] == 390


def test_a_tap_later_than_now_or_of_no_kind_is_refused(friday: Friday, tracking: None) -> None:
    tomorrow = today() + timedelta(days=2)
    assert refused(friday, "sleep_mark", kind="up", at=f"{tomorrow}T07:00") == "at: that's later than now"
    assert "kind" in refused(friday, "sleep_mark", kind="nap", at=f"{today()}T03:00")
    assert "'whenever' is not a time" in refused(friday, "sleep_mark", kind="bed", at="whenever")
    assert night(friday, tomorrow - timedelta(days=1)) is None


def test_the_morning_tap_ends_a_nap_left_running(friday: Friday, tracking: None) -> None:
    lay_down = datetime.now(ZoneInfo(TZ)) - timedelta(minutes=20)
    friday.c("nap_start", at=lay_down.strftime("%Y-%m-%dT%H:%M"))
    assert friday.q("sleep")["napping"] is not None
    friday.c("sleep_mark", kind="up")
    assert friday.q("sleep")["napping"] is None  # up: the nap is over, not left counting
    naps = friday.q("sleep")["naps"]
    assert naps and naps[0]["end"] is not None and 19 <= naps[0]["minutes"] <= 21  # ended now, 20 minutes on


# ---- sleep_mark_edit -------------------------------------------------------------------------------------------------


def test_a_tap_moved_changes_the_night_it_was_in(friday: Friday, tracking: None) -> None:
    evening = today() - timedelta(days=6)
    morning = evening + timedelta(days=1)
    friday.c("sleep_mark", kind="bed", at=f"{evening}T23:00")
    friday.c("sleep_mark", kind="up", at=f"{morning}T09:00")
    found = night(friday, evening)
    assert found is not None and found["slept_min"] == 600
    said = friday.c("sleep_mark_edit", id=found["up_id"], at=f"{morning}T06:30")["message"]
    assert said == "Good morning moved to 6:30am"
    moved = night(friday, evening)
    assert moved is not None
    assert (moved["up"], moved["slept_min"], moved["up_id"]) == (f"{morning}T06:30", 450, found["up_id"])


def test_a_tap_moved_to_later_than_now_or_one_that_isnt_there_is_refused(friday: Friday, tracking: None) -> None:
    evening = today() - timedelta(days=7)
    friday.c("sleep_mark", kind="bed", at=f"{evening}T23:10")
    found = night(friday, evening)
    assert found is not None
    future = today() + timedelta(days=3)
    assert refused(friday, "sleep_mark_edit", id=found["bed_id"], at=f"{future}T23:00") == "at: that's later than now"
    assert night(friday, evening)["bed"] == f"{evening}T23:10"  # type: ignore[index]  # unchanged
    assert refused(friday, "sleep_mark_edit", id=987_654, at=f"{evening}T23:00") == "id: no sleep mark 987654"


# ---- sleep_mark_remove -----------------------------------------------------------------------------------------------


def test_a_tap_taken_back_leaves_the_night_without_it(friday: Friday, tracking: None) -> None:
    evening = today() - timedelta(days=8)
    morning = evening + timedelta(days=1)
    friday.c("sleep_mark", kind="bed", at=f"{evening}T22:50")
    friday.c("sleep_mark", kind="up", at=f"{morning}T06:50")
    found = night(friday, evening)
    assert found is not None and found["slept_min"] == 480
    said = friday.c("sleep_mark_remove", id=found["bed_id"])["message"]
    assert said == "Removed good night at 10:50pm"
    after = night(friday, evening)
    assert after is not None  # the morning's tap keeps the night
    assert (after["bed"], after["bed_id"], after["slept_min"], after["up"]) == (None, None, None, f"{morning}T06:50")
    assert refused(friday, "sleep_mark_remove", id=found["bed_id"]) == f"id: no sleep mark {found['bed_id']}"
    friday.c("sleep_mark_remove", id=after["up_id"])
    assert night(friday, evening) is None  # nothing left of it


# ---- sleep_skip ------------------------------------------------------------------------------------------------------


def test_a_review_asks_for_the_taps_a_day_is_missing_and_skip_stops_one(friday: Friday, tracking: None) -> None:
    day = today() - timedelta(days=11)  # no taps on it, nor the night before
    asked = {a["kind"]: a for a in friday.q("review", date=str(day))["sleep"]}
    assert set(asked) == {"up", "ready", "done", "bed"}
    assert asked["up"]["question"] == "When did you get up?" and asked["up"]["at"] == f"{day}T07:30"  # your usual
    assert asked["bed"]["at"] == f"{day}T23:30"
    assert friday.c("sleep_skip", date=str(day), kind="up")["message"] == "Skipped"
    after = {a["kind"] for a in friday.q("review", date=str(day))["sleep"]}
    assert after == {"ready", "done", "bed"}  # only that one stops
    friday.c("sleep_skip", date=str(day), kind="up")  # twice is once
    friday.c("sleep_skip", date=str(day), kind="bed")
    assert {a["kind"] for a in friday.q("review", date=str(day))["sleep"]} == {"ready", "done"}
    other = today() - timedelta(days=12)
    assert "up" in {a["kind"] for a in friday.q("review", date=str(other))["sleep"]}  # another day's still asked


def test_a_tap_made_answers_the_reviews_question_too(friday: Friday, tracking: None) -> None:
    day = today() - timedelta(days=13)
    assert "bed" in {a["kind"] for a in friday.q("review", date=str(day))["sleep"]}
    friday.c("sleep_mark", kind="bed", at=f"{day}T23:20")
    assert "bed" not in {a["kind"] for a in friday.q("review", date=str(day))["sleep"]}


def test_skip_refuses_a_kind_or_day_it_doesnt_know(friday: Friday, tracking: None) -> None:
    assert "kind" in refused(friday, "sleep_skip", date=str(today()), kind="nap")
    assert "date" in refused(friday, "sleep_skip", date="someday", kind="up")


def test_with_tracking_off_the_review_asks_nothing(friday: Friday) -> None:
    day = today() - timedelta(days=15)
    friday.c("settings_set", key="sleep_tracking", value={"on": True})
    assert friday.q("review", date=str(day))["sleep"]
    friday.c("settings_set", key="sleep_tracking", value={"on": False})
    assert friday.q("review", date=str(day))["sleep"] == []
    friday.c("settings_set", key="sleep_tracking", value={"on": True})


# ---- what Friday learns from them ------------------------------------------------------------------------------------


def test_nights_recorded_later_than_planned_are_offered_as_a_later_bedtime(friday: Friday, tracking: None) -> None:
    friday.c("settings_set", key="sleep_tracking", value={"on": True, "min_nights": 2})
    for n in range(20, 34):  # two weeks of nights, a month ago: in bed by 1am, up at 9am
        evening = today() - timedelta(days=n)
        morning = evening + timedelta(days=1)
        friday.c("sleep_mark", kind="bed", at=f"{morning}T01:00")
        friday.c("sleep_mark", kind="up", at=f"{morning}T09:00")
    out = friday.q("sleep")
    assert out["recorded_nights"] >= 14
    learned = {(c["field"], c["learned"]) for c in out["changes"]}
    assert ("bedtime", "01:00") in learned and ("wake", "09:00") in learned
    # the schedule offered is your settings with each learned time on its days
    assert all(out["suggested"][d][c["field"]] == c["learned"] for c in out["changes"] for d in c["days"])
    late = [d for d, s in out["suggested"].items() if s["bedtime"] == "01:00"]
    assert len(late) >= 5  # most nights (one group also has the other tests' earlier nights)
    assert friday.q("settings")["sleep"]["mon"]["bedtime"] == "23:30"  # offered, never changed without a yes
