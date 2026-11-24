"""Settings, paces and one day's changes through the whole pipeline (24 Nov, the user: every feature tested in every
layer): a real `fridayd serve`, each command sent over HTTP as Settings and the calendar send it, and what you'd then
see read back through other queries: the saved paces and the one in effect (`paces`), each day's pace, sleep and most
work on the calendar (`calendar`), and the plan the worker makes after (`plan`). Refusals are checked with the words
the server says, and that a refused change keeps nothing."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest

from tests.system.test_beat_plan_system import SLEEP, WEEKDAYS, Friday


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("settings"))
    server.c("settings_set", key="sleep", value=SLEEP)
    yield server
    server.stop()


@pytest.fixture(scope="module")
def today(friday: Friday) -> date:
    return date.fromisoformat(friday.q("calendar")["today"])


def refused(friday: Friday, verb: str, **body: Any) -> dict:
    """The refusal's field and words: a command's own (FieldError), or the request's shape (FastAPI's `detail`)."""
    answer = friday.http.post(f"/api/c/{verb}", json=body)
    assert answer.status_code == 422, answer.text
    out = answer.json()
    if "detail" in out:
        first = out["detail"][0]
        return {"field": first["loc"][-1], "message": first["msg"]}
    return out


def days(friday: Friday, start: date, n: int = 7) -> dict[str, dict]:
    return {d["date"]: d for d in friday.q("calendar", start=start.isoformat(), days=n)["days"]}


def planned(friday: Friday) -> dict:
    """The plan once the worker has caught up with every change."""

    def caught_up() -> bool:
        s = friday.q("status")
        return s["plan_generation"] is not None and s["plan_generation"] >= s["generation"]

    friday.until(caught_up, timeout=180)
    return friday.q("plan")


# Saved paces


def test_pace_save_makes_a_pace_from_the_dials_in_effect_with_those_given(friday: Friday) -> None:
    said = friday.c("pace_save", name="Crunch", capacity=1.3)
    assert said["message"] == "Saved pace Crunch: capacity 1.3 · rest 1 · spread 1 · growth 1"
    out = friday.q("paces")
    assert out["paces"]["Crunch"] == {"capacity": 1.3, "rest": 1.0, "spread": 1.0, "growth": 1.0}
    assert {"Normal", "Easy", "Push", "Crunch"} <= set(out["paces"]) and out["default"] == "Normal"


def test_pace_save_changes_a_saved_pace_by_any_case_keeping_the_dials_left_out(friday: Friday) -> None:
    friday.c("pace_save", name="crunch", rest=0.5)
    paces = friday.q("paces")["paces"]
    assert paces["Crunch"] == {"capacity": 1.3, "rest": 0.5, "spread": 1.0, "growth": 1.0}
    assert "crunch" not in paces  # the same pace, not a second one


def test_pace_save_refuses_dials_out_of_range_and_keeps_nothing(friday: Friday) -> None:
    for dials in ({"capacity": 2.0}, {"rest": 0.1}, {"spread": 9}, {"growth": -1}):
        assert refused(friday, "pace_save", name="Wild", **dials)["field"] == "dials"
    assert "Wild" not in friday.q("paces")["paces"]


# Switching pace


def test_pace_for_days_runs_from_today_then_back_to_the_default(friday: Friday, today: date) -> None:
    out = friday.c("pace", name="crunch", for_days=3)
    last = today + timedelta(days=2)
    assert (out["label"], out["start_date"], out["end_date"]) == ("Crunch", today.isoformat(), last.isoformat())
    assert out["message"] == f"Crunch pace, today through {last:%a %b} {last.day}. Then back to Normal."
    now = friday.q("paces")
    assert now["now_label"] == "Crunch" and now["period_end"] == last.isoformat()
    assert now["now_dials"] == {"capacity": 1.3, "rest": 0.5, "spread": 1.0, "growth": 1.0}
    shown = days(friday, today, 5)
    assert [shown[(today + timedelta(n)).isoformat()]["pace"] for n in range(5)] == ["Crunch"] * 3 + [None] * 2


def test_a_saved_pace_in_use_cant_be_deleted(friday: Friday) -> None:
    assert refused(friday, "pace_delete", name="Crunch")["message"] == "name: Crunch is in use now"
    assert "Crunch" in friday.q("paces")["paces"]


def test_pace_refuses_what_isnt_a_pace_or_a_time_to_run_it(friday: Friday, today: date) -> None:
    assert refused(friday, "pace", name="Turbo")["message"].startswith("name: no pace called Turbo; saved: Normal")
    assert refused(friday, "pace", name="Easy", for_days=0)["message"] == "for_days: must be at least 1"
    assert refused(friday, "pace", name="Easy", until="someday soon")["field"] == "until"
    yesterday = today - timedelta(days=1)
    assert refused(friday, "pace", name="Easy", start=yesterday.isoformat())["message"] == (
        f"start: {yesterday:%a %b} {yesterday.day} is before today"
    )
    assert refused(friday, "pace", name="Easy", start="next tuesday")["field"] == "start"
    assert refused(friday, "pace", capacity=0.1)["field"] == "dials"
    assert friday.q("paces")["now_label"] == "Crunch"  # nothing refused changed the pace


def test_pace_back_to_the_default_ends_the_period(friday: Friday, today: date) -> None:
    out = friday.c("pace", name="Normal")
    assert out["message"] == "Normal pace from today." and out["end_date"] is None
    now = friday.q("paces")
    assert now["now_label"] == "Normal" and now["period_end"] is None
    assert all(d["pace"] is None for d in days(friday, today, 4).values())


def test_dials_alone_make_a_custom_pace_and_a_later_start_leaves_the_days_before(friday: Friday, today: date) -> None:
    start = today + timedelta(days=2)
    out = friday.c("pace", capacity=0.8, start=start.isoformat(), for_days=2)
    assert out["label"] == "Custom" and out["dials"]["capacity"] == 0.8
    assert out["start_date"] == start.isoformat() and out["end_date"] == (start + timedelta(days=1)).isoformat()
    assert out["message"].startswith(f"Custom pace, {start:%a %b} {start.day} through")
    shown = days(friday, today, 6)
    assert [shown[(today + timedelta(n)).isoformat()]["pace"] for n in range(6)] == [
        None,
        None,
        "Custom",
        "Custom",
        None,
        None,
    ]
    assert friday.q("paces")["now_label"] == "Normal"  # today still the default
    friday.c("pace", name="Normal", start=start.isoformat())  # and back, from that day
    assert all(d["pace"] is None for d in days(friday, today, 6).values())


# Deleting a pace


def test_pace_delete_refuses_the_default_and_a_pace_that_isnt_there(friday: Friday) -> None:
    assert refused(friday, "pace_delete", name="normal")["message"] == "name: Normal is the default pace"
    assert refused(friday, "pace_delete", name="Turbo")["message"] == "name: no pace called Turbo"
    assert "Normal" in friday.q("paces")["paces"]


def test_pace_delete_removes_it_and_its_weekdays_go_back_to_the_default(friday: Friday, today: date) -> None:
    other = WEEKDAYS[(today.weekday() + 3) % 7]  # a weekday that isn't today: the pace isn't in use now
    friday.c("settings_set", key="pace", value={"weekly": {other: "Crunch"}})
    shown = days(friday, today)
    assert [d["pace"] for d in shown.values() if WEEKDAYS[date.fromisoformat(d["date"]).weekday()] == other] == [
        "Crunch"
    ]
    assert friday.c("pace_delete", name="CRUNCH")["message"] == "Deleted pace Crunch"
    assert "Crunch" not in friday.q("paces")["paces"]
    pace = friday.q("settings")["pace"]
    assert pace["weekly"] == {} and pace["default"] == "Normal"
    assert all(d["pace"] is None for d in days(friday, today).values())


# One day's changes


def test_day_override_moves_that_nights_sleep_and_the_calendar_draws_it(friday: Friday, today: date) -> None:
    day = today + timedelta(days=3)
    assert friday.c("day_override", date=day.isoformat(), bedtime="22:00")["message"] == f"Set {day:%a %b} {day.day}"
    shown = days(friday, day, 1)[day.isoformat()]
    assert shown["bedtime"] == f"{day}T22:00" and shown["core"] == f"{day}T23:00"  # its hour of margin kept
    before = days(friday, day - timedelta(days=1), 1)[(day - timedelta(days=1)).isoformat()]
    assert before["bedtime"].endswith("T23:30")  # the usual on other nights
    friday.c("day_override", date=day.isoformat(), margin_min=0)  # what's left out (the bedtime) stays
    shown = days(friday, day, 1)[day.isoformat()]
    assert shown["bedtime"] == f"{day}T22:00" and shown["core"] == f"{day}T22:00"
    friday.c("day_override", date=day.isoformat(), wake="09:00")
    morning = days(friday, day - timedelta(days=1), 1)[(day - timedelta(days=1)).isoformat()]
    assert morning["wake"] == f"{day}T09:00"  # that date's morning
    friday.c("day_override", date=day.isoformat(), bedtime=None, margin_min=None)  # null clears one
    shown = days(friday, day, 1)[day.isoformat()]
    assert shown["bedtime"] == f"{day}T23:30" and shown["core"] == f"{day + timedelta(days=1)}T00:30"


def test_day_override_with_no_work_hours_keeps_work_off_that_day(friday: Friday, today: date) -> None:
    day = today + timedelta(days=2)
    due = (today + timedelta(days=6)).isoformat() + "T17:00"
    ids = {friday.c("add", title=f"Essay part {n}", duration_min=240, due=due)["item"]["id"] for n in (1, 2, 3)}
    friday.c("day_override", date=day.isoformat(), cap_hours=0)
    assert days(friday, day, 1)[day.isoformat()]["cap_hours"] == 0
    plan = planned(friday)
    ours = [b for b in plan["blocks"] if b["item_id"] in ids]
    assert ours, "the work wasn't planned at all"
    assert not [b for b in ours if b["start"].startswith(day.isoformat())], "work planned on a day with no work hours"
    friday.c("day_override", date=day.isoformat(), margin_min=30)  # a later change leaves the cap as it was
    assert days(friday, day, 1)[day.isoformat()]["cap_hours"] == 0
    friday.c("day_override", date=day.isoformat(), cap_hours=None)
    assert days(friday, day, 1)[day.isoformat()]["cap_hours"] == 10.0  # back to the weekday's


def test_day_override_refuses_a_bad_date_or_time_on_its_own_field(friday: Friday, today: date) -> None:
    day = (today + timedelta(days=4)).isoformat()
    assert refused(friday, "day_override", date="2026-13-40", bedtime="22:00")["field"] == "date"
    assert refused(friday, "day_override", date=day, bedtime="25:00")["field"] == "bedtime"
    assert refused(friday, "day_override", date=day, wake="7am")["field"] == "wake"
    assert refused(friday, "day_override", date=day, cap_hours=30)["field"] == "cap_hours"
    assert refused(friday, "day_override", date=day, cap_hours=-3)["field"] == "cap_hours"
    assert refused(friday, "day_override", date=day, margin_min=-5)["field"] == "margin_min"
    shown = days(friday, date.fromisoformat(day), 1)[day]
    assert shown["bedtime"].endswith("T23:30") and shown["cap_hours"] == 10.0  # nothing refused was kept


# Settings


def test_settings_set_changes_only_the_nights_named_and_the_calendar_follows(friday: Friday, today: date) -> None:
    night = WEEKDAYS[today.weekday()]
    friday.c("settings_set", key="sleep", value={night: {"bedtime": "22:30"}})
    sleep = friday.q("settings")["sleep"]
    assert (
        sleep[night] == {**SLEEP[night], "bedtime": "22:30"}
        and sleep[WEEKDAYS[(today.weekday() + 1) % 7]] == SLEEP["mon"]
    )
    assert days(friday, today, 1)[today.isoformat()]["bedtime"] == f"{today}T22:30"
    friday.c("settings_set", key="sleep", value={night: {"bedtime": "23:30"}})


def test_settings_set_refuses_what_isnt_a_setting_and_keeps_what_was(friday: Friday) -> None:
    assert refused(friday, "settings_set", key="sleep", value={"mon": "bad"})["field"] == "value"
    assert refused(friday, "settings_set", key="daily_cap", value={"mon": 5})["field"] == "value"  # every weekday
    assert (
        "isn't one of your saved paces"
        in refused(friday, "settings_set", key="pace", value={"default": "Turbo"})["message"]
    )
    after = friday.q("settings")
    assert after["sleep"]["mon"] == SLEEP["mon"] and after["daily_cap"]["mon"] == 10.0
    assert after["pace"]["default"] == "Normal"


def test_settings_set_daily_cap_is_each_days_most_work_on_the_calendar(friday: Friday, today: date) -> None:
    caps = dict.fromkeys(WEEKDAYS, 10.0) | {WEEKDAYS[(today.weekday() + 5) % 7]: 2.5}
    friday.c("settings_set", key="daily_cap", value=caps)
    shown = days(friday, today)
    assert [d["cap_hours"] for d in shown.values()] == [10.0] * 5 + [2.5, 10.0]
