"""Repeats made by hand (8 Nov, a user: "when creating new events manually, they don't repeat as they should"; and
"check all of the manual actions in depth"). Each test is one bug an audit of every manual action found, through the
commands the app sends, against a stand-in Google where a calendar is part of it."""

from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.core.series import Series, occurrence_timing
from friday.core.time import parse_utc, to_local
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import TZ, App, new_app

ASIDE = {"color": None, "notes": "", "location": None}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now="2026-11-08T15:00")


def local(item: dict) -> str:
    return f"{to_local(parse_utc(item['start_utc'] or item['due_utc']), TZ):%a %Y-%m-%d %H:%M}"


def todo(app: App, title: str) -> list[dict]:
    found = [i for i in app.table("items") if i["title"] == title and i["status"] == "todo"]
    return sorted(found, key=lambda i: i["start_utc"] or i["due_utc"])


def with_google(app: App, read: list[str]) -> FakeGoogle:
    google = FakeGoogle({"Classes@group": [event("a1", "Lecture", "2026-11-10T10:00", "2026-11-10T11:15")]})
    app.do("settings_set", key="gcal", value={"read": read, "trusted": read})
    sync(app.conn, app.now_utc, google=google)
    app.do("settings_set", key="gcal", value={"read": read, "trusted": read, "new_events_to": "Classes@group"})
    return google


@pytest.mark.parametrize("read", [["Classes"], []])
def test_an_event_made_here_and_saved_to_google_repeats_here_at_once(app: App, read: list[str]) -> None:
    """The user's bug: made, saved to Google, then made to repeat, Friday showed one time (until its next read of
    that calendar, or for good when it didn't read it), as the repeat was handed to Google."""
    google = with_google(app, read)
    chess = app.do("add", title="Chess", when="fixed", start="2026-11-11T19:00", end="2026-11-11T20:00", **ASIDE)
    write_events(app.conn, app.now_utc, google=google)
    app.do("repeat", id=chess["item"]["id"], every="rrule:FREQ=WEEKLY;BYDAY=WE")
    times = todo(app, "Chess")
    assert len(times) > 10 and {local(t)[:3] for t in times} == {"Wed"} and local(times[0]) == "Wed 2026-11-11 19:00"
    queued = [w for w in app.table("event_writes") if w["done_utc"] is None]
    assert len(queued) == len(times) - 1 and all(w["op"] == "save" for w in queued)  # each later time to Google too


def test_an_only_friday_repeat_stays_only_in_friday_when_one_time_changes(app: App) -> None:
    google = with_google(app, ["Classes"])
    app.do("add", title="Gym", when="fixed", start="2026-11-10T07:00", end="2026-11-10T08:00",
           every="rrule:FREQ=WEEKLY;BYDAY=TU", calendar="", **ASIDE)  # fmt: skip
    first = todo(app, "Gym")[0]
    app.do("edit", id=first["id"], start="2026-11-10T08:00", end="2026-11-10T09:00")  # dragged
    app.do("edit", id=first["id"], blocks_time=False)  # "Not going"
    write_events(app.conn, app.now_utc, google=google)
    assert app.table("event_writes") == [] and len(google.calendars_by_id["Classes@group"]) == 1


def test_stopped_then_started_on_a_calendar_its_times_come_back(app: App) -> None:
    google = with_google(app, ["Classes"])
    made = app.do("add", title="Gym", when="fixed", start="2026-11-10T07:30", end="2026-11-10T08:30",
                  every="rrule:FREQ=WEEKLY;BYDAY=TU", **ASIDE)  # fmt: skip
    write_events(app.conn, app.now_utc, google=google)
    before = len(todo(app, "Gym"))
    app.do("series_stop", id=made["series_id"])
    write_events(app.conn, app.now_utc, google=google)  # the deletes go out
    assert todo(app, "Gym") == []
    app.do("series_resume", id=made["series_id"])
    assert len(todo(app, "Gym")) == before  # not 17 empty weeks
    write_events(app.conn, app.now_utc, google=google)
    assert sum(e.get("summary") == "Gym" for e in google.calendars_by_id["Classes@group"]) == before


def test_a_repeat_starting_far_ahead_has_its_first_time(app: App) -> None:
    made = app.do("add", title="Mom's birthday", when="fixed", start="2027-06-10T00:00", end="2027-06-11T00:00",
                  every="rrule:FREQ=YEARLY", **ASIDE)  # fmt: skip
    assert made["occurrences"] == 1 and [local(t) for t in todo(app, "Mom's birthday")] == ["Thu 2027-06-10 00:00"]
    one = app.do("add", title="Recital", when="fixed", start="2027-04-01T18:00", end="2027-04-01T19:00", **ASIDE)
    app.do("repeat", id=one["item"]["id"], every="rrule:FREQ=YEARLY")
    assert [i["series_id"] is not None for i in todo(app, "Recital")] == [True]  # joined its repeat, no second


def test_a_repeating_task_comes_due_on_its_own_day(app: App) -> None:
    app.do("add", text="Pay rent", due="2026-12-01T09:00", every="rrule:FREQ=MONTHLY")
    assert [local(t) for t in todo(app, "Pay rent")][:4] == [
        "Tue 2026-12-01 09:00", "Fri 2027-01-01 09:00", "Mon 2027-02-01 09:00", "Mon 2027-03-01 09:00",
    ]  # fmt: skip


def test_the_repeat_chosen_beats_one_in_the_text(app: App) -> None:
    made = app.do("add", text="Run every tue", every="day")
    rule = next(s["rrule"] for s in app.table("series") if s["id"] == made["series_id"])
    assert rule == "FREQ=DAILY"


def test_ends_after_n_times_keeps_counting_after_a_split(app: App) -> None:
    made = app.do("add", title="Course", when="fixed", start="2026-11-10T18:00", end="2026-11-10T19:00",
                  every="rrule:FREQ=WEEKLY;BYDAY=TU;COUNT=10", **ASIDE)  # fmt: skip
    app.do("series_edit", id=made["series_id"], every="rrule:FREQ=WEEKLY;BYDAY=TU,TH;COUNT=10",
           from_date="2026-12-08")  # the 5th: four held before it  # fmt: skip
    assert len(todo(app, "Course")) == 4 + 6


def test_a_new_day_and_pattern_from_one_time_on_is_one_split(app: App) -> None:
    """Moved to Wednesday with "Every week on Wednesday", this and later: every Wednesday was there twice."""
    made = app.do("add", title="Club", when="fixed", start="2026-11-10T18:00", end="2026-11-10T19:00",
                  every="rrule:FREQ=WEEKLY;BYDAY=TU", **ASIDE)  # fmt: skip
    app.do("series_edit", id=made["series_id"], every="rrule:FREQ=WEEKLY;BYDAY=WE", from_date="2026-12-08",
           start="2026-12-09T17:00", end="2026-12-09T18:30", title="Club")  # fmt: skip
    times = [local(t) for t in todo(app, "Club")]
    assert not [t for t, n in Counter(times).items() if n > 1]
    after = [t for t in times if t[4:14] >= "2026-12-08"]
    assert after[:2] == ["Wed 2026-12-09 17:00", "Wed 2026-12-16 17:00"]


def test_a_length_is_real_minutes_when_the_clocks_change() -> None:
    series = Series(1, {"when": "fixed", "length_min": 60}, "FREQ=DAILY", "2027-03-12T02:30", "2027-03-01T00:00Z")
    forward = occurrence_timing(series, datetime(2027, 3, 14, 2, 30), TZ)  # 2:30 doesn't exist that night
    assert parse_utc(forward["end_utc"]) - parse_utc(forward["start_utc"]) == 60
    allday = Series(2, {"when": "fixed", "length_min": 1440}, "FREQ=DAILY", "2027-03-13T00:00", "2027-03-01T00:00Z")
    whole = occurrence_timing(allday, datetime(2027, 3, 14), TZ)  # a 23-hour day, still midnight to midnight
    assert parse_utc(whole["end_utc"]) - parse_utc(whole["start_utc"]) == 23 * 60


def test_the_event_you_placed_stays_when_the_repeat_leaves_its_day_out(app: App) -> None:
    app.do("add", title="Shift", when="fixed", start="2026-11-14T10:00", end="2026-11-14T11:00",
           every="rrule:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", **ASIDE)  # a Saturday's, every weekday  # fmt: skip
    times = [local(t) for t in todo(app, "Shift")]
    assert times[0] == "Sat 2026-11-14 10:00" and times[1] == "Mon 2026-11-16 10:00"
