"""The sample term used the way a student would (M12c): connect Google with only the primary calendar named, pick
calendars in Settings, import the repeating ones in Repeating, read mail, go through the Inbox, plan, and live a
week while Google changes underneath."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.core.time import parse_utc
from friday.planner.service import replan
from friday.sim.sample import Sample, term, timed
from tests.commands.helpers import App, new_app

ON = {"school@g": None, "homework@g": "Assignment", "canvas@g": None, "personal@g": None, "extra@g": None}


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=14)
    app.do("settings_set", key="gcal", value={"read": ["primary"]})
    app.do("settings_set", key="gmail", value={"enabled": True})
    return app


@pytest.fixture
def sample(app: App) -> Sample:
    return term(date.fromisoformat(app.local_now()[:10]))


def read(app: App, sample: Sample) -> None:
    app.conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'sync_now', '1')")
    sync(app.conn, app.now_utc, google=sample.google, mail=sample.gmail, client=sample.ai)


def connect(app: App, sample: Sample) -> None:
    """The first sync, then the calendars switched on in Settings, then the sync that reads them."""
    read(app, sample)
    for calendar, kind in ON.items():
        app.do("calendar_set", id=calendar, on=True, **({"kind": kind} if kind else {}))
    read(app, sample)


def rows(app: App) -> dict[str, dict]:
    """Inbox suggestions by title."""
    return {s["input"]["title"]: s for s in app.do("inbox")["suggestions"]}


def repeats(app: App) -> dict[str, dict]:
    """Repeating events waiting in Settings → Repeating, by title."""
    return {r["title"]: r for r in app.do("calendar_repeats")}


def import_all(app: App) -> None:
    app.do("repeats_import", repeats=[{"batch": r["batch"]} for r in app.do("calendar_repeats")])


def test_the_primary_calendar_alone_brings_nothing_and_every_calendar_is_listed(app: App, sample: Sample) -> None:
    read(app, sample)
    listed = app.do("google_calendars")
    assert [c["name"] for c in listed][:3] == ["1. Projects", "2. To-Do", "3. Personal"]
    assert [c["name"] for c in listed if c["on"]] == ["1. Projects"]
    assert not any(s["source_kind"] == "gcal" for s in app.do("inbox")["suggestions"])


def test_each_calendar_is_read_as_its_kind_and_repeats_wait_in_repeating(app: App, sample: Sample) -> None:
    connect(app, sample)
    waiting = repeats(app)
    for course in ("CHEM 2090, Lecture", "MATH 1920, Discussion", "PHYS 1110, Laboratory", "ENGRG 1050, Seminar"):
        assert waiting[course]["kind"] == "Class" and waiting[course]["calendar"] == "4. School"
    assert waiting["MATH 1920, Lecture"]["pattern"] == "Every Mon, Wed and Fri, 11:15–12:05"
    assert waiting["Gym"]["kind"] == "Event" and waiting["CHEM Reading Response"]["kind"] == "Assignment"
    assert app.do("inbox")["repeats"] == len(waiting) == 13
    kinds = {title: s["input"]["preset"] for title, s in rows(app).items()}
    assert not set(kinds) & set(waiting)
    assert kinds["CHEM Prelim 2"] == "Exam" and kinds["Prep: CHEM Prelim 2"] == "Exam prep"
    assert kinds["Prep: MATH Quiz 2"] == "Exam prep" and "MATH Quiz 2" not in kinds
    assert kinds["Math HW8"] == kinds["PHYS Project Proposal (TWR)"] == "Assignment"
    assert rows(app)["PHYS 1110 Light Intensity Lab"]["input"]["due"].endswith("T23:30")  # the small model's title
    assert kinds["Startup Recruitment Expo"] == "Event" and kinds["Dentist"] == "Appointment"
    assert "Club social" not in kinds and "Career fair" not in kinds and "Halloween" not in kinds
    assert app.do("status")["suggestions"] == len(kinds)


def test_mail_reads_course_mail_and_notes_and_skips_receipts_newsletters_and_chat(app: App, sample: Sample) -> None:
    connect(app, sample)
    log = {m["subject"]: m for m in app.do("mail_log")}
    read_ones = sorted(s for s, m in log.items() if m["status"] == "read")
    assert read_ones == [
        "Action needed: submit your verification documents",
        "Prelim 2 Conflict Form",
        "RA APPLICATION REMINDER: Priority Due Date",
        "Re: Makeup Lab Report",
        "Robotics meeting moved",
        "[CS 1110] New Assignment Released",
        "[CS 1110] Prelim 1, Support Sessions, and A4",  # "prelim" in its subject
    ]
    assert all(m["why"] for m in log.values() if m["status"] == "skipped")
    titles = set(rows(app))
    assert {"CS 1110 A5", "RA application", "Makeup lab report", "Financial aid verification"} <= titles
    assert log["Robotics meeting moved"]["found"] == 0


def test_importing_puts_classes_in_the_plan_and_later_weeks_follow_on_their_own(app: App, sample: Sample) -> None:
    connect(app, sample)
    import_all(app)
    for suggestion in rows(app).values():
        app.do("suggestion_accept", id=suggestion["id"], edits={})
    assert app.do("inbox")["suggestions"] == [] and app.do("calendar_repeats") == []
    replan(app.conn, app.now_utc)
    lectures = [i for i in app.table("items") if i["title"] == "CHEM 2090, Lecture" and i["status"] == "todo"]
    assert lectures and {i["event_kind"] for i in lectures} == {"class"}
    assert any(i["start_utc"].endswith("T18:00Z") for i in lectures)  # next Wednesday's, moved to 14:00
    assert all(parse_utc(i["start_utc"]) >= app.now_utc - 24 * 60 for i in lectures)
    app.now_utc += 7 * 24 * 60
    later_on = sample.monday + timedelta(weeks=12)  # read for the first time now that it is 12 weeks ahead
    sample.google.calendars_by_id["school@g"].append(
        timed(f"chem_{later_on:%Y%m%d}", "CHEM 2090, Lecture", later_on, "12:20", "13:10")
        | {"recurringEventId": "chem"}
    )
    read(app, sample)
    assert app.do("calendar_repeats") == []
    later = [i for i in app.table("items") if i["title"] == "CHEM 2090, Lecture"]
    assert len(later) > len(lectures) and len({i["series_id"] for i in later}) == 1


def test_google_moving_or_cancelling_an_imported_class_applies_on_its_own(app: App, sample: Sample) -> None:
    connect(app, sample)
    app.do("repeats_import", repeats=[{"batch": "repeat:cs"}])
    before = sum(1 for i in app.table("items") if i["title"] == "CS 1110, Lecture" and i["status"] == "todo")
    school = sample.google.calendars_by_id["school@g"]
    ahead = sorted((e for e in school if e.get("recurringEventId") == "cs" and e["start"]["dateTime"] > "2026-10-20"),
                   key=lambda e: e["start"]["dateTime"])  # fmt: skip
    moved, cancelled = ahead[0], ahead[1]
    moved["start"]["dateTime"] = moved["start"]["dateTime"].replace("11:15", "16:00")
    moved["end"]["dateTime"] = moved["end"]["dateTime"].replace("12:05", "16:50")
    school.remove(cancelled)
    app.now_utc += 60
    read(app, sample)
    assert not [s for s in app.do("inbox")["suggestions"] if s["origin"] == "CS 1110, Lecture"]
    lectures = [i for i in app.table("items") if i["title"] == "CS 1110, Lecture" and i["status"] == "todo"]
    assert len(lectures) == before - 1 and any(i["start_utc"].endswith("T20:00Z") for i in lectures)


def test_a_calendar_switched_off_leaves_the_inbox_and_its_kind_can_change(app: App, sample: Sample) -> None:
    connect(app, sample)
    app.do("calendar_set", id="personal@g", on=False)
    assert "Dentist" not in rows(app) and "Gym" not in repeats(app)
    app.do("calendar_set", id="personal@g", on=True, kind="Class")
    read(app, sample)
    assert rows(app)["Dentist"]["input"]["preset"] == "Class" and repeats(app)["Gym"]["kind"] == "Class"


def test_imported_repeats_are_listed_in_repeating_and_can_be_switched_off(app: App, sample: Sample) -> None:
    connect(app, sample)
    app.do("area_add", name="Chemistry")
    app.do("repeats_import", repeats=[{"batch": "repeat:reading", "area": "Chemistry"}, {"batch": "repeat:chem"}])
    responses = [i for i in app.table("items") if i["title"] == "CHEM Reading Response"]
    assert len(responses) > 1 and len({i["series_id"] for i in responses}) == 1
    assert responses[0]["preset"] == "Assignment" and responses[0]["due_utc"]
    listed = {s["title"]: s for s in app.do("series_list")}
    assert listed["CHEM Reading Response"]["area"] == "Chemistry"
    assert listed["CHEM 2090, Lecture"]["external"] and listed["CHEM 2090, Lecture"]["source"] == "4. School"
    app.do("series_stop", id=listed["CHEM 2090, Lecture"]["id"])
    app.do("materialize")
    open_lectures = [i for i in app.table("items") if i["title"] == "CHEM 2090, Lecture" and i["status"] == "todo"]
    assert all(parse_utc(i["start_utc"]) < app.now_utc for i in open_lectures)


def test_an_imported_class_can_be_tagged_afterwards_but_not_moved(app: App, sample: Sample) -> None:
    connect(app, sample)
    app.do("repeats_import", repeats=[{"batch": "repeat:chem"}])
    app.do("area_add", name="CHEM 2090")
    lecture = next(s for s in app.do("series_list") if s["title"] == "CHEM 2090, Lecture")
    app.do("series_edit", id=lecture["id"], area="CHEM 2090")
    assert next(s for s in app.do("series_list") if s["id"] == lecture["id"])["area"] == "CHEM 2090"
    tagged = {i["area_id"] for i in app.table("items") if i["title"] == "CHEM 2090, Lecture" and i["status"] == "todo"}
    assert len(tagged) == 1 and None not in tagged
    with pytest.raises(FieldError):
        app.do("series_edit", id=lecture["id"], start="2026-10-23T09:00")
