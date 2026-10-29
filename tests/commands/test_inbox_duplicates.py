"""The inbox sets aside what you have already (27 Oct: "please scan for duplicates before proposing things to me. I have
gotten many requests to add duplicates" and "make many test suites testing many different potentially duplicate
situations because these can definitely get complicated although them still being duplicate"). Each suite is one
situation, through the inbox as mail, feeds and calendars reach it: tasks, events, what you finished, two sources at
once, what changes while a suggestion waits, and adding one anyway. Titles alone are tested in core/test_sameness.py."""

from pathlib import Path
from typing import Any

import pytest

from friday.commands.fetching import sync
from friday.commands.suggesting import suggest
from friday.ingest.ics import Proposed
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app

# Monday 19 Oct 2026, 9am (the helpers' now).


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def propose(app: App, *fields: dict[str, Any], trusted: bool = False, source: str = "Mail") -> None:
    """What one letter or one feed read proposes, as the sync proposes it; then the sync's check of what waits."""
    n = len(app.table("raw_inputs"))
    app.do("document_add", name=f"{source} {n}.txt", content=f"read {n}")
    raw = app.table("raw_inputs")[-1]["id"]
    settings = load_settings(app.conn, 1)
    proposals = [Proposed("add", dict(f), fixed="start" in f) for f in fields]
    suggest(app.conn, settings, app.now_utc, 1, raw, proposals, trusted, source)
    sync(app.conn, app.now_utc)  # its check of what waits, as after any read


def waiting(app: App) -> dict[str, dict]:
    return {s["input"]["title"]: s for s in app.do("inbox")["suggestions"]}


def aside(app: App) -> dict[str, str]:
    return {s["title"]: s["why"] for s in app.do("inbox")["set_aside"]}


def task(title: str, due: str | None = None, **more: Any) -> dict[str, Any]:
    return {"title": title, "preset": "Assignment"} | ({"due": due} if due else {}) | more


def event(title: str, start: str, end: str) -> dict[str, Any]:
    return {"title": title, "preset": "Event", "start": start, "end": end}


class TestTasksYouHave:
    def test_the_same_title_due_the_same_day_is_set_aside(self, app: App) -> None:
        app.do("add", title="PS 4", due="2026-10-22T23:59", preset="Assignment")
        propose(app, task("PS 4", "2026-10-22T23:59"))
        assert waiting(app) == {} and aside(app) == {"PS 4": "You have PS 4"}

    def test_written_another_way_it_is_still_yours(self, app: App) -> None:
        app.do("add", title="Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]",
               due="2026-10-30T17:00", preset="Assignment")  # fmt: skip
        propose(
            app,
            task("WWA 7: Material Write-Up 'B' Draft", "2026-10-30T17:00"),
            task("PSYCH 1130 Weekly Writing Assignment 7", "2026-10-30T23:59"),
            task("Material write-up B draft (WWA7)", "2026-10-30T12:00"),
        )
        assert waiting(app) == {} and len(aside(app)) == 3

    def test_due_within_a_day_is_yours_and_two_days_apart_is_another(self, app: App) -> None:
        app.do("add", title="Reading response", due="2026-10-22T23:59", preset="Assignment")
        propose(app, task("Reading response", "2026-10-23T09:00"))
        assert "Reading response" in aside(app)
        propose(app, task("Reading response", "2026-10-29T23:59"))  # next week's: no number says it's this one
        assert "Reading response" in waiting(app) and waiting(app)["Reading response"]["duplicate_of"] is None

    def test_a_routine_a_full_day_later_is_the_next_days(self, app: App) -> None:
        app.do("add", title="Laundry", due="2026-10-22T20:00", preset="Errand")
        propose(app, task("Laundry", "2026-10-23T20:00"))  # the same time the next day: not this one
        assert "Laundry" in waiting(app) and aside(app) == {}

    def test_the_same_numbered_task_with_another_date_is_asked_as_moving_it(self, app: App) -> None:
        mine = app.do("add", title="A4: Interpretation and Simulation", due="2026-10-29T23:59", preset="Assignment")
        propose(app, task("[CS 2112] A4: Interpretation and Simulation", "2026-11-05T23:59"))
        moved = waiting(app)["[CS 2112] A4: Interpretation and Simulation"]
        assert moved["duplicate_of"] == mine["item"]["id"]
        app.do("suggestion_accept", id=moved["id"])
        (a4,) = [i for i in app.do("items") if "A4" in i["title"]]
        assert a4["due"] == "2026-11-05T23:59"  # moved, not made twice

    def test_without_a_date_it_is_yours_and_with_one_it_gives_yours_a_date(self, app: App) -> None:
        app.do("add", title="Core Values Impact", due="2026-11-20T17:00", preset="Assignment")
        propose(app, task("Core Values Impact (Required)"))
        assert "Core Values Impact (Required)" in aside(app)
        undated = app.do("add", title="Career Podcast Reflection", preset="Assignment", firmness="none")["item"]["id"]
        propose(app, task("Engineering Career Podcast Reflection", "2026-12-19T23:30"))
        assert waiting(app)["Engineering Career Podcast Reflection"]["duplicate_of"] == undated

    def test_another_number_course_or_part_is_asked(self, app: App) -> None:
        app.do("add", title="CHEM 2090 Problem Set 9", due="2026-10-28T23:59", preset="Assignment")
        app.do("add", title="Textbook Contribution A", due="2026-11-13T23:59", preset="Assignment")
        propose(
            app,
            task("CHEM 2090 Problem Set 10", "2026-10-28T23:59"),
            task("CHEM 2091 Problem Set 9", "2026-10-28T23:59"),
            task("Textbook Contribution B", "2026-11-13T23:59"),
        )
        assert set(waiting(app)) == {"CHEM 2090 Problem Set 10", "CHEM 2091 Problem Set 9", "Textbook Contribution B"}
        assert aside(app) == {}


class TestWhatYouFinished:
    def test_something_done_is_not_proposed_again(self, app: App) -> None:
        done = app.do("add", title="HRL survey", due="2026-10-30T23:59", preset="Errand")["item"]["id"]
        app.do("done", id=done)
        propose(app, task("HRL Survey", "2026-10-30T23:59"))
        assert aside(app) == {"HRL Survey": "Done: HRL survey"}

    def test_something_deleted_is_not_proposed_again(self, app: App) -> None:
        gone = app.do("add", title="Petition: MATH 2210 for MATH 2940", preset="Errand")["item"]["id"]
        app.do("drop", id=gone)
        propose(app, task("Petition MATH 2210 for MATH 2940"))
        assert aside(app) == {"Petition MATH 2210 for MATH 2940": "You deleted Petition: MATH 2210 for MATH 2940"}

    def test_a_numbered_task_you_did_stays_done_when_its_date_moves(self, app: App) -> None:
        done = app.do("add", title="A3 Oral Evaluation", due="2026-10-23T23:59", preset="Assignment")["item"]["id"]
        app.do("done", id=done)
        propose(app, task("A3 Oral Evaluation", "2026-10-30T23:59"))
        assert "A3 Oral Evaluation" in aside(app) and "A3 Oral Evaluation" not in waiting(app)

    def test_something_finished_long_ago_may_come_again(self, app: App) -> None:
        old = app.do("add", title="Course evaluation", due="2026-05-01T23:59", preset="Errand")["item"]["id"]
        app.do("done", id=old)
        app.conn.execute("UPDATE items SET updated_utc = '2026-05-02T00:00Z' WHERE id = ?", [old])
        propose(app, task("Course evaluation", "2026-12-01T23:59"))
        assert "Course evaluation" in waiting(app)


class TestEvents:
    def test_the_same_event_at_the_same_time_is_set_aside(self, app: App) -> None:
        app.do("add", title="A4dd", when="fixed", start="2026-10-20T21:00", end="2026-10-20T23:00")
        propose(app, event("A4dd", "2026-10-20T21:00", "2026-10-20T23:00"))
        assert aside(app) == {"A4dd": "You have A4dd"}

    def test_an_invitation_a_few_minutes_off_or_with_its_room_is_yours(self, app: App) -> None:
        app.do("add", title="CS 2112 Lecture", when="fixed", start="2026-10-20T10:10", end="2026-10-20T11:00")
        propose(app, event("CS 2112 Lecture (room 155)", "2026-10-20T10:15", "2026-10-20T11:00"))
        assert "CS 2112 Lecture (room 155)" in aside(app)

    def test_the_same_title_hours_or_a_week_apart_is_another_event(self, app: App) -> None:
        app.do("add", title="Salsa practice", when="fixed", start="2026-10-24T13:15", end="2026-10-24T14:30")
        propose(app, event("Salsa practice", "2026-10-24T18:00", "2026-10-24T19:00"))
        propose(app, event("Salsa practice", "2026-10-31T13:15", "2026-10-31T14:30"))
        assert aside(app) == {} and [s["input"]["start"] for s in app.do("inbox")["suggestions"]] == [
            "2026-10-24T18:00", "2026-10-31T13:15"]  # fmt: skip

    def test_an_event_is_never_a_task_of_the_same_name(self, app: App) -> None:
        app.do("add", title="CS A4 Design Doc", due="2026-10-29T23:59", preset="Assignment")
        propose(app, event("A4dd", "2026-10-27T21:00", "2026-10-27T23:00"))
        assert "A4dd" in waiting(app) and waiting(app)["A4dd"]["duplicate_of"] is None

    def test_a_trusted_calendars_copy_of_an_event_you_have_isnt_added_twice(self, app: App) -> None:
        app.do("add", title="Options Pricing Group Meeting", when="fixed", start="2026-10-21T19:00",
               end="2026-10-21T20:30")  # fmt: skip
        propose(app, event("Options Pricing Group Meeting", "2026-10-21T19:00", "2026-10-21T20:30"), trusted=True)
        assert len([r for r in app.table("items") if r["title"] == "Options Pricing Group Meeting"]) == 1


class TestTwoSourcesAtOnce:
    def test_the_same_thing_from_mail_and_from_canvas_is_asked_once(self, app: App) -> None:
        propose(app, task("Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]", "2026-10-30T17:00"),
                source="Canvas")  # fmt: skip
        propose(app, task("WWA 7: Material Write-Up 'B' Draft", "2026-10-30T17:00"), source="Mail")
        assert list(waiting(app)) == ["Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]"]
        assert aside(app) == {"WWA 7: Material Write-Up 'B' Draft": "Also waiting in your inbox"}

    def test_accepting_one_sets_aside_the_others_of_it(self, app: App) -> None:
        propose(app, task("Order Salsa merch", "2026-10-30T23:59"))
        app.do("add", title="Ignore me", preset="Errand")  # nothing to do with it
        sid = waiting(app)["Order Salsa merch"]["id"]
        app.do("suggestion_accept", id=sid)
        propose(app, task("Order salsa merch by Friday", "2026-10-30T20:00"))
        assert "Order salsa merch by Friday" in aside(app)


class TestWhatChangesWhileItWaits:
    def test_something_you_add_while_one_waits_sets_it_aside_at_the_next_read(self, app: App) -> None:
        propose(app, task("Pay Salsa dues", "2026-11-01T23:59"))
        assert "Pay Salsa dues" in waiting(app)
        app.do("add", title="Pay salsa dues", due="2026-11-01T20:00", preset="Errand")
        sync(app.conn, app.now_utc)
        assert "Pay Salsa dues" not in waiting(app) and "Pay Salsa dues" in aside(app)

    def test_a_repeating_events_next_time_is_never_a_duplicate_of_this_one(self, app: App) -> None:
        app.do("add", title="Chem Lecture", when="fixed", start="2026-10-21T12:20", end="2026-10-21T13:10")
        app.do("document_add", name="feed.txt", content="a feed")
        raw = app.table("raw_inputs")[-1]["id"]
        settings = load_settings(app.conn, 1)
        weekly = Proposed("add", event("Chem Lecture", "2026-10-28T12:20", "2026-10-28T13:10"), fixed=True, series="s1")
        suggest(app.conn, settings, app.now_utc, 1, raw, [weekly], False, "Canvas")
        assert aside(app) == {}  # next week's: not the one you have, a week from it
        same = Proposed("add", event("Chem Lecture", "2026-10-21T12:20", "2026-10-21T13:10"), fixed=True, series="s1")
        suggest(app.conn, settings, app.now_utc, 1, raw, [same], False, "Canvas")
        assert aside(app) == {"Chem Lecture": "You have Chem Lecture"}  # this week's is the one you have (29 Oct)


class TestAddingOneAnyway:
    def test_add_anyway_brings_it_back_and_it_stays_back(self, app: App) -> None:
        app.do("add", title="Lab report", due="2026-10-22T23:59", preset="Assignment")
        propose(app, task("Lab report", "2026-10-22T23:59"))
        sid = app.do("inbox")["set_aside"][0]["id"]
        app.do("suggestion_restore", id=sid)
        sync(app.conn, app.now_utc)  # the next read's check leaves it
        assert "Lab report" in waiting(app) and aside(app) == {}
        app.do("suggestion_accept", id=sid)
        assert len([i for i in app.do("items") if i["title"] == "Lab report"]) == 2  # you said so

    def test_only_one_set_aside_can_be_brought_back(self, app: App) -> None:
        propose(app, task("Fresh thing", "2026-10-22T23:59"))
        with pytest.raises(Exception, match="set aside"):
            app.do("suggestion_restore", id=waiting(app)["Fresh thing"]["id"])


def propose_series(app: App, series: str, *fields: dict[str, Any], source: str = "Calendar") -> None:
    """A calendar's repeating event: each instance proposed as one of `series`, as a calendar read proposes them."""
    n = len(app.table("raw_inputs"))
    app.do("document_add", name=f"{source} {n}.txt", content=f"read {n}")
    raw = app.table("raw_inputs")[-1]["id"]
    settings = load_settings(app.conn, 1)
    proposals = [Proposed("add", dict(f), fixed=True, series=series) for f in fields]
    suggest(app.conn, settings, app.now_utc, 1, raw, proposals, False, source)
    sync(app.conn, app.now_utc)


def statuses(app: App, title: str) -> list[str]:
    return [s["status"] for s in app.table("suggestions") if title in s["input"]]


SATURDAYS = [("2026-10-24T15:30", "2026-10-24T17:30"), ("2026-10-31T15:30", "2026-10-31T17:30"),
             ("2026-11-07T15:30", "2026-11-07T17:30")]  # fmt: skip


class TestRepeatingEvents:
    """29 Oct: 197 of 224 waiting suggestions were events already on the calendar, nearly all instances of repeating
    events from a second calendar, which were never checked against what you have."""

    def test_a_weekly_event_you_have_from_another_calendar_is_set_aside_every_week(self, app: App) -> None:
        for start, end in SATURDAYS:
            app.do("add", title="Open Table Tennis Practice (3rd floor, Appel)", when="fixed", start=start, end=end)
        propose_series(app, "ttp", *(event("Open Table Tennis Practice", s, e) for s, e in SATURDAYS))
        assert statuses(app, "Open Table Tennis Practice") == ["superseded"] * 3

    def test_a_weekly_event_you_don_t_have_is_still_asked(self, app: App) -> None:
        propose_series(app, "chess", *(event("Chess Club", s, e) for s, e in SATURDAYS))
        assert statuses(app, "Chess Club") == ["pending"] * 3

    def test_only_the_weeks_you_have_are_set_aside(self, app: App) -> None:
        start, end = SATURDAYS[0]
        app.do("add", title="Chess Club", when="fixed", start=start, end=end)
        propose_series(app, "chess", *(event("Chess Club", s, e) for s, e in SATURDAYS))
        assert statuses(app, "Chess Club") == ["superseded", "pending", "pending"]

    def test_waiting_weeks_are_set_aside_once_you_have_them(self, app: App) -> None:
        propose_series(app, "ttp", *(event("Open Table Tennis Practice", s, e) for s, e in SATURDAYS))
        for start, end in SATURDAYS:  # the same practice, from the other calendar, accepted meanwhile
            app.do("add", title="Open Table Tennis Practice (3rd floor, Appel)", when="fixed", start=start, end=end)
        sync(app.conn, app.now_utc)
        assert statuses(app, "Open Table Tennis Practice") == ["superseded"] * 3

    def test_the_same_series_from_two_calendars_is_asked_once(self, app: App) -> None:
        propose_series(app, "a", *(event("Cornell Poker", s, e) for s, e in SATURDAYS), source="Mine")
        propose_series(app, "b", *(event("Cornell Poker (Olin 245)", s, e) for s, e in SATURDAYS), source="School")
        assert statuses(app, "Cornell Poker") == ["pending"] * 3 + ["superseded"] * 3

    def test_a_week_you_skipped_is_yours_too(self, app: App) -> None:
        made = [app.do("add", title="Cornell Poker", when="fixed", start=s, end=e)["item"]["id"] for s, e in SATURDAYS]
        app.conn.execute("UPDATE items SET status = 'skipped' WHERE id = ?", [made[1]])  # not going that week
        propose_series(app, "poker", *(event("Cornell Poker", s, e) for s, e in SATURDAYS))
        assert statuses(app, "Cornell Poker") == ["superseded"] * 3

    def test_a_repeating_task_s_days_are_not_one_another_s_twins(self, app: App) -> None:
        settings = load_settings(app.conn, 1)
        app.do("document_add", name="Feed.txt", content="read")
        raw = app.table("raw_inputs")[-1]["id"]
        days = [task("Daily reflection", f"2026-10-2{d}T20:00") for d in (2, 3, 4)]
        suggest(
            app.conn, settings, app.now_utc, 1, raw, [Proposed("add", f, series="refl") for f in days], False, "Feed"
        )
        sync(app.conn, app.now_utc)
        assert statuses(app, "Daily reflection") == ["pending"] * 3
