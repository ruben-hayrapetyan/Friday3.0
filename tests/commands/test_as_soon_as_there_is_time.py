"""By default work goes into the first free time (17 Nov, the user: "for the projects and things along those lines,
friday should use all time allocated … by default, friday should use all time that it can"; asked, "As soon as there's
time"): a project with no pace set, its steps, an assignment due weeks away and an ongoing project's hours a week, up
to what each day takes. A pace you set, a rule keeping work near its due and deadlines all come first.

Whole system, through the commands and the planner, from Monday 19 Oct 2026 9am on an empty calendar, two weeks
planned."""

from collections import defaultdict
from pathlib import Path

import pytest

from friday.core.time import format_local, parse_local, parse_utc, to_local, to_utc
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app

TUESDAY_NIGHT = parse_utc("2026-10-21T08:00Z")  # Wednesday 21 Oct, 4am in New York: Tuesday's planning day is over


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=14)


def planned(app: App, ids: list[int] | None = None) -> list[tuple[int, int, int]]:
    plan = app.conn.execute("SELECT id FROM plans WHERE status = 'current'").fetchone()[0]
    found = app.conn.execute("SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ?", [plan])
    return [(r[0], parse_utc(r[1]), parse_utc(r[2])) for r in found if ids is None or r[0] in ids]


def hours(app: App, ids: list[int], before: int | None = None) -> float:
    found = planned(app, ids)
    return sum(min(end, before or end) - start for _, start, end in found if before is None or start < before) / 60


def big_project(app: App, due: str, minutes: int) -> int:
    return app.do("add", title="Big project", preset="Project", due=due, duration_min=minutes)["item"]["id"]


@pytest.mark.parametrize("due", ["2026-10-29T17:00", "2026-11-30T17:00"])
def test_a_project_with_no_pace_takes_the_first_free_days(app: App, due: str) -> None:
    # 10 hours: due in ten days, it was planned 2-3 hours a day over four days leaning toward its due; due in six
    # weeks, only 3.5 of them in the plan's two weeks
    made = big_project(app, due, 600)
    replan(app.conn, app.now_utc)
    assert hours(app, [made]) == 10
    assert hours(app, [made], TUESDAY_NIGHT) == 10


def test_a_project_bigger_than_the_days_fills_each_of_them_to_its_most(app: App) -> None:
    made = big_project(app, "2026-11-02T17:00", 200 * 60)
    replan(app.conn, app.now_utc)
    per_day: dict[str, float] = defaultdict(float)
    for _, start, end in planned(app, [made]):
        per_day[format_local(to_local(start, TZ))[:10]] += (end - start) / 60
    assert len(per_day) == 14 and min(per_day.values()) >= 8  # every day of the plan, as full as a day may be


def test_an_assignment_due_in_weeks_is_done_now(app: App) -> None:
    # due past the plan's two weeks, it was left for later: nothing of it planned
    made = app.do("add", title="Lab report", preset="Assignment", due="2026-11-06T17:00", duration_min=240)
    replan(app.conn, app.now_utc)
    assert hours(app, [made["item"]["id"]], TUESDAY_NIGHT) == 4


def test_an_ongoing_projects_hours_are_all_planned_each_week(app: App) -> None:
    # 10 hours a week came out 6 this week: each sitting cost what splitting the whole week's hours does
    series = app.do("ongoing_add", title="Guitar", hours_per_week=10)["id"]
    replan(app.conn, app.now_utc)
    weeks = [
        i for (i,) in app.conn.execute("SELECT id FROM items WHERE series_id = ? ORDER BY occurrence_date", [series])
    ]
    for week in weeks[:2]:
        assert hours(app, [week]) >= 10


@pytest.mark.parametrize("pace", ["linear", "back"])
def test_a_pace_you_set_still_spreads_the_work(app: App, pace: str) -> None:
    made = big_project(app, "2026-10-29T17:00", 600)
    app.do("project_set", id=made, pacing=pace)
    replan(app.conn, app.now_utc)
    assert hours(app, [made]) == 10
    assert hours(app, [made], TUESDAY_NIGHT) <= (4 if pace == "linear" else 2.5)


def test_work_due_first_still_comes_first(app: App) -> None:
    # Tuesday to Friday full; a 30-hour project due in three weeks and an assignment due Monday evening: the
    # assignment isn't late for it, and is done first
    for day in ("20", "21", "22", "23"):
        app.do("add", title="Shift", when="fixed", start=f"2026-10-{day}T07:30", end=f"2026-10-{day}T23:00",
               preset="Event")  # fmt: skip
    project = big_project(app, "2026-11-09T17:00", 30 * 60)
    due = "2026-10-19T21:00"
    task = app.do("add", title="Problem set", preset="Assignment", due=due, duration_min=180)["item"]["id"]
    replan(app.conn, app.now_utc)
    assert hours(app, [task]) == 3
    assert max(end for _, _, end in planned(app, [task])) <= to_utc(parse_local(due), TZ)
    assert hours(app, [project]) > 0
    assert app.do("changes")["late_hours"] == {}


def test_exam_prep_kept_close_to_its_exam_stays_there(app: App) -> None:
    quiz = app.do("add", title="Math 1920 Quiz 3", when="fixed", start="2026-10-23T13:25", end="2026-10-23T14:15",
                  event_kind="exam")["item"]["id"]  # fmt: skip
    prep = app.do("add", title="Prep: Math 1920 Quiz 3", preset="Exam prep", duration_min=120,
                  due="2026-10-23T13:25", before=[quiz])["item"]["id"]  # fmt: skip
    big_project(app, "2026-11-09T17:00", 20 * 60)
    app.do("rule_add", text="I prefer all sessions of exam prep tasks to be done as close to the exam as possible")
    replan(app.conn, app.now_utc)
    assert hours(app, [prep]) == 2
    assert all(start >= to_utc(parse_local("2026-10-22T12:00"), TZ) for _, start, _ in planned(app, [prep]))


def test_work_pulled_early_comes_in_sittings_of_an_hour_or_whole(app: App) -> None:
    # 17 Nov, Linux only: Jordan's hour-long Aplia quiz, due in three weeks, got 30 minutes in a gap on Monday, a scrap.
    # Pulled early only because there's time, a sitting is an hour at least, or the whole of shorter work.
    from friday.planner.build import build_problem
    from friday.planner.prepare import build_input
    from friday.planner.snapshot import take_snapshot

    quiz = app.do("add", title="Aplia quiz 9", preset="Assignment", duration_min=60, due="2026-11-08T23:59")["item"]["id"]
    short = app.do("add", title="Reading response", preset="Assignment", duration_min=45, due="2026-11-08T23:59")["item"]["id"]
    big = app.do("add", title="Lab report", preset="Assignment", duration_min=240, due="2026-11-08T23:59")["item"]["id"]
    items = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items
    by_id = {int(k.split(":")[1]): v for k, v in items.items() if k.startswith("item:")}
    assert all(by_id[i].soon for i in (quiz, short, big))
    assert by_id[quiz].min_chunk == 4  # an hour: one sitting
    assert by_id[short].min_chunk == 3  # all 45 minutes at once
    assert by_id[big].min_chunk >= 4  # an hour at least
