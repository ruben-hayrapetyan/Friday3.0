"""The morning brief on a break day, and all-day events in any day's brief (Friday Notes-3, a tester's notes of
Thursday 26 Nov, on the Thanksgiving break, Light, about 4h a day): "morning briefing – incorrect behavior on breaks".

10. Times for tasks ("14:15–14:45", "12:45–13:45") "bc friday doesn't plan when u do them on break": the brief now
    says the day is on a break, and the page shows its things by name (web: Dialogs.screen.test.tsx).
11. "today is not black friday": Black Friday, all day Friday 27, under Thursday's "Fixed today". The day runs from
    4am to 4am, and an all-day event begins at midnight, inside it. An all-day event is on its own dates.
12. "Push pace doesn't exist on break, neither do any of the other paces": no pace on a break day.
13. "four tasks are listed in the morning briefing, whereas only three are listed in today's to-do. the missing task
    is an overdue one (DLI reading)": a repeating task's time from before the break, overdue, was planned on the
    break day (the plan leaves out only the break's own days' times) but kept off the day's list (which left out
    every repeating task). Now one rule leaves them out of both, and the brief of a break day is its list.

Monday 2026-10-19 in New York; the break is Wednesday 21 to Friday 23, as in test_breaks.py.
"""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app

MON, TUE, WED, THU, FRI, SAT = "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now=f"{MON}T08:05", horizon_days=7)


def add_break(app: App, **more) -> dict:
    return app.do("vacation_add", **({"name": "Fall break", "start": WED, "end": FRI} | more))["vacation"]


def task(app: App, title: str, minutes: int, due: str | None = None, **more) -> int:
    return app.do("add", title=title, duration_min=minutes, **({"due": due} if due else {}), **more)["item"]["id"]


def weekly_reading(app: App, **more) -> None:
    """A reading due every Tuesday at 8pm, 75 minutes, as the tester's DLI reading (due Sun 22 Nov, end of day)."""
    app.do("series_add", title="DLI reading", every="tue", duration_min=75, start_date="2026-10-13",
           due_offset_min=1200, firmness="hard", **more)  # fmt: skip


def all_day(app: App, title: str, first: str, after: str) -> int:
    """An all-day event from `first` to the day before `after`, as calendars give them: midnight to midnight."""
    return app.do("add", title=title, when="fixed", start=f"{first}T00:00", end=f"{after}T00:00")["item"]["id"]


def morning(app: App, at: str) -> dict:
    app.at(at)
    replan(app.conn, app.now_utc)
    return app.do("brief")


def listed(app: App, day: str) -> list[str]:
    return [t["title"] for t in app.do("vacation_day", date=day)["items"]]


def rocks(brief: dict) -> list[str]:
    return [r["title"] for r in brief["rocks"]]


# 10. A break day's brief says so: the page shows no times then.


class TestTheBriefSaysTheBreak:
    @pytest.mark.parametrize("mode", ["light", "off"])
    def test_a_break_day_names_its_break(self, app: App, mode: str) -> None:
        task(app, "essay", 60, f"{FRI}T23:00")
        add_break(app, mode=mode)
        brief = morning(app, f"{THU}T08:05")
        assert brief["vacation"] is not None
        assert (brief["vacation"]["name"], brief["vacation"]["mode"], brief["vacation"]["day_n"]) == (
            "Fall break",
            mode,
            2,
        )

    @pytest.mark.parametrize("day", [TUE, SAT])
    def test_the_days_before_and_after_are_ordinary(self, app: App, day: str) -> None:
        add_break(app)
        assert morning(app, f"{day}T08:05")["vacation"] is None

    def test_a_day_with_no_break_at_all_is_ordinary(self, app: App) -> None:
        task(app, "essay", 60, f"{TUE}T17:00")
        brief = morning(app, f"{MON}T08:05")
        assert brief["vacation"] is None and rocks(brief) == ["essay"]


# 12. No pace on a break day, neither in words nor offered.


class TestNoPaceOnABreak:
    @pytest.mark.parametrize("pace", ["Push", "Easy"])
    @pytest.mark.parametrize("mode", ["light", "off"])
    def test_a_pace_set_for_days_isnt_said_on_a_break_day(self, app: App, pace: str, mode: str) -> None:
        task(app, "essay", 60, f"{FRI}T23:00")
        app.do("pace", name=pace, for_days=14)
        add_break(app, mode=mode)
        brief = morning(app, f"{THU}T08:05")
        assert brief["pace"] is None and "pace" not in brief["summary"].lower()

    @pytest.mark.parametrize("pace", ["Push", "Easy"])
    def test_the_same_pace_is_said_on_the_days_around_it(self, app: App, pace: str) -> None:
        app.do("pace", name=pace, for_days=14)
        add_break(app)
        for day in (TUE, SAT):
            brief = morning(app, f"{day}T08:05")
            assert brief["pace"].startswith(f"{pace} pace until") and brief["pace"] in brief["summary"], day

    def test_back_to_normal_isnt_said_on_a_break_day(self, app: App) -> None:
        app.do("pace", name="Push", for_days=2)  # Monday and Tuesday: over on Wednesday, the break's first day
        add_break(app)
        assert morning(app, f"{WED}T08:05")["pace"] is None

    def test_back_to_normal_is_said_on_an_ordinary_day(self, app: App) -> None:
        app.do("pace", name="Push", for_days=1)
        assert morning(app, f"{TUE}T08:05")["pace"] == "Back to Normal today"

    def test_a_short_night_on_a_break_offers_no_easy_day(self, app: App) -> None:
        app.do("settings_set", key="sleep_tracking", value={"on": True})
        add_break(app, keep_sleep=True)
        app.at(f"{THU}T07:30")
        app.do("sleep_mark", kind="bed", at=f"{THU}T03:00")  # Wednesday night: four hours
        app.do("sleep_mark", kind="up", at=f"{THU}T07:00")
        said = morning(app, f"{THU}T08:05")["sleep"]
        assert said.startswith("You slept 4h last night") and "Easy" not in said

    def test_a_short_night_on_an_ordinary_day_offers_an_easy_day(self, app: App) -> None:
        app.do("settings_set", key="sleep_tracking", value={"on": True})
        app.do("sleep_mark", kind="bed", at=f"{MON}T03:00")
        app.do("sleep_mark", kind="up", at=f"{MON}T07:00")
        assert morning(app, f"{MON}T08:05")["sleep"].endswith("An Easy day?")


# 11. An all-day event is on its own dates, on any day.


def fixed(brief: dict) -> list[str]:
    return [f["title"] for f in brief["fixed"]]


def time_of(app: App, title: str, day: str) -> int:
    """The time of a repeating all-day event on that day: its midnight is 4am in UTC, the same date."""
    return next(i["id"] for i in app.table("items") if i["title"] == title and i["start_utc"][:10] == day)


class TestAllDayEvents:
    def test_the_reported_case_thanksgiving_today_black_friday_tomorrow_on_a_break(self, app: App) -> None:
        all_day(app, "Thanksgiving Day", THU, FRI)
        all_day(app, "Black Friday", FRI, SAT)
        add_break(app)
        brief = morning(app, f"{THU}T08:05")
        assert fixed(brief) == ["Thanksgiving Day"]
        assert "1 fixed" in brief["summary"]

    @pytest.mark.parametrize(
        ("first", "after", "shown"),
        [
            (TUE, WED, True),  # today
            (WED, THU, False),  # tomorrow: begins at midnight, inside today's hours to 4am
            (WED, SAT, False),  # three days from tomorrow
            (MON, TUE, False),  # yesterday
            (MON, THU, True),  # from yesterday to tomorrow
            (TUE, SAT, True),  # from today on
            (MON, WED, True),  # yesterday and today
        ],
    )
    def test_an_ordinary_days_brief_lists_the_all_day_events_of_its_date(
        self, app: App, first: str, after: str, shown: bool
    ) -> None:
        all_day(app, "Holiday", first, after)
        brief = morning(app, f"{TUE}T08:05")
        assert ("Holiday" in fixed(brief)) is shown
        assert f"{len(brief['fixed'])} fixed" in brief["summary"]

    def test_before_the_day_starts_it_is_still_yesterdays_brief(self, app: App) -> None:
        """At 2am Wednesday the day is still Tuesday's (days start at 4am): Tuesday's all-day event, not Wednesday's,
        though Wednesday's has begun by the clock."""
        all_day(app, "Tuesday's", TUE, WED)
        all_day(app, "Wednesday's", WED, THU)
        assert fixed(morning(app, f"{WED}T02:00")) == ["Tuesday's"]

    def test_after_the_day_starts_it_is_todays(self, app: App) -> None:
        all_day(app, "Tuesday's", TUE, WED)
        all_day(app, "Wednesday's", WED, THU)
        assert fixed(morning(app, f"{WED}T04:30")) == ["Wednesday's"]

    def test_a_timed_event_after_midnight_is_still_the_day_befores(self, app: App) -> None:
        app.do("add", title="Late show", when="fixed", start=f"{WED}T01:00", end=f"{WED}T02:00")
        app.do("add", title="Overnight", when="fixed", start=f"{TUE}T23:00", end=f"{WED}T01:00")
        app.do("add", title="Breakfast meeting", when="fixed", start=f"{WED}T05:00", end=f"{WED}T06:00")
        assert sorted(fixed(morning(app, f"{TUE}T08:05"))) == ["Late show", "Overnight"]

    def test_a_repeating_all_day_event_the_day_after_a_break_isnt_paused(self, app: App) -> None:
        """Saturday's begins at midnight, in the hours of Friday, the break's last day: it was paused as Friday's."""
        app.do("add", title="Market day", when="fixed", start="2026-10-17T00:00", end="2026-10-18T00:00", every="sat")
        add_break(app)
        saturday = time_of(app, "Market day", SAT)
        assert saturday not in app.do("plan", start=f"{SAT}T04:00", end=f"{SAT}T23:59")["paused"]

    def test_a_repeating_all_day_event_on_a_breaks_first_day_is_paused(self, app: App) -> None:
        """Wednesday's begins at midnight, in the hours of Tuesday, the day before the break: it was left on."""
        app.do("add", title="Lab day", when="fixed", start="2026-10-14T00:00", end="2026-10-15T00:00", every="wed")
        add_break(app)
        wednesday = time_of(app, "Lab day", WED)
        assert wednesday in app.do("plan", start=f"{WED}T04:00", end=f"{WED}T23:59")["paused"]


# 13. A break day's brief is its list: the same things, in the same order, by one rule.


class TestTheBriefIsTheDaysList:
    def test_the_reported_case_an_overdue_reading_from_before_the_break(self, app: App) -> None:
        weekly_reading(app)
        task(app, "edit article draft", 60, f"{FRI}T23:59")
        add_break(app, work_min=240)
        brief = morning(app, f"{THU}T08:05")  # Tuesday's reading is two days late
        assert "DLI reading" in listed(app, THU)
        assert rocks(brief) == listed(app, THU)

    def test_the_overdue_reading_counts_in_the_days_hours(self, app: App) -> None:
        weekly_reading(app)
        add_break(app, work_min=240)
        brief = morning(app, f"{THU}T08:05")
        (reading,) = brief["rocks"]
        assert listed(app, THU) == ["DLI reading"]
        assert reading["planned_min"] == 75 and brief["summary"].startswith("1.2 h planned")

    @pytest.mark.parametrize("plan_repeating", [False, True])
    def test_a_repeating_tasks_time_on_the_break_follows_its_switch_in_both(
        self, app: App, plan_repeating: bool
    ) -> None:
        app.do("series_add", title="Groceries", every="day", duration_min=45, release_offset_min=540,
               due_offset_min=1200, start_date=WED)  # fmt: skip
        add_break(app, plan_repeating=plan_repeating)
        brief = morning(app, f"{THU}T08:05")
        assert ("Groceries" in listed(app, THU)) is plan_repeating
        assert rocks(brief) == listed(app, THU)

    def test_a_repeating_tasks_time_missed_before_the_break_is_in_both(self, app: App) -> None:
        """Tuesday's errand, not done, is late work like any other: the break turns off its own days' times only."""
        app.do("series_add", title="Groceries", every="day", duration_min=45, release_offset_min=540,
               due_offset_min=1200, start_date=TUE)  # fmt: skip
        add_break(app)
        brief = morning(app, f"{WED}T08:05")
        assert listed(app, WED) == ["Groceries"] and rocks(brief) == ["Groceries"]

    @pytest.mark.parametrize("plan_meals", [False, True])
    def test_a_meal_on_the_break_follows_its_switch_in_both(self, app: App, plan_meals: bool) -> None:
        app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=690, due_offset_min=840,
               min_min=15, ideal_min=30, max_min=30)  # fmt: skip
        task(app, "essay", 60, f"{FRI}T23:00")
        add_break(app, plan_meals=plan_meals)
        brief = morning(app, f"{THU}T08:05")
        assert ("Lunch" in listed(app, THU)) is plan_meals
        assert rocks(brief) == listed(app, THU)

    def test_overdue_and_undated_one_offs_are_in_both(self, app: App) -> None:
        task(app, "late report", 90, f"{TUE}T17:00", firmness="hard")
        task(app, "someday reading", 60)
        task(app, "essay", 60, f"{FRI}T23:00")
        add_break(app, work_min=240)
        brief = morning(app, f"{THU}T08:05")
        assert {"late report", "someday reading"} <= set(listed(app, THU))
        assert rocks(brief) == listed(app, THU)

    def test_work_due_soon_planned_another_day_is_in_neither(self, app: App) -> None:
        """A light day of an hour holds one of two hard deadlines due Friday: the other is Friday's thing, not today's
        (the brief added any hard deadline within two days, planned today or not)."""
        task(app, "essay", 60, f"{FRI}T23:00", firmness="hard", release=f"{THU}T04:00")
        task(app, "report", 60, f"{FRI}T23:00", firmness="hard", release=f"{THU}T04:00")
        add_break(app, work_min=60)
        brief = morning(app, f"{THU}T08:05")
        assert len(listed(app, THU)) == 1 and rocks(brief) == listed(app, THU)
        assert brief["summary"].startswith("1 h planned")

    def test_an_off_day_has_nothing_in_either_even_with_work_due_soon(self, app: App) -> None:
        task(app, "late report", 90, f"{TUE}T17:00", firmness="hard")
        task(app, "report", 60, f"{SAT}T12:00", firmness="hard")
        add_break(app, mode="off")
        brief = morning(app, f"{THU}T08:05")
        assert listed(app, THU) == [] and brief["rocks"] == []
        assert brief["summary"].startswith("0 h planned")

    def test_a_ticked_thing_stays_in_both_ticked(self, app: App) -> None:
        essay = task(app, "essay", 60, f"{FRI}T23:00", release=f"{THU}T04:00")
        task(app, "slides", 60, f"{FRI}T23:00", release=f"{THU}T04:00")
        add_break(app)
        morning(app, f"{THU}T08:05")
        app.do("vacation_tick", date=THU, item_id=essay)
        brief = morning(app, f"{THU}T09:00")
        assert rocks(brief) == listed(app, THU)
        assert {r["title"]: r["ticked"] for r in brief["rocks"]} == {"essay": True, "slides": False}
        assert (brief["vacation"]["things"], brief["vacation"]["ticked"]) == (2, 1)

    def test_more_things_than_five_are_all_in_the_brief(self, app: App) -> None:
        for n in range(7):
            task(app, f"reading {n}", 30, f"{FRI}T23:00", release=f"{THU}T04:00")
        add_break(app, work_min=240)
        brief = morning(app, f"{THU}T08:05")
        assert len(listed(app, THU)) >= 6 and rocks(brief) == listed(app, THU)

    def test_the_hours_are_the_lists(self, app: App) -> None:
        for n in range(3):
            task(app, f"reading {n}", 60, f"{FRI}T23:00", release=f"{THU}T04:00")
        add_break(app, work_min=240)
        brief = morning(app, f"{THU}T08:05")
        minutes = sum(r["planned_min"] for r in brief["rocks"])
        assert minutes == 180 and brief["summary"].startswith("3 h planned")

    def test_an_ordinary_day_still_names_overdue_work_not_planned_today(self, app: App) -> None:
        """Off a break the brief is as it was: a hard deadline past or within two days is there, planned today or
        not ("not today" on the page)."""
        task(app, "late report", 90, f"{MON}T07:00", firmness="hard")
        brief = morning(app, f"{MON}T08:05")
        assert "late report" in rocks(brief) and brief["vacation"] is None
