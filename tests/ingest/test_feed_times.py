"""A calendar link's times, however its service writes them (11 Nov, checking the school and shift services' feeds:
their help pages don't say): in UTC (Moodle, Canvas), in a named zone (TZID), or floating (no zone at all, meant as
your own clock): each comes in at the same moment on your clock; a whole day is read as a day."""

from friday.ingest.ics import local

TZ = "America/New_York"


def test_utc_named_zone_floating_and_whole_day_times_land_on_your_clock() -> None:
    from icalendar import Calendar

    feed = Calendar.from_ical(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nUID:a\r\nDTSTART:20261023T210000Z\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:b\r\nDTSTART;TZID=America/Chicago:20261023T160000\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:c\r\nDTSTART:20261023T170000\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:d\r\nDTSTART;VALUE=DATE:20261023\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    starts = {str(e["UID"]): local(e.decoded("DTSTART"), TZ) for e in feed.walk("VEVENT")}
    assert starts["a"] == starts["b"] == starts["c"] == "2026-10-23T17:00", starts
    assert starts["d"] is None  # a whole day isn't a time: read as a day, by whole_days


def test_an_event_with_no_length_or_ending_before_it_starts_is_friday_s_smallest_block() -> None:
    """11 Nov: an event in a Family calendar (read as events) was refused, "end_utc: must be after the start"; such
    a moment comes in as fifteen minutes from its start. A calendar read by the rules still takes one as a due."""
    from friday.ingest.ics import classify, reading

    events = reading(r"\bdue\b", r"\bexam\b", r"\blecture\b", kind="Event")
    for end in ("2026-10-23T17:00", "2026-10-23T16:00"):
        (p,) = classify("Pick up Ani", "2026-10-23T17:00", end, None, None, events)
        assert (p.input["start"], p.input["end"]) == ("2026-10-23T17:00", "2026-10-23T17:15"), p.input
    rules = reading(r"\bdue\b", r"\bexam\b", r"\blecture\b")
    (due,) = classify("Problem set 5", "2026-10-23T23:59", "2026-10-23T23:59", None, None, rules)
    assert due.input == {"title": "Problem set 5", "preset": "Assignment", "due": "2026-10-23T23:59"}
