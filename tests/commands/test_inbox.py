"""The inbox through the registry (DESIGN §22.1–22.7): feeds and documents become suggestions; nothing changes the
plan until accepted, except a trusted feed's events; duplicates, updates, syllabus batches and the AI budget."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.ingest import llm
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FEED, FakeClient


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def feed(app: App, text: str = FEED, trusted: bool = False) -> None:
    app.do("source_add", name="Canvas", url="https://example.edu/feed.ics", trusted=trusted)
    sync(app.conn, app.now_utc, fetch=lambda url: text)


def pending(app: App) -> dict[str, dict]:
    return {s["input"].get("title", s["origin"]): s for s in app.do("inbox")["suggestions"]}


def test_a_feed_fills_the_inbox_and_nothing_is_planned_until_accepted(app: App) -> None:
    feed(app)
    found = pending(app)
    assert set(found) == {"CS 1110 Lecture", "PS4", "Essay draft"} and app.do("items") == []
    app.do("suggestion_accept", id=found["PS4"]["id"], edits={"duration_min": 180})
    assert [(i["title"], i["due"], i["duration_min"]) for i in app.do("items")] == [("PS4", "2026-10-22T23:59", 180)]
    app.do("suggestion_reject", id=found["Essay draft"]["id"])
    assert set(pending(app)) == {"CS 1110 Lecture"}


def test_a_trusted_feeds_events_go_straight_in_and_its_tasks_still_wait(app: App) -> None:
    feed(app, trusted=True)
    assert set(pending(app)) == {"PS4", "Essay draft"}
    assert [r["actor"] for r in app.table("command_log") if r["command"] == "suggestion_accept"] == ["sync:Canvas"]


def test_a_changed_event_suggests_editing_what_was_accepted(app: App) -> None:
    feed(app)
    app.do("suggestion_accept", id=pending(app)["PS4"]["id"])
    moved = FEED.replace(
        "DTSTART:20261023T035900Z\nDTEND:20261023T035900Z", "DTSTART:20261024T035900Z\nDTEND:20261024T035900Z"
    )
    sync(app.conn, app.now_utc + 60, fetch=lambda url: moved)  # past the poll interval
    change = pending(app)["PS4"]
    assert change["command"] == "edit" and change["input"]["due"] == "2026-10-23T23:59"
    app.do("suggestion_accept", id=change["id"])
    assert [i["due"] for i in app.do("items") if i["title"] == "PS4"] == ["2026-10-23T23:59"]


PRELIM = FEED.replace(
    "END:VCALENDAR",
    "BEGIN:VEVENT\nUID:prelim\nSUMMARY:CHEM Prelim 2\nDTSTART:20261029T233000Z\n"
    "DTEND:20261030T010000Z\nEND:VEVENT\nEND:VCALENDAR",
)


def test_a_moved_exam_edits_the_exam_and_its_prep_stays_a_prep(app: App) -> None:
    feed(app, PRELIM)
    app.do("suggestion_accept", id=pending(app)["CHEM Prelim 2"]["id"])
    sync(app.conn, app.now_utc + 60, fetch=lambda url: PRELIM.replace("20261029T2330", "20261029T2300"))
    found = pending(app)
    assert found["CHEM Prelim 2"]["command"] == "edit" and found["CHEM Prelim 2"]["input"]["preset"] == "Exam"
    assert found["Prep: CHEM Prelim 2"]["command"] == "add"


def test_an_item_you_already_have_is_marked_a_duplicate_and_accepting_edits_it(app: App) -> None:
    mine = app.do("add", text="PS4 due thu 20:00 ~2h")["item"]["id"]
    feed(app)
    duplicate = pending(app)["PS4"]
    assert duplicate["duplicate_of"] == mine
    app.do("suggestion_accept", id=duplicate["id"])
    assert len([i for i in app.do("items") if i["title"] == "PS4"]) == 1


def test_a_course_named_exam_at_the_same_minute_is_the_one_you_have(app: App) -> None:
    mine = app.do("add", text="Prelim 2 at 10/29 7:30pm for 90m /exam")["item"]["id"]
    feed(app, PRELIM)
    assert pending(app)["CHEM Prelim 2"]["duplicate_of"] == mine


def syllabus_answer() -> dict:
    return {
        "is_syllabus": True,
        "items": [
            {
                "title": "Midterm 1",
                "preset": "Event",
                "start": "2026-11-05T14:00",
                "end": "2026-11-05T16:00",
                "confidence": 0.9,
                "quotes": {"start": "Nov 5, 2-4pm"},
            },
            {
                "title": "Midterm 1 prep",
                "preset": "Exam prep",
                "due": "2026-11-05T14:00",
                "duration_min": 360,
                "before": "Midterm 1",
                "confidence": 0.8,
                "quotes": {},
            },
        ],
    }


def test_a_syllabus_is_one_batch_and_prep_comes_before_its_exam(app: App) -> None:
    app.do("document_add", name="CS 1110 syllabus.pdf", media_type="application/pdf", content="JVBERi0=")
    client = FakeClient(syllabus_answer())
    sync(app.conn, app.now_utc, client=client)
    batches = {s["batch"] for s in app.do("inbox")["suggestions"]}
    assert len(batches) == 1 and None not in batches
    app.do("batch_accept", batch=batches.pop())
    items = {i["title"]: i for i in app.do("items")}
    exam = next(r for r in app.table("items") if r["title"] == "Midterm 1")
    deps = app.table("dependencies")
    assert "Midterm 1 prep" in items and [(d["item_id"], d["depends_on_id"]) for d in deps] == [
        (exam["id"], items["Midterm 1 prep"]["id"])
    ]  # stored as the exam waiting for its prep: `before:`


def test_documents_wait_for_tomorrow_once_the_days_ai_budget_is_spent(app: App) -> None:
    app.do("settings_set", key="llm", value={"daily_calls": 1})
    for n in range(2):
        app.do("document_add", name=f"handout {n}", content=f"Reading {n} due Friday")
    client = FakeClient({"is_syllabus": False, "items": []})
    sync(app.conn, app.now_utc, client=client)
    assert len(client.calls) == 1 and [r["status"] for r in app.table("raw_inputs")] == ["extracted", "new"]
    assert app.do("inbox")["llm"]["calls"] == 1


def test_a_bad_api_key_leaves_documents_waiting_and_shows_on_the_source(app: App) -> None:
    class BadKey(Exception):
        status_code = 401

    class Refusing(FakeClient):
        def create(self, **request: object) -> object:
            raise BadKey("invalid x-api-key")

    for n in range(2):
        app.do("document_add", name=f"handout {n}", content=f"Reading {n} due Friday")
    sync(app.conn, app.now_utc, client=Refusing({}))
    assert [r["status"] for r in app.table("raw_inputs")] == ["new", "new"]
    assert "invalid x-api-key" in app.table("sources")[0]["last_error"]
    assert "refused the key" in app.table("sources")[0]["last_error"]


def test_ask_ai_reads_a_line_the_grammar_cant_and_runs_nothing(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    answer = {
        "title": "call mom",
        "preset": "Event",
        "start": "2026-10-24T15:00",
        "end": "2026-10-24T15:30",
        "confidence": 0.9,
        "quotes": {},
    }
    monkeypatch.setattr(llm, "client", lambda: FakeClient(answer))
    fields = app.do("ask_ai", text="ring mum saturday afternoon around 3 for half an hour")
    assert fields["start"] == "2026-10-24T15:00" and app.do("items") == []
    monkeypatch.setattr(llm, "client", lambda: None)
    with pytest.raises(FieldError, match="no Anthropic key"):
        app.do("ask_ai", text="anything")


def test_forgetting_a_source_deletes_what_it_brought_in(app: App) -> None:
    feed(app)
    source = app.do("inbox")["sources"][0]["id"]
    app.do("source_remove", id=source, forget=True)
    assert app.table("raw_inputs") == [] and app.do("inbox")["suggestions"] == []


def test_a_suggestion_carries_the_text_it_was_read_from(app: App) -> None:
    app.do("document_add", name="Email from prof", content="PS5 is due Friday at 5pm.")
    answer = {
        "is_syllabus": False,
        "items": [{"title": "PS5", "due": "2026-10-23T17:00", "quotes": {"due": "Friday at 5pm"}, "confidence": 0.9}],
    }
    sync(app.conn, app.now_utc, client=FakeClient(answer))
    (found,) = app.do("inbox")["suggestions"]
    assert found["source_text"] == "PS5 is due Friday at 5pm." and found["source_kind"] == "upload"


def test_a_request_the_model_wont_take_leaves_documents_waiting_and_says_so(app: App) -> None:
    class Unsupported(Exception):
        status_code = 400

    class Refusing(FakeClient):
        def create(self, **request: object) -> object:
            raise Unsupported("tool_choice: type 'tool' is not supported for this model")

    app.do("document_add", name="handout", content="Reading due Friday")
    sync(app.conn, app.now_utc, client=Refusing({}))
    assert [r["status"] for r in app.table("raw_inputs")] == ["new"]
    assert "won't take Friday's request" in app.table("sources")[0]["last_error"]
