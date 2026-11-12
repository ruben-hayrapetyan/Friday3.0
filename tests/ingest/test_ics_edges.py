"""Calendar feeds at the edges: an event or to-do with no title or no date proposes nothing, a feed is fetched over
HTTP (redirects followed, a refusal raised), and an event read again as another kind keeps being free."""

import httpx
import pytest

from friday.ingest import ics

TZ = "America/New_York"
READ = ics.reading(r"^(due|deadline)[: ]", r"exam", r"lecture")


def feed(*components: str) -> str:
    return "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\n" + "".join(components) + "END:VCALENDAR\n"


def test_an_event_or_todo_without_a_title_or_a_date_proposes_nothing() -> None:
    text = feed(
        "BEGIN:VEVENT\nUID:nameless\nDTSTART:20261020T140000Z\nEND:VEVENT\n",
        "BEGIN:VEVENT\nUID:undated\nSUMMARY:Party\nEND:VEVENT\n",
        "BEGIN:VTODO\nUID:no-due\nSUMMARY:Essay draft\nEND:VTODO\n",
        "BEGIN:VTODO\nUID:no-title\nDUE;VALUE=DATE:20261030\nEND:VTODO\n",
    )
    found = {f.external_id: f for f in ics.parse_feed(text, TZ, READ)}
    assert set(found) == {"nameless", "undated", "no-due", "no-title"}
    assert all(f.proposals == [] for f in found.values())
    assert found["nameless"].event is None


def test_a_todo_read_as_another_kind_keeps_the_proposals_it_had() -> None:
    text = feed("BEGIN:VTODO\nUID:essay\nSUMMARY:Essay draft\nDUE;VALUE=DATE:20261030\nEND:VTODO\n")
    (essay,) = ics.parse_feed(text, TZ, READ)
    assert essay.as_kind("Reading", "Essay draft") == essay.proposals


def test_a_free_event_read_again_as_a_class_is_still_free() -> None:
    event = {
        "id": "g1",
        "summary": "Office hours",
        "start": {"dateTime": "2026-10-20T14:00:00+00:00"},
        "end": {"dateTime": "2026-10-20T15:00:00+00:00"},
        "transparency": "transparent",
    }
    found = ics.google_event(event, TZ, READ)
    assert found is not None
    again = found.as_kind("Class", "Office hours")
    assert again and all(p.input.get("free") is True for p in again if p.fixed)


def test_a_feed_is_fetched_and_a_refusal_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, dict]] = []

    def get(url: str, **options: object) -> httpx.Response:
        asked.append((url, options))
        status = 404 if "gone" in url else 200
        return httpx.Response(status, text="BEGIN:VCALENDAR", request=httpx.Request("GET", url))

    monkeypatch.setattr(ics.httpx, "get", get)
    assert ics.fetch("https://example.test/cal.ics") == "BEGIN:VCALENDAR"
    assert asked[0][1]["follow_redirects"] is True
    with pytest.raises(httpx.HTTPStatusError):
        ics.fetch("https://example.test/gone.ics")


def test_an_all_day_event_with_no_end_lasts_its_one_day() -> None:
    # RFC 5545: a DATE start with neither DTEND nor DURATION is one day long; it came in ending as it started, a
    # whole-day event of no length
    text = feed("BEGIN:VEVENT\nUID:holiday\nSUMMARY:Fall break\nDTSTART;VALUE=DATE:20261120\nEND:VEVENT\n")
    (holiday,) = ics.parse_feed(text, TZ, ics.reading(r"^due", r"exam", r"lecture", all_day=True))
    assert holiday.proposals[0].input | {"location": None} == {
        "title": "Fall break", "preset": "Event", "start": "2026-11-20T00:00", "end": "2026-11-21T00:00",
        "blocks_time": False, "location": None,
    }  # fmt: skip


def test_one_time_of_a_repeat_moved_in_the_feed_is_there_once() -> None:
    # A feed moves one time of a repeat by a second VEVENT with the same UID and a RECURRENCE-ID: the repeat skips
    # that time, as it does an EXDATE, or the lecture showed both at 10:00 Monday and at 2:00 Tuesday
    text = feed(
        "BEGIN:VEVENT\nUID:lecture\nSUMMARY:Lecture\nDTSTART;TZID=America/New_York:20261102T100000\n"
        "DTEND;TZID=America/New_York:20261102T110000\nRRULE:FREQ=WEEKLY;COUNT=4\n"
        "EXDATE;TZID=America/New_York:20261123T100000\nEND:VEVENT\n",
        "BEGIN:VEVENT\nUID:lecture\nSUMMARY:Lecture\nRECURRENCE-ID;TZID=America/New_York:20261109T100000\n"
        "DTSTART;TZID=America/New_York:20261110T140000\nDTEND;TZID=America/New_York:20261110T150000\nEND:VEVENT\n",
    )
    found = {f.external_id: f for f in ics.parse_feed(text, TZ, READ)}
    series = found["lecture"].proposals[0].input["every"]
    assert series == "rrule:FREQ=WEEKLY;COUNT=4;EXDATE=20261109T100000,20261123T100000"
    moved = found["lecture#2026-11-09T10:00:00-05:00"].proposals[0].input
    assert (moved["start"], moved["end"]) == ("2026-11-10T14:00", "2026-11-10T15:00")
