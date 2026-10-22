"""Calendar feeds by fixed rules, and LLM extraction checked against its source (DESIGN §22.2, §22.5)."""

from datetime import date

from friday.ingest import extract, ics
from tests.ingest.fakes import FEED, FakeClient

TZ = "America/New_York"


def test_a_feed_gives_a_repeating_class_an_assignment_and_a_todo_and_skips_all_day_events() -> None:
    found = {
        f.external_id: f for f in ics.parse_feed(FEED, TZ, ics.reading(r"^(due|deadline)[: ]", r"exam", r"lecture"))
    }
    lecture = found["lecture-1"].proposals[0]
    assert lecture.fixed and lecture.input["preset"] == "Class" and lecture.input["start"] == "2026-10-20T10:00"
    assert lecture.input["every"].startswith("rrule:FREQ=WEEKLY")
    ps4 = found["ps4"].proposals[0].input
    assert ps4 == {"title": "PS4", "preset": "Assignment", "due": "2026-10-22T23:59"}
    assert found["holiday"].proposals == []
    assert found["essay"].proposals[0].input["due"] == "2026-10-30T23:59"


def test_extraction_keeps_only_dates_quoted_from_the_source() -> None:
    mail = "Hi all, Problem Set 5 is due Friday Oct 23 at 5pm. See you in lecture."
    answer = {
        "is_syllabus": False,
        "items": [
            {
                "title": "PS5",
                "preset": "Assignment",
                "due": "2026-10-23T17:00",
                "confidence": 0.9,
                "quotes": {"title": "Problem Set 5", "due": "due Friday Oct 23 at 5pm"},
            },
            {
                "title": "Quiz",
                "preset": "Assignment",
                "due": "2026-10-24T09:00",
                "confidence": 0.9,
                "quotes": {"due": "quiz on Saturday"},
            },
        ],
    }
    client = FakeClient(answer)
    found, syllabus, tokens = extract.extract(
        client, "m", mail, "text/plain", date(2026, 10, 19), TZ, ["CS"], ["Assignment"]
    )
    assert not syllabus and tokens == 1000
    assert found[0].input["due"] == "2026-10-23T17:00" and found[0].confidence == 0.9
    assert "due" not in found[1].input and found[1].confidence < 0.9  # its quote isn't in the mail
    assert client.calls[0]["output_config"]["format"]["schema"] is extract.PROPOSE


def test_a_pdf_goes_to_the_model_as_a_document_and_its_unchecked_quotes_lower_confidence() -> None:
    answer = {
        "is_syllabus": True,
        "items": [
            {
                "title": "Midterm",
                "preset": "Event",
                "start": "2026-11-05T14:00",
                "end": "2026-11-05T16:00",
                "confidence": 0.95,
                "quotes": {"start": "Nov 5, 2-4pm"},
            }
        ],
    }
    client = FakeClient(answer)
    found, syllabus, _ = extract.extract(client, "m", "JVBERi0=", "application/pdf", date(2026, 10, 19), TZ, [], [])
    assert syllabus and found[0].confidence == extract.UNCHECKED_CONFIDENCE
    assert client.calls[0]["messages"][0]["content"][0]["type"] == "document"
