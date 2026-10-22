"""How Google events are read (DESIGN §22.2): due work, exams with prep, classes and commitments by the ingest
patterns or the kind a calendar names; a repeating event is one inbox card, and what you say to it holds for its
later instances."""

import json
from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def all_day(eid: str, summary: str, day: str, until: str) -> dict:
    return {"id": eid, "summary": summary, "start": {"date": day}, "end": {"date": until}}


def lecture(n: int, day: str) -> dict:
    return event(f"chem_{n}", "CHEM 2090, Lecture", f"{day}T12:20", f"{day}T13:10", recurringEventId="chem")


def read(app: App, google: FakeGoogle, minutes_later: int = 0) -> None:
    app.do("settings_set", key="gcal", value={"read": ["School"]})
    sync(app.conn, app.now_utc + minutes_later, google=google)


def cards(app: App) -> list[tuple[str, str, str | None]]:
    return [(s["input"]["title"], s["input"]["preset"], s["batch"]) for s in app.do("inbox")["suggestions"]]


def test_events_are_read_as_due_work_exams_with_prep_classes_and_commitments(app: App) -> None:
    school = [
        all_day("hw", "Math HW8 Due", "2026-10-22", "2026-10-23"),
        event("lab", "Light Intensity Lab [PHYS1110]", "2026-10-24T23:30", "2026-10-24T23:30"),
        event("prelim", "CHEM Prelim 2", "2026-10-22T19:30", "2026-10-22T21:00"),
        all_day("quiz", "MATH Quiz 2", "2026-10-20", "2026-10-21"),
        event("disc", "MATH 1920, Discussion", "2026-10-20T14:30", "2026-10-20T15:20"),
        event("expo", "Startup Expo", "2026-10-20T15:00", "2026-10-20T19:00"),
        all_day("break", "Fall break", "2026-10-23", "2026-10-25"),
    ]
    read(app, FakeGoogle({"School@group": school}))
    by_title = {s["input"]["title"]: s["input"] for s in app.do("inbox")["suggestions"]}
    assert by_title["Math HW8"] == {"title": "Math HW8", "preset": "Assignment", "due": "2026-10-22T23:59"}
    assert by_title["Light Intensity Lab [PHYS1110]"]["due"] == "2026-10-24T23:30"
    assert by_title["CHEM Prelim 2"]["preset"] == "Exam"
    assert by_title["Prep: CHEM Prelim 2"] == {
        "title": "Prep: CHEM Prelim 2",
        "preset": "Exam prep",
        "due": "2026-10-22T19:30",
    }
    assert by_title["Prep: MATH Quiz 2"]["due"] == "2026-10-19T23:59" and "MATH Quiz 2" not in by_title
    assert by_title["MATH 1920, Discussion"]["preset"] == "Class"
    assert by_title["Startup Expo"]["preset"] == "Event"
    assert "Fall break" not in by_title


def test_a_calendar_that_names_a_kind_reads_every_event_as_it(app: App) -> None:
    google = FakeGoogle({"School@group": [all_day("p", "PHYS Project Proposal", "2026-10-24", "2026-10-25")]})
    read(app, google)
    app.conn.execute("UPDATE sources SET config = json_set(config, '$.kind', 'Project') WHERE name = 'School'")
    app.conn.execute("DELETE FROM raw_inputs")
    read(app, google, minutes_later=60)
    assert cards(app) == [("PHYS Project Proposal", "Project", None)]
    assert json.loads(app.table("sources")[0]["config"])["kind"] == "Project"  # reading again keeps it


def test_a_repeating_event_waits_in_repeating_rather_than_the_inbox(app: App) -> None:
    google = FakeGoogle({"School@group": [lecture(1, "2026-10-19"), lecture(2, "2026-10-21")]})
    read(app, google)
    assert cards(app) == [] and app.do("inbox")["repeats"] == 1 and app.do("status")["suggestions"] == 0
    [found] = app.do("calendar_repeats")
    assert found["title"] == "CHEM 2090, Lecture" and found["kind"] == "Class" and found["calendar"] == "School"
    assert found["pattern"] == "Every Mon and Wed, 12:20–13:10" and found["count"] == 2


def test_an_imported_repeat_is_one_series_with_your_tag_and_kind_and_its_later_times_follow(app: App) -> None:
    app.do("area_add", name="Chemistry")
    google = FakeGoogle({"School@group": [lecture(1, "2026-10-19"), lecture(2, "2026-10-21")]})
    read(app, google)
    app.do("repeats_import", repeats=[{"batch": "repeat:chem", "area": "Chemistry", "kind": "Event"}])
    google.calendars_by_id["School@group"].append(lecture(3, "2026-10-23"))
    read(app, google, minutes_later=60)
    lectures = [i for i in app.table("items") if i["title"] == "CHEM 2090, Lecture"]
    assert [i["start_utc"] for i in lectures] == ["2026-10-19T16:20Z", "2026-10-21T16:20Z", "2026-10-23T16:20Z"]
    assert len({i["series_id"] for i in lectures}) == 1 and {i["event_kind"] for i in lectures} == {"other"}
    assert app.do("calendar_repeats") == [] and cards(app) == []
    [series] = app.do("series_list")
    assert series["external"] and series["area"] == "Chemistry" and series["source"] == "School"


def test_moves_and_cancellations_of_an_imported_repeat_apply_on_their_own(app: App) -> None:
    google = FakeGoogle(
        {"School@group": [lecture(1, "2026-10-19"), lecture(2, "2026-10-21"), lecture(3, "2026-10-23")]}
    )
    read(app, google)
    app.do("repeats_import", repeats=[{"batch": "repeat:chem"}])
    school = google.calendars_by_id["School@group"]
    school[0] = lecture(1, "2026-10-19") | {"start": {"dateTime": "2026-10-19T15:00:00-04:00"}}
    school[0]["end"] = {"dateTime": "2026-10-19T15:50:00-04:00"}
    del school[2]
    read(app, google, minutes_later=60)
    assert cards(app) == []
    open_ones = [
        i["start_utc"] for i in app.table("items") if i["title"] == "CHEM 2090, Lecture" and i["status"] == "todo"
    ]
    assert open_ones == ["2026-10-19T19:00Z", "2026-10-21T16:20Z"]


def test_switching_an_imported_repeat_off_removes_it_and_on_brings_it_back(app: App) -> None:
    google = FakeGoogle({"School@group": [lecture(1, "2026-10-20"), lecture(2, "2026-10-22")]})
    read(app, google)
    app.do("repeats_import", repeats=[{"batch": "repeat:chem"}])
    series = app.do("series_list")[0]["id"]
    app.do("series_stop", id=series)
    google.calendars_by_id["School@group"].append(lecture(3, "2026-10-23"))
    read(app, google, minutes_later=60)

    def open_lectures() -> int:
        return sum(1 for i in app.table("items") if i["title"] == "CHEM 2090, Lecture" and i["status"] == "todo")

    assert open_lectures() == 0 and app.do("calendar_repeats") == []
    app.do("series_resume", id=series)
    read(app, google, minutes_later=120)
    assert open_lectures() == 3


def test_an_imported_repeat_keeps_its_calendar_and_times_when_switched_off(app: App) -> None:
    google = FakeGoogle({"School@group": [lecture(1, "2026-10-20"), lecture(2, "2026-10-22")]})
    read(app, google)
    app.do("repeats_import", repeats=[{"batch": "repeat:chem"}])
    app.do("series_stop", id=app.do("series_list")[0]["id"])
    [series] = app.do("series_list")
    assert series["source"] == "School" and series["external"] and not series["active"]
    assert series["pattern"] == "Every Tue and Thu, 12:20–13:10"
