"""The full audit, 8 Nov ("do a full audit of all of the features of this app in depth"): one test for each bug it
found in tasks, quick-add, the planner and calendars, through the commands the app sends."""

from datetime import datetime
from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.core.calendars import STARTER_CATEGORIES, CategorySettings, category_of
from friday.core.items import FieldError
from friday.core.recurrence import is_valid_rule, occurrences
from friday.planner.service import replan
from friday.sim.fakes import FakeGoogle, event, repeated
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_quick_add_reads_the_kind_from_the_title(app: App) -> None:
    """ "quiz prep 2h due tue" was an Assignment, so planned after the quiz."""
    assert app.do("add", text="quiz prep 2h due tue")["item"]["preset"] == "Exam prep"


def test_todays_work_counts_toward_todays_cap(app: App) -> None:
    app.do("settings_set", key="daily_cap", value=dict.fromkeys(["mon", "tue", "wed", "thu", "fri", "sat", "sun"], 3.0))
    essay = app.do("add", text="essay 6h due fri")["item"]["id"]
    app.do("start", id=essay)
    app.at("2026-10-19T12:00").do("stop")  # 3 h timed today
    replan(app.conn, app.now_utc)
    today = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T04:00")["blocks"]
    assert [b for b in today if b["start"] >= "2026-10-19T12:00"] == []


def test_a_new_length_is_your_estimate(app: App) -> None:
    essay = app.do("add", title="essay", duration_min=240, due="2026-10-23T17:00")["item"]["id"]
    app.do("edit", id=essay, duration_min=60)
    row = next(r for r in app.table("items") if r["id"] == essay)
    assert row["your_estimate_units"] == row["duration_units"] == 4


def test_no_due_date_is_no_deadline(app: App) -> None:
    essay = app.do("add", title="essay", preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
    out = app.do("edit", id=essay, due=None)["item"]
    assert out["due"] is None and out["firmness"] == "none"


def test_undoing_an_add_doesnt_take_the_work_timed_on_it(app: App) -> None:
    added = app.full("add", payload={"text": "essay 3h due fri"}, provisional=False)
    app.do("start", id=added.result["item"]["id"])
    app.at("2026-10-19T11:00").do("stop")
    with pytest.raises(FieldError, match="worked on it since"):
        app.do("undo", command_id=added.command_id)


@pytest.mark.parametrize(
    ("text", "title", "due"),
    [("report due 5pm fri", "report", "2026-10-23T17:00"), ("read pages 10-20", "read pages 10-20", None),
     ("hw problems 1-5 due fri", "hw problems 1-5", "2026-10-23T23:59"), ("lab 2-5", "lab 2-5", None)],
)  # fmt: skip
def test_a_day_after_a_time_and_numbers_that_arent_days(app: App, text: str, title: str, due: str | None) -> None:
    item = app.do("add", text=text)["item"]
    assert (item["title"], item["due"]) == (title, due)


def test_after_midnight_a_time_is_on_the_day_that_has_begun(app: App) -> None:
    app.at("2026-10-20T01:00")
    assert app.do("add", text="meeting at 2am")["item"]["start"] == "2026-10-20T02:00"
    assert app.do("add", text="essay due today")["item"]["due"] == "2026-10-20T23:59"


def test_a_dropped_one_isnt_done(app: App) -> None:
    item = app.do("add", text="x 1h")["item"]["id"]
    app.do("drop", id=item)
    with pytest.raises(FieldError, match="dropped"):
        app.do("done", id=item)


def test_switching_off_a_calendars_repeat_leaves_the_calendar_alone(app: App) -> None:
    master = event("w1", "Office hours", "2026-10-20T15:00", "2026-10-20T16:00")
    google = FakeGoogle({"Classes@group": repeated(master, "FREQ=WEEKLY", times=30)}, rules={"w1": "FREQ=WEEKLY"})
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc, google=google)
    (series,) = app.table("series")
    app.do("series_stop", id=series["id"])
    write_events(app.conn, app.now_utc, google=google)
    assert len(google.calendars_by_id["Classes@group"]) == 30


def test_an_end_written_in_utc_is_a_repeat() -> None:
    rule = "FREQ=WEEKLY;UNTIL=20261210T150000Z;BYDAY=TU,TH"
    times = occurrences(rule, datetime(2026, 10, 20, 10), datetime(2026, 10, 20), datetime(2027, 1, 1))
    assert is_valid_rule(rule) and len(times) == 16 and times[-1] == datetime(2026, 12, 10, 10)


@pytest.mark.parametrize(
    ("title", "category"),
    [("Flight UA 1234", "Travel"), ("Interview at Suite 1200", "Meeting"), ("New Year's party 2026", "Social"),
     ("Final Fantasy movie night", "Social"), ("CS 2110 Lecture", "Class"), ("MATH 1920 Final exam", "Exam")],
)  # fmt: skip
def test_starter_categories_dont_take_numbers_for_courses(title: str, category: str) -> None:
    found = category_of(title, CategorySettings(categories=STARTER_CATEGORIES))
    assert found is not None and found.name == category
