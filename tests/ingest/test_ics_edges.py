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
