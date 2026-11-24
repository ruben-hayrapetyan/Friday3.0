"""The calendar's days and tags, the whole pipeline (tests/features.toml: calendar; 24 Nov, the user: "go through every
single functionality of the app and build an extensive test suite ... absolutely nothing can break without our tests
flagging it"): a real `fridayd serve` in its own folder, the sleep, one-day changes, breaks, deadlines and tags it's
told over HTTP, and the calendar's day headers, nights, time axis, due markers and tag list read back as the Plan
page reads them."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday


def day(n: int) -> str:
    return (datetime.now(ZoneInfo(TZ)) + timedelta(days=n)).strftime("%Y-%m-%d")


def after(d: str, n: int = 1) -> str:
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("calendar"))
    try:
        server.c("settings_set", key="sleep", value=SLEEP)
        yield server
    finally:
        server.stop()


def refused(friday: Friday, verb: str, **params: object) -> dict:
    answer = friday.http.get(f"/api/q/{verb}", params=params)
    assert answer.status_code == 422, answer.text
    return answer.json()


def days_of(friday: Friday, start: str, days: int = 7) -> dict[str, dict]:
    return {d["date"]: d for d in friday.q("calendar", start=start, days=days)["days"]}


def test_a_week_from_today_by_default_with_each_night_as_set(friday: Friday) -> None:
    out = friday.q("calendar")
    today = out["today"]
    assert [d["date"] for d in out["days"]] == [after(today, n) for n in range(7)]
    assert out["now"][:10] in (today, after(today))  # the server's own clock (a day starting at 4am)
    first = out["days"][0]
    assert (first["bedtime"], first["core"], first["wake"]) == (
        f"{today}T23:30",
        f"{after(today)}T00:30",  # an hour of margin past bedtime
        f"{after(today)}T07:30",
    )
    assert (out["axis_start_min"], out["axis_end_min"]) == (7 * 60 + 30, 24 * 60 + 30)  # 7:30am to 12:30am


def test_any_start_and_length_up_to_six_weeks(friday: Friday) -> None:
    start = day(10)
    out = friday.q("calendar", start=start, days=42)
    assert len(out["days"]) == 42 and out["days"][0]["date"] == start and out["days"][-1]["date"] == after(start, 41)
    assert len(friday.q("calendar", start=start, days=1)["days"]) == 1


def test_refuses_a_date_it_cant_read_and_a_length_out_of_range(friday: Friday) -> None:
    said = refused(friday, "calendar", start="next tuesday")
    assert said["field"] == "start" and "isn't a date like" in said["message"]
    refused(friday, "calendar", days=0)
    refused(friday, "calendar", days=43)


def test_a_later_night_on_one_weekday_moves_that_nights_lines_and_the_axis(friday: Friday) -> None:
    sleep = {**SLEEP, "sat": {"bedtime": "01:00", "wake": "09:00", "margin_min": 30}}
    friday.c("settings_set", key="sleep", value=sleep)
    try:
        start = day(14)
        week = days_of(friday, start)
        saturday = next(d for d in week if date.fromisoformat(d).weekday() == 5)
        assert (week[saturday]["bedtime"], week[saturday]["core"]) == (f"{after(saturday)}T01:00",
                                                                       f"{after(saturday)}T01:30")  # fmt: skip
        friday_ = after(saturday, -1)
        assert week[friday_]["wake"] == f"{saturday}T09:00"  # Saturday morning's wake, on Friday's night
        out = friday.q("calendar", start=start, days=7)
        assert out["axis_end_min"] == 25 * 60 + 30  # past midnight: 1:30am
        assert out["axis_start_min"] == 7 * 60 + 30  # the earliest wake still
    finally:
        friday.c("settings_set", key="sleep", value=SLEEP)
    assert friday.q("calendar", start=day(14), days=7)["axis_end_min"] == 24 * 60 + 30


def test_a_one_day_change_shows_on_that_day_alone(friday: Friday) -> None:
    d = day(3)
    usual = days_of(friday, day(2), 3)
    friday.c("day_override", date=d, bedtime="21:00", cap_hours=2)
    week = days_of(friday, day(2), 3)
    assert week[d]["bedtime"] == f"{d}T21:00" and week[d]["cap_hours"] == 2
    assert week[d]["core"] == f"{d}T22:00"
    for other in (day(2), day(4)):
        assert week[other] == usual[other]
    assert week[d]["cap_hours"] != usual[d]["cap_hours"]


def test_a_break_marks_its_days(friday: Friday) -> None:
    first, last = day(20), day(22)
    friday.c("vacation_add", name="Thanksgiving trip", start=first, end=last, mode="off")
    week = days_of(friday, day(19), 5)
    assert week[day(19)]["vacation"] is None and week[day(23)]["vacation"] is None
    on = [week[d]["vacation"] for d in (first, day(21), last)]
    assert [(v["name"], v["mode"], v["day_n"], v["days"]) for v in on] == [
        ("Thanksgiving trip", "off", n, 3) for n in (1, 2, 3)
    ]


def test_deadlines_show_on_their_days_until_done(friday: Friday) -> None:
    d = day(5)
    hard = friday.c("add", title="Grant form", duration_min=30, firmness="hard", due=f"{d}T17:00")["item"]["id"]
    soft = friday.c("add", title="Tidy notes", duration_min=30, firmness="soft", due=f"{d}T20:00")["item"]["id"]
    later = friday.c("add", title="Far away", duration_min=30, firmness="hard", due=f"{day(30)}T12:00")["item"]["id"]
    dues = friday.q("calendar", start=d, days=1)["dues"]
    assert [(m["item_id"], m["title"], m["due"]) for m in dues] == [
        (hard, "Grant form", f"{d}T17:00"),
        (soft, "Tidy notes", f"{d}T20:00"),
    ]
    assert later not in {m["item_id"] for m in friday.q("calendar", start=d, days=7)["dues"]}
    friday.c("done", id=hard)
    assert [m["item_id"] for m in friday.q("calendar", start=d, days=1)["dues"]] == [soft]
    friday.c("drop", id=soft)
    assert friday.q("calendar", start=d, days=1)["dues"] == []


def test_a_repeats_soft_window_isnt_a_deadline_on_the_calendar(friday: Friday) -> None:
    friday.c("series_add", title="Laundry", every="week", duration_min=60, firmness="soft")
    friday.c("materialize")
    dues = friday.q("calendar", start=day(0), days=21)["dues"]
    assert "Laundry" not in {m["title"] for m in dues}
    assert any(i["title"] == "Laundry" and i["due"] for i in friday.q("items"))  # it has one, just not drawn


def test_the_tags_are_listed_by_name_with_color_and_archived(friday: Friday) -> None:
    friday.c("area_add", name="Zoology", color="green")
    gone = friday.c("area_add", name="Art history")
    friday.c("area_edit", id=gone["id"], archived=True)
    found = friday.q("areas")
    names = [a["name"] for a in found]
    assert names == sorted(names) and {"Zoology", "Art history"} <= set(names)
    by = {a["name"]: a for a in found}
    assert (by["Zoology"]["color"], by["Zoology"]["archived"]) == ("green", False)
    assert by["Art history"]["archived"] is True
