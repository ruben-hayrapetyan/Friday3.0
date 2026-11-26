"""A suggestion's evidence from a calendar event is the event in words (25 Nov, the user's screenshot: "Prep: MATH 1920
Final Exam" from the Mac's calendar showed {"end": {"dateTime": ...}, "summary": ...} under From the source; "the
evidence is just a raw json")."""

import json

from friday.commands.inbox import event_words, source_text

EXAM = json.dumps({"end": {"dateTime": "2026-12-13T10:30:00-06:00"}, "start": {"dateTime": "2026-12-13T08:00:00-06:00"},
                   "summary": "MATH 1920 Final Exam"})  # fmt: skip


def test_the_mac_calendars_event_is_said_in_words_on_your_clock() -> None:
    said = source_text({"content": EXAM, "kind": "mac", "media_type": "text/plain"}, "America/New_York")
    assert said == "MATH 1920 Final Exam\nSun 13 Dec, 9am–11:30am"
    assert "{" not in said and "dateTime" not in said


def test_its_title_is_as_written_so_the_quote_highlights_in_it() -> None:
    assert "MATH 1920 Final Exam" in event_words(EXAM, "America/New_York")


def test_whole_days_a_place_and_a_note_and_google_calendar_too() -> None:
    trip = json.dumps({"summary": "Trip", "start": {"date": "2026-12-20"}, "end": {"date": "2026-12-23"},
                       "location": "Boston", "description": "Bring the charger"})  # fmt: skip
    assert source_text({"content": trip, "kind": "gcal", "media_type": "application/json"}, "UTC") == (
        "Trip\nSun 20 Dec – Tue 22 Dec\nBoston\nBring the charger"
    )
    one_day = json.dumps({"summary": "Holiday", "start": {"date": "2026-12-25"}, "end": {"date": "2026-12-26"}})
    assert event_words(one_day, "UTC") == "Holiday\nFri 25 Dec, all day"


def test_an_ics_events_raw_lines_and_ordinary_text_are_as_before() -> None:
    assert (
        source_text({"content": "BEGIN:VEVENT\nSUMMARY:x\nEND:VEVENT", "kind": "ics", "media_type": "text/calendar"})
        is None
    )
    assert source_text({"content": "PS5 due Friday", "kind": "gmail", "media_type": "text/plain"}) == "PS5 due Friday"
