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


def test_a_syllabus_reading_is_asked_for_and_its_pages_give_its_length() -> None:
    syllabus = "Week 3, Tue Oct 20 10:00: Lecture 5. Read Chapter 4, pp. 85-112, before class."
    answer = {
        "is_syllabus": True,
        "items": [
            {
                "title": "Read ch. 4",
                "preset": "Reading",
                "due": "2026-10-20T10:00",
                "pages": 28,
                "confidence": 0.85,
                "quotes": [{"field": "due", "words": "Tue Oct 20 10:00"}, {"field": "pages", "words": "pp. 85-112"}],
            }
        ],
    }
    client = FakeClient(answer)
    found, _, _ = extract.extract(client, "m", syllabus, "text/plain", date(2026, 10, 19), TZ, [], ["Reading"])
    reading = found[0]
    assert reading.input == {"title": "Read ch. 4", "preset": "Reading", "due": "2026-10-20T10:00", "duration_min": 90}
    assert reading.quotes["duration_min"] == "pp. 85-112"  # 28 pages at three minutes a page, to the quarter hour
    assert "each assigned reading" in client.calls[0]["system"]
    assert "pages" in extract.ITEM["required"] and client.calls[0]["max_tokens"] == extract.MAX_TOKENS


def test_a_quick_add_with_pages_gets_a_length_not_a_pages_field() -> None:
    client = FakeClient({"title": "Read ch. 5", "preset": "Reading", "pages": 10, "quotes": [], "confidence": 0.9})
    fields, _ = extract.quick_add(client, "m", "read ch 5 (10 pages)", date(2026, 10, 19), TZ, [], ["Reading"])
    assert fields == {"title": "Read ch. 5", "preset": "Reading", "duration_min": 30}


def test_an_image_goes_to_the_model_as_an_image_and_an_item_without_a_title_is_left_out() -> None:
    answer = {
        "is_syllabus": False,
        "items": [
            {"title": "", "due": "2026-10-23T17:00", "confidence": 0.9, "quotes": {}},
            {"title": "Poster", "confidence": 0.9, "quotes": {}},
        ],
    }
    client = FakeClient(answer)
    found, _, _ = extract.extract(client, "m", "iVBORw0K", "image/png", date(2026, 10, 19), TZ, [], [])
    assert [f.input["title"] for f in found] == ["Poster"]
    assert client.calls[0]["messages"][0]["content"][0]["type"] == "image"
