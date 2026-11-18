"""Breaks (vacation days, 18 Nov): a run of days off or light. On a break day repeating events pause (one-off events
stay), meals aren't planned unless you say so, tasks of a paused tag wait, and instead of timed blocks the day has a
list of things to get done to stay on track: about N a day when Light, none when Off (work due inside is done before).
Ticking one on the day's list finishes it, or that day's share of something bigger. Black box through the commands,
then the rules inside. Monday 2026-10-19 9am; the break is Wednesday 21 to Friday 23."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app

WED, THU, FRI = "2026-10-21", "2026-10-22", "2026-10-23"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=7)


def add_break(app: App, **more) -> dict:
    return app.do("vacation_add", **({"name": "Fall break", "start": WED, "end": FRI} | more))["vacation"]


def blocks_on(app: App, day: str, item_id: int | None = None) -> list[dict]:
    replan(app.conn, app.now_utc)
    found = app.do("plan", start=f"{day}T04:00", end=f"{day}T23:59")["blocks"]
    return [b for b in found if item_id is None or b["item_id"] == item_id]


def minutes_on(app: App, day: str, item_id: int | None = None) -> int:
    from friday.core.time import parse_local

    return sum(
        int((parse_local(b["end"][:16]) - parse_local(b["start"][:16])).total_seconds() // 60)
        for b in blocks_on(app, day, item_id)
    )


def task(app: App, title: str, minutes: int, due: str, **more) -> int:
    return app.do("add", title=title, duration_min=minutes, due=due, **more)["item"]["id"]


def weekly(app: App, title: str, day: str, every: str) -> None:
    app.do("add", title=title, when="fixed", start=f"{day}T10:00", end=f"{day}T16:00", every=every)


def event_on(app: App, title: str, day: str) -> int:
    """The time of an event, or of a routine, on that day."""
    return next(i["id"] for i in app.table("items") if i["title"] == title and i["status"] == "todo"
                and (i["occurrence_date"] == day or (i["start_utc"] or "")[:10] == day))  # fmt: skip


class TestAddingOne:
    def test_a_break_is_saved_with_your_defaults(self, app: App) -> None:
        made = add_break(app)
        (listed,) = app.do("vacations")["vacations"]
        assert listed["id"] == made["id"] and listed["name"] == "Fall break"
        assert (listed["start"], listed["end"], listed["mode"], listed["per_day"]) == (WED, FRI, "light", 3)
        assert listed["plan_meals"] is False and listed["keep_sleep"] is False
        assert listed["pause"]["repeating"] == "all"

    def test_a_break_ending_before_it_starts_is_refused(self, app: App) -> None:
        with pytest.raises(Exception, match="ends on or after"):
            app.do("vacation_add", name="Oops", start=FRI, end=WED)

    def test_two_breaks_on_the_same_day_are_refused_by_name(self, app: App) -> None:
        add_break(app)
        with pytest.raises(Exception, match="Fall break"):
            app.do("vacation_add", name="Trip", start=THU, end="2026-10-25")

    def test_a_break_has_a_name_even_when_none_is_given(self, app: App) -> None:
        assert app.do("vacation_add", start=WED, end=FRI)["vacation"]["name"] == "Break"

    def test_editing_changes_what_you_said_and_keeps_the_rest(self, app: App) -> None:
        made = add_break(app)
        app.do("vacation_edit", id=made["id"], mode="off")
        (listed,) = app.do("vacations")["vacations"]
        assert listed["mode"] == "off" and listed["name"] == "Fall break" and listed["end"] == FRI

    def test_deleting_one_and_undoing_brings_it_back(self, app: App) -> None:
        made = add_break(app)
        out = app.full("vacation_delete", payload={"id": made["id"]}, provisional=False)
        assert app.do("vacations")["vacations"] == []
        app.do("undo", command_id=out.command_id)
        assert [v["id"] for v in app.do("vacations")["vacations"]] == [made["id"]]

    def test_the_calendar_says_which_days_are_on_a_break(self, app: App) -> None:
        add_break(app)
        days = {d["date"]: d for d in app.do("calendar", start="2026-10-19", days=7)["days"]}
        assert days["2026-10-20"]["vacation"] is None
        assert days[WED]["vacation"]["name"] == "Fall break" and days[WED]["vacation"]["mode"] == "light"
        assert days[FRI]["vacation"]["day_n"] == 3 and days[FRI]["vacation"]["days"] == 3


class TestEvents:
    def test_a_repeating_event_pauses_on_break_days_and_frees_its_time(self, app: App) -> None:
        app.do("add", title="Shift", when="fixed", start="2026-10-19T07:00", end="2026-10-19T23:59", every="mon,wed")
        essay = task(app, "essay", 120, "2026-10-21T23:00", release="2026-10-21T04:00")
        add_break(app)
        shift = event_on(app, "Shift", WED)
        plan = app.do("plan", start=f"{WED}T04:00", end=f"{WED}T23:59")
        assert shift in plan["paused"]
        assert next(f for f in plan["fixed"] if f["id"] == shift)["left_out"] == "paused"  # drawn paused
        assert minutes_on(app, WED, essay) == 120  # the day the shift took is free to use

    def test_it_is_not_paused_outside_the_break(self, app: App) -> None:
        weekly(app, "Seminar", "2026-10-19", "mon,wed")
        add_break(app)
        monday = event_on(app, "Seminar", "2026-10-19")
        assert monday not in app.do("plan", start="2026-10-19T04:00", end="2026-10-19T23:59")["paused"]

    def test_a_one_off_event_on_a_break_day_stays(self, app: App) -> None:
        app.do("add", title="Flight", when="fixed", start=f"{THU}T13:00", end=f"{THU}T16:00")
        add_break(app)
        flight = event_on(app, "Flight", THU)
        assert flight not in app.do("plan", start=f"{THU}T04:00", end=f"{THU}T23:59")["paused"]

    def test_a_repeat_you_keep_stays_on_the_break(self, app: App) -> None:
        weekly(app, "Choir", "2026-10-19", "mon,wed")
        series = next(i["series_id"] for i in app.table("items") if i["title"] == "Choir")
        add_break(app, pause={"repeating": "all", "series_kept": [series]})
        choir = event_on(app, "Choir", WED)
        assert choir not in app.do("plan", start=f"{WED}T04:00", end=f"{WED}T23:59")["paused"]

    def test_deleting_the_break_brings_the_event_back(self, app: App) -> None:
        weekly(app, "Seminar", "2026-10-19", "mon,wed")
        made = add_break(app)
        app.do("vacation_delete", id=made["id"])
        assert event_on(app, "Seminar", WED) not in app.do("plan", start=f"{WED}T04:00", end=f"{WED}T23:59")["paused"]


class TestWork:
    def test_off_plans_nothing_and_work_due_inside_is_done_before(self, app: App) -> None:
        report = task(app, "report", 180, f"{THU}T17:00")
        add_break(app, mode="off")
        assert all(minutes_on(app, d) == 0 for d in (WED, THU, FRI))
        assert sum(minutes_on(app, d, report) for d in ("2026-10-19", "2026-10-20")) == 180

    def test_light_keeps_a_day_to_about_n_things(self, app: App) -> None:
        for n in range(6):
            task(app, f"reading {n}", 60, f"{FRI}T23:00", release=f"{WED}T04:00")  # more than the days hold
        add_break(app, per_day=2)
        assert 0 < minutes_on(app, WED) <= 2 * 45

    def test_the_day_lists_things_by_name_without_times(self, app: App) -> None:
        essay = task(app, "essay", 60, f"{WED}T23:00", release=f"{WED}T04:00")
        add_break(app)
        replan(app.conn, app.now_utc)
        day = app.do("vacation_day", date=WED)
        assert day["vacation"]["name"] == "Fall break"
        (row,) = day["items"]
        assert row["item_id"] == essay and row["title"] == "essay" and row["ticked"] is False
        assert "start" not in row and "end" not in row
        days = {d["date"]: d for d in app.do("calendar", start=WED, days=1)["days"]}
        assert (days[WED]["vacation"]["things"], days[WED]["vacation"]["ticked"]) == (1, 0)

    def test_a_paused_tag_waits_until_after_the_break(self, app: App) -> None:
        app.do("area_add", name="Work")  # a task's tag, as To-do details names it
        work = task(app, "slides", 120, f"{FRI}T23:00", release=f"{WED}T04:00", area="Work")
        reading = task(app, "reading", 120, f"{FRI}T23:00", release=f"{WED}T04:00")
        add_break(app, pause={"repeating": "all", "tags": ["Work"]})
        assert all(minutes_on(app, d, work) == 0 for d in (WED, THU, FRI))  # only break days were open to it
        assert sum(minutes_on(app, d, reading) for d in (WED, THU, FRI)) == 120  # untagged work goes on

    def test_meals_are_not_planned_on_a_break_unless_you_say(self, app: App) -> None:
        app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
               min_min=15, ideal_min=30, max_min=30)  # fmt: skip
        lunch = event_on(app, "Lunch", WED)
        made = add_break(app)
        assert minutes_on(app, WED, lunch) == 0
        app.do("vacation_edit", id=made["id"], plan_meals=True)
        assert minutes_on(app, WED, lunch) > 0


    def test_a_break_added_mid_day_lists_no_meal_planned_that_morning(self, app: App) -> None:
        """Found in the demo, 18 Nov: a break added at 4pm listed that day's Breakfast and Lunch, kept as blocks begun
        before now from the plan made before the break."""
        app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
               min_min=15, ideal_min=30, max_min=30)  # fmt: skip
        app.at(f"{WED}T08:00")
        replan(app.conn, app.now_utc)  # Wednesday's lunch planned, before any break
        app.at(f"{WED}T16:00")
        add_break(app)
        replan(app.conn, app.now_utc)
        assert [t["title"] for t in app.do("vacation_day", date=WED)["items"]] == []


class TestTicking:
    def test_ticking_a_small_thing_finishes_it_and_unticking_opens_it_again(self, app: App) -> None:
        rent = task(app, "Pay rent", 15, f"{WED}T23:00", release=f"{WED}T04:00")
        add_break(app)
        app.at(f"{WED}T10:00")
        replan(app.conn, app.now_utc)
        app.do("vacation_tick", date=WED, item_id=rent, ticked=True)
        assert next(i for i in app.table("items") if i["id"] == rent)["status"] == "done"
        row = next(r for r in app.do("vacation_day", date=WED)["items"] if r["item_id"] == rent)
        assert row["ticked"] is True
        app.do("vacation_tick", date=WED, item_id=rent, ticked=False)
        assert next(i for i in app.table("items") if i["id"] == rent)["status"] == "todo"

    def test_ticking_a_bigger_thing_counts_the_days_share_and_keeps_it_open(self, app: App) -> None:
        big = task(app, "DLI reading", 360, f"{FRI}T23:00", release=f"{WED}T04:00")  # three break days of it
        add_break(app)
        app.at(f"{WED}T10:00")
        replan(app.conn, app.now_utc)
        share = minutes_on(app, WED, big)
        assert share > 0
        app.do("vacation_tick", date=WED, item_id=big, ticked=True)
        assert next(i for i in app.table("items") if i["id"] == big)["status"] == "todo"
        assert sum(p["minutes"] for p in app.table("progress") if p["item_id"] == big) == share
        replan(app.conn, app.now_utc)
        row = next(r for r in app.do("vacation_day", date=WED)["items"] if r["item_id"] == big)
        assert row["ticked"] is True
        app.do("vacation_tick", date=WED, item_id=big, ticked=False)
        assert not [p for p in app.table("progress") if p["item_id"] == big]

    def test_ticking_a_day_not_on_a_break_is_refused(self, app: App) -> None:
        rent = task(app, "Pay rent", 15, f"{WED}T23:00")
        add_break(app)
        with pytest.raises(Exception, match="isn't on a break"):
            app.do("vacation_tick", date="2026-10-20", item_id=rent, ticked=True)


class TestInside:
    def test_which_repeats_pause_by_calendar(self) -> None:
        from friday.core.vacations import Pause, pauses

        everything = Pause()
        assert pauses(everything, series_id=4, calendar="Work")
        assert not pauses(everything, series_id=None, calendar="Work")  # a one-off stays
        kept = Pause(repeating="all", calendars=["Family"])
        assert pauses(kept, series_id=4, calendar="Work") and not pauses(kept, series_id=4, calendar="Family")
        only = Pause(repeating="only", calendars=["Work"])
        assert pauses(only, series_id=4, calendar="Work") and not pauses(only, series_id=4, calendar="Gym")
        assert not pauses(only, series_id=4, calendar=None)  # made in Friday: not on a calendar named here
        assert pauses(Pause(repeating="only", series_paused=[9]), series_id=9, calendar="Gym")
        assert not pauses(Pause(series_kept=[4]), series_id=4, calendar="Work")

    def test_a_light_day_is_sized_by_things(self) -> None:
        from friday.core.vacations import LIGHT_MIN_PER_THING, Vacation, day_cap_hours

        light = Vacation(1, "b", WED, FRI, "light", 3)
        assert day_cap_hours(light, usual=8.0) == 3 * LIGHT_MIN_PER_THING / 60
        assert day_cap_hours(light, usual=1.0) == 1.0  # never more than your own cap
        assert day_cap_hours(Vacation(1, "b", WED, FRI, "off", 3), usual=8.0) == 0.0


class TestLearning:
    """Break days teach Friday nothing (18 Nov: "learning and insights should be paused during the break"): they
    don't count toward your averages, or say how long things take."""

    @pytest.fixture
    def october(self, tmp_path: Path) -> App:
        app = new_app(tmp_path, now="2026-10-01T09:00", horizon_days=3)
        app.do("area_add", name="CS")
        return app

    def finish(self, app: App, title: str, minutes: int, day: int) -> int:
        item = app.do("add", text=f"{title} #CS ~1h")["item"]["id"]
        end_min = 10 * 60 + minutes
        start, end = f"2026-10-{day:02d}T10:00", f"2026-10-{day:02d}T{end_min // 60:02d}:{end_min % 60:02d}"
        app.at(end).do("log", id=item, start=start, end=end)
        app.do("done", id=item)
        return item

    def test_lengths_arent_learned_from_a_break(self, october: App) -> None:
        from friday.commands.learned import learn_nightly
        from friday.planner.store import kv_get

        october.do("vacation_add", name="Fall break", start="2026-10-01", end="2026-10-10")
        for n in range(8):
            self.finish(october, f"problem set {n + 1}", 400, n + 1)
        october.at("2026-10-12T09:00")
        learn_nightly(october.conn, october.now_utc)
        assert kv_get(october.conn, "learned_durations") is None

    def test_insights_leave_break_days_out(self, october: App) -> None:
        october.do("vacation_add", name="Fall break", start="2026-10-01", end="2026-10-03")
        self.finish(october, "problem set 1", 400, 2)
        self.finish(october, "problem set 2", 90, 6)
        october.at("2026-10-12T09:00")
        seen = october.do("insights", weeks=4)
        assert seen["done"] == 1 and seen["hours"] == 1.5
        assert sum(map(sum, seen["heat"])) == 90

    def test_a_new_estimate_isnt_drawn_from_a_break(self, october: App) -> None:
        october.do("vacation_add", name="Fall break", start="2026-10-01", end="2026-10-03")
        for n in (1, 2, 3):  # three alike are enough to estimate from, off a break (`similar`, 400 minutes)
            self.finish(october, f"lab report {n}", 400, n)
        october.at("2026-10-12T09:00")
        estimate = october.do("add", text="lab report 4 #CS")["item"]["estimate"]
        assert estimate is None or estimate.get("method") != "similar"


class TestChoices:
    def test_the_chooser_offers_repeats_with_their_calendar_and_every_tag(self, app: App) -> None:
        weekly(app, "Seminar", "2026-10-19", "mon,wed")
        app.do("add", title="Flight", when="fixed", start=f"{THU}T13:00", end=f"{THU}T16:00")
        app.do("area_add", name="Work")
        found = app.do("break_choices")
        assert [s["title"] for s in found["series"]] == ["Seminar"]  # a one-off isn't a repeat
        assert found["series"][0]["calendar"] == "Friday" and found["series"][0]["every"]
        assert {"name": "Friday", "repeats": 1} in found["calendars"]
        assert "Work" in found["tags"]


class TestSuggested:
    """Breaks are suggested too (18 Nov: "breaks can both be added and suggested"): from an all-day event that says
    you're away, or from weekdays where your repeating events stop. A decision in the Inbox; yours to take or not."""

    def suggested(self, app: App) -> list[dict]:
        return [d for d in app.do("status")["decisions"] if d["kind"] == "break"]

    def test_an_all_day_vacation_event_is_suggested_and_taken(self, app: App) -> None:
        app.do("add", title="Vacation 🌴", when="fixed", start=f"{WED}T00:00", end="2026-10-24T00:00")
        (one,) = self.suggested(app)
        assert (one["start"], one["end"], one["name"]) == (WED, FRI, "Vacation 🌴") and "Vacation" in one["title"]
        app.do("break_suggestion", key=one["key"], take=True)
        (made,) = app.do("vacations")["vacations"]
        assert (made["start"], made["end"], made["name"]) == (WED, FRI, "Vacation 🌴")
        assert self.suggested(app) == []

    def test_one_declined_isnt_asked_again(self, app: App) -> None:
        app.do("add", title="Out of office", when="fixed", start=f"{THU}T00:00", end="2026-10-23T00:00")
        (one,) = self.suggested(app)
        app.do("break_suggestion", key=one["key"], take=False)
        assert self.suggested(app) == [] and app.do("vacations")["vacations"] == []

    def test_a_birthday_isnt_a_break(self, app: App) -> None:
        app.do("add", title="Remy's Birthday", when="fixed", start=f"{WED}T00:00", end=f"{THU}T00:00")
        assert self.suggested(app) == []

    def test_weekdays_where_your_repeats_stop_are_suggested(self, app: App) -> None:
        app.do("add", title="Lecture", when="fixed", start="2026-10-19T10:00", end="2026-10-19T11:00",
               every="rrule:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", exceptions=[{"date": d, "skip": True} for d in ("2026-10-28", "2026-10-29", "2026-10-30")])  # fmt: skip
        (one,) = self.suggested(app)
        assert (one["start"], one["end"]) == ("2026-10-28", "2026-10-30")

    def test_a_usual_week_suggests_nothing(self, app: App) -> None:
        app.do("add", title="Lecture", when="fixed", start="2026-10-19T10:00", end="2026-10-19T11:00",
               every="rrule:FREQ=WEEKLY;BYDAY=MO,WE,FR")  # fmt: skip
        assert self.suggested(app) == []

    def test_days_already_on_a_break_arent_suggested(self, app: App) -> None:
        app.do("add", title="Vacation", when="fixed", start=f"{WED}T00:00", end="2026-10-24T00:00")
        add_break(app)
        assert self.suggested(app) == []
