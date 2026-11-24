"""Insights' trends, the whole pipeline (tests/features.toml: insights; 24 Nov, the user: "build an extensive test suite
... i want to make sure that absolutely nothing can break without our tests flagging it"): a real `fridayd serve`; work
added, timed and finished over HTTP as the app sends it, and `insights` read back as the Insights page reads it: what
was finished, the hours, how far off the estimates were by kind, and when you work (the heatmap and its sentence)."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.system.test_beat_plan_system import SLEEP, TZ, Friday

DAYS = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")


@pytest.fixture(scope="module")
def friday(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Friday]:
    server = Friday(tmp_path_factory.mktemp("insights"))
    server.c("settings_set", key="sleep", value=SLEEP)
    server.c("settings_set", key="time", value=server.q("settings")["time"] | {"day_start": "04:00"})
    yield server
    server.stop()


def day(back: int) -> date:
    return datetime.now(ZoneInfo(TZ)).date() - timedelta(days=back)


def add(friday: Friday, title: str, **fields: object) -> int:
    return friday.c("add", title=title, due=f"{day(-10)}T17:00", **fields)["item"]["id"]


def column(out: dict, hour: int) -> int:
    return out["heat_hours"].index(hour)


def test_1_with_nothing_done_insights_are_empty(friday: Friday) -> None:
    out = friday.q("insights")
    assert (out["weeks"], out["done"], out["hours"], out["estimate_ratio"], out["by_kind"]) == (4, 0, 0, None, [])
    assert out["heat_hours"] == list(range(8, 24)) and out["heat"] == [[0] * 16] * 7
    assert out["best_hours"] is None


def test_2_estimates_against_the_time_it_took_by_kind_not_counting_routines(friday: Friday) -> None:
    essay = add(friday, "Essay", preset="Assignment", duration_min=120)
    email = add(friday, "Email the TA", preset="Task", duration_min=60)
    friday.c("done", id=essay, actual_min=180)  # half again as long
    friday.c("done", id=email, actual_min=30)  # half
    walk = friday.c("series_add", title="Evening walk", preset="Routine", every="day", duration_min=30)
    (first,) = [i for i in friday.q("items") if i["series_id"] == walk["id"]][:1]
    friday.c("done", id=first["id"], actual_min=45)  # part of the day, not work
    out = friday.q("insights")
    assert (out["done"], out["hours"], out["estimate_ratio"]) == (2, 3.5, 1.0)
    kinds = {k["kind"]: (k["n"], k["median"], k["low"], k["high"]) for k in out["by_kind"]}
    assert kinds == {"Assignment": (1, 1.5, 1.5, 1.5), "Task": (1, 0.5, 0.5, 0.5)}


def test_3_several_of_a_kind_give_its_median_and_quartiles(friday: Friday) -> None:
    for n, took in enumerate((30, 45, 90), start=1):  # each planned at an hour
        friday.c("done", id=add(friday, f"Reading {n}", preset="Task", duration_min=60), actual_min=took)
    task = next(k for k in friday.q("insights")["by_kind"] if k["kind"] == "Task")
    # Task's ratios: 0.5 (the email), 0.5, 0.75, 1.5
    assert (task["n"], task["median"], task["low"], task["high"]) == (4, 0.62, 0.5, 1.5)
    assert friday.q("insights")["by_kind"][0]["kind"] == "Task"  # the kind with the most first


def test_4_time_worked_fills_the_heatmap_and_says_your_best_hours(friday: Friday) -> None:
    lab = add(friday, "Lab report", preset="Assignment", duration_min=240)
    yesterday = day(1)
    friday.c("log", id=lab, start=f"{yesterday}T14:00", end=f"{yesterday}T16:00")
    out = friday.q("insights")
    row = out["heat"][yesterday.weekday()]
    assert (row[column(out, 14)], row[column(out, 15)]) == (60, 60)
    assert sum(map(sum, out["heat"])) == 120
    assert out["best_hours"] == f"You get the most done on {DAYS[yesterday.weekday()]}, 2pm to 4pm."


def test_5_one_hour_holds_at_most_sixty_minutes_however_many_timers_ran(friday: Friday) -> None:
    other = add(friday, "Problem set", preset="Assignment", duration_min=120)
    yesterday = day(1)
    friday.c("log", id=other, start=f"{yesterday}T14:00", end=f"{yesterday}T15:00")  # alongside the lab report
    out = friday.q("insights")
    assert out["heat"][yesterday.weekday()][column(out, 14)] == 60
    assert sum(map(sum, out["heat"])) == 120


def test_6_work_past_midnight_counts_for_the_night_before_and_widens_the_columns(friday: Friday) -> None:
    late = add(friday, "Night reading", preset="Task", duration_min=60)
    friday.c("log", id=late, start=f"{day(1)}T02:00", end=f"{day(1)}T03:00")  # before the 4am day start
    out = friday.q("insights")
    assert out["heat_hours"] == [*range(8, 24), 0, 1, 2]  # out to the 2am column, after 11pm
    assert out["heat"][day(2).weekday()][column(out, 2)] == 60  # the night before's row
    assert out["heat"][day(1).weekday()][column(out, 2)] == 0
    assert all(len(row) == len(out["heat_hours"]) for row in out["heat"])


def test_7_weeks_says_how_far_back_and_out_of_range_is_refused(friday: Friday) -> None:
    old = add(friday, "Old notes", preset="Task", duration_min=60)
    friday.c("log", id=old, start=f"{day(10)}T10:00", end=f"{day(10)}T11:00")
    four, one = friday.q("insights", weeks=4), friday.q("insights", weeks=1)
    assert (four["weeks"], one["weeks"]) == (4, 1)
    assert four["heat"][day(10).weekday()][column(four, 10)] == 60
    assert one["heat"][day(10).weekday()][column(one, 10)] == 0  # ten days ago is before last week
    assert four["done"] == one["done"] == 5  # finished today
    for weeks in (0, 53, -1):
        answer = friday.http.get("/api/q/insights", params={"weeks": weeks})
        assert answer.status_code == 422, answer.text


def test_8_work_opened_again_leaves_the_numbers(friday: Friday) -> None:
    before = friday.q("insights")
    essay = next(i for i in friday.q("items", status="all") if i["title"] == "Essay")
    friday.c("reopen", id=essay["id"])
    out = friday.q("insights")
    assert (out["done"], out["hours"]) == (before["done"] - 1, round(before["hours"] - 3, 1))
    assert "Assignment" not in {k["kind"] for k in out["by_kind"]}
