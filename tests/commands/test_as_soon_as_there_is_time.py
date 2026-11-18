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


def test_short_work_comes_in_one_sitting_but_never_past_the_sittings_you_set(app: App) -> None:
    # 17 Nov, Linux only: Jordan's hour-long Aplia quiz, due in three weeks, got 30 minutes in a gap on Monday, a scrap.
    # An hour or less wanted as soon as there's time goes in one sitting when an hour is free for it; a least or
    # longest sitting set on the item itself stays as you set it, and longer work keeps its own least (an hour's least
    # for a thesis's steps left 19 of its 40 hours unplanned). A split of it costs as a long sitting's does.
    from friday.planner.build import SOON_SITTING_HOURS, build_problem
    from friday.planner.prepare import build_input
    from friday.planner.snapshot import take_snapshot

    def add(title: str, minutes: int, **chunks: int) -> int:
        due = "2026-11-08T23:59"
        return app.do("add", title=title, preset="Assignment", duration_min=minutes, due=due, **chunks)["item"]["id"]

    quiz, short, big = add("Aplia quiz 9", 60), add("Reading response", 45), add("Lab report", 240)
    own_least = add("Aplia quiz 10", 60, min_chunk_min=45)
    own_most = add("Aplia quiz 11", 60, max_chunk_min=45)
    items = build_problem(build_input(take_snapshot(app.conn, app.now_utc))).items
    by_id = {int(k.split(":")[1]): v for k, v in items.items() if k.startswith("item:")}
    assert all(by_id[i].soon for i in (quiz, short, big, own_least, own_most))
    assert [by_id[i].min_chunk for i in (quiz, short, big)] == [4, 3, 2]  # an hour, 45 minutes, the kind's half hour
    assert (by_id[own_least].min_chunk, by_id[own_most].min_chunk, by_id[own_most].max_chunk) == (3, 2, 3)
    assert [by_id[i].size_hours for i in (quiz, short, big)] == [SOON_SITTING_HOURS, SOON_SITTING_HOURS, 4]


# What's due first goes first (17 Nov, the user's choice: "as soon as there's time" for all deadline work, in due
# order): work due this week goes in the earliest good time too, before work due later, and the rest fills in after it.


def event(app: App, title: str, start: str, end: str) -> None:
    app.do("add", title=title, when="fixed", start=start, end=end, preset="Event")


def sittings(app: App, item_id: int) -> list[tuple[int, int]]:
    """Back-to-back blocks of the item as one sitting: (start, end), UTC minutes."""
    out: list[tuple[int, int]] = []
    for _, start, end in sorted(planned(app, [item_id]), key=lambda b: b[1]):
        if out and out[-1][1] == start:
            out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def local(when: str) -> int:
    return to_utc(parse_local(when), TZ)


def test_work_due_sooner_is_planned_no_later_than_work_due_later_and_both_early(app: App) -> None:
    # Monday has three hours, 9 to noon; Tuesday is free. A lab report due in three weeks and a problem set due
    # Wednesday, 3 hours each: with only work due a week off pulled early, the lab report took Monday morning and the
    # problem set waited (17 Nov: Mastering Physics 11, due in three weeks, planned tonight, number 9, due in six
    # days, the day before its due)
    event(app, "Shift", "2026-10-19T12:00", "2026-10-19T23:00")
    later = app.do("add", title="Lab report", preset="Assignment", due="2026-11-09T17:00", duration_min=180)
    sooner = app.do("add", title="Problem set", preset="Assignment", due="2026-10-21T23:59", duration_min=180)
    replan(app.conn, app.now_utc)
    first, second = sittings(app, sooner["item"]["id"]), sittings(app, later["item"]["id"])
    assert hours(app, [sooner["item"]["id"]]) == 3 and hours(app, [later["item"]["id"]]) == 3
    assert first[0][0] <= second[0][0]
    assert first[-1][1] <= local("2026-10-19T12:00")  # Monday's three hours
    assert second[-1][1] <= TUESDAY_NIGHT  # and the lab report as soon as there's time after it


def test_a_lab_due_wednesday_is_not_cut_into_the_gaps_between_mondays_classes(app: App) -> None:
    # Early isn't shredded: Monday is classes with 45 minutes between them, then a club until 23:00; Tuesday has the
    # afternoon free. The lab goes in one real sitting on Tuesday, not in Monday's gaps (17 Nov: four times the price
    # for work due within two days cut a 3-hour lab due Wednesday into the gaps between Monday's classes)
    for start, end in (("09:00", "10:00"), ("10:45", "11:45"), ("12:30", "13:30"), ("14:15", "15:15"),
                       ("16:00", "17:00"), ("17:45", "18:45")):  # fmt: skip
        event(app, "Class", f"2026-10-19T{start}", f"2026-10-19T{end}")
    event(app, "Club", "2026-10-19T19:00", "2026-10-19T23:00")
    event(app, "Shift", "2026-10-20T08:00", "2026-10-20T13:00")
    lab = app.do("add", title="Physics lab", preset="Assignment", due="2026-10-21T23:59", duration_min=180)
    app.do("add", title="Essay", preset="Assignment", due="2026-11-09T17:00", duration_min=240)
    replan(app.conn, app.now_utc)
    found = sittings(app, lab["item"]["id"])
    assert sum(end - start for start, end in found) == 180
    assert all(end - start >= 60 for start, end in found), found
    assert found[-1][1] <= local("2026-10-21T23:59")


def test_an_hours_work_due_this_week_is_one_sitting_when_an_hour_is_free(app: App) -> None:
    # Monday to Friday are shifts with half hours between them, but for one free hour on Thursday, 12:00–13:00; the
    # weekend is free. An hour's quiz due Friday and an hour's quiz due in three weeks: the one due Friday takes the
    # hour, whole, and the other goes in one sitting after it (17 Nov: Jordan's Aplia quiz 7 came out 30 + 30 minutes,
    # the good time taken by work due weeks off)
    for day in ("19", "20", "21", "23"):
        for start, end in (("08:00", "11:30"), ("12:00", "15:30"), ("16:00", "19:30"), ("20:00", "23:30")):
            event(app, "Shift", f"2026-10-{day}T{start}", f"2026-10-{day}T{end}")
    event(app, "Shift", "2026-10-22T08:00", "2026-10-22T12:00")
    event(app, "Shift", "2026-10-22T13:00", "2026-10-22T23:30")
    quiz = app.do("add", title="Aplia quiz 7", preset="Assignment", due="2026-10-23T23:59", duration_min=60)
    later = app.do("add", title="Aplia quiz 9", preset="Assignment", due="2026-11-08T23:59", duration_min=60)
    replan(app.conn, app.now_utc)
    assert sittings(app, quiz["item"]["id"]) == [(local("2026-10-22T12:00"), local("2026-10-22T13:00"))]
    # and the one due in three weeks whole too, after it, not in the week's half hours (on Linux it was)
    ((after, until),) = sittings(app, later["item"]["id"])
    assert until - after == 60 and after >= local("2026-10-22T13:00")


def test_an_hours_work_with_only_half_hours_free_before_its_due_is_still_done_in_time(app: App) -> None:
    # Only half hours free before its due: in one sitting it couldn't be done in time at all, so it keeps its kind's
    # least sitting and is done in two, on time
    for day in ("19", "20"):
        for start, end in (("08:00", "11:30"), ("12:00", "15:30"), ("16:00", "19:30"), ("20:00", "23:30")):
            event(app, "Shift", f"2026-10-{day}T{start}", f"2026-10-{day}T{end}")
    quiz = app.do("add", title="Aplia quiz 7", preset="Assignment", due="2026-10-20T23:59", duration_min=60)
    replan(app.conn, app.now_utc)
    found = sittings(app, quiz["item"]["id"])
    assert sum(end - start for start, end in found) == 60 and found[-1][1] <= local("2026-10-20T23:59")
    assert app.do("changes")["late_hours"] == {}
