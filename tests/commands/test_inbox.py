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


def test_an_item_you_already_have_is_set_aside_not_asked(app: App) -> None:
    """27 Oct: "please scan for duplicates before proposing things to me": PS4, due the same day, is what you have."""
    app.do("add", text="PS4 due thu 20:00 ~2h")
    feed(app)
    assert "PS4" not in pending(app)
    assert [(s["title"], s["why"]) for s in app.do("inbox")["set_aside"]] == [("PS4", "You have PS4")]
    assert len([i for i in app.do("items") if i["title"] == "PS4"]) == 1


def test_a_course_named_exam_at_the_same_minute_is_the_one_you_have(app: App) -> None:
    app.do("add", text="Prelim 2 at 10/29 7:30pm for 90m /exam")
    feed(app, PRELIM)
    assert "CHEM Prelim 2" not in pending(app)
    assert [s["why"] for s in app.do("inbox")["set_aside"]] == ["You have Prelim 2"]


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


def test_a_task_without_a_length_shows_the_one_it_will_get(app: App) -> None:
    feed(app)
    found = pending(app)
    guess = found["PS4"]["guess_min"]
    assert guess and found["CS 1110 Lecture"]["guess_min"] is None  # an event has its own length
    app.do("suggestion_accept", id=found["PS4"]["id"])
    (ps4,) = app.do("items")
    assert ps4["duration_min"] == guess  # here the kind's usual length, as nothing learned says otherwise
    assert [a["name"] for a in app.do("areas")] == [r["name"] for r in app.table("areas")]  # guessing made no tag


def test_an_event_read_with_a_start_and_no_end_is_accepted_an_hour_long(app: App) -> None:
    """27 Oct: "friday proposes something in the inbox but then when i hit accept i get an error": an email gave the
    Salsa Halloween Social's start and no end, and an event can't be added without one."""
    app.do("document_add", name="mail.txt", content="Salsa Halloween Social Friday 10pm")
    raw = app.table("raw_inputs")[-1]["id"]
    social = '{"title": "Salsa Halloween Social", "preset": "Event", "start": "2026-10-23T22:00"}'
    app.conn.execute(
        "INSERT INTO suggestions (user_id, raw_input_id, command, input, status, created_utc) "
        "VALUES (1, ?, 'add', ?, 'pending', '2026-10-19T13:00Z')",
        [raw, social],
    )
    sid = next(s["id"] for s in app.do("inbox")["suggestions"] if s["input"].get("title") == "Salsa Halloween Social")
    app.do("suggestion_accept", id=sid)
    (event,) = [i for i in app.table("items") if i["title"] == "Salsa Halloween Social"]
    assert (event["when_kind"], event["start_utc"], event["end_utc"]) == (
        "fixed",
        "2026-10-24T02:00Z",
        "2026-10-24T03:00Z",
    )


def test_an_event_suggested_without_an_end_shows_the_end_it_will_have() -> None:
    from friday.commands.suggesting import addable
    from friday.core.settings import DEFAULTS

    presets = DEFAULTS["presets"]
    fields = addable({"title": "Social", "preset": "Event", "start": "2026-10-30T22:00"}, presets)
    assert fields["end"] == "2026-10-30T23:00"
    late = addable({"title": "Party", "preset": "Event", "start": "2026-10-30T23:30"}, presets)
    assert late["end"] == "2026-10-31T00:30"  # past midnight, the next day
    timed = {"title": "Talk", "preset": "Event", "start": "2026-10-30T18:00", "end": "2026-10-30T20:00"}
    assert addable(timed, presets) == timed  # an end it was given stays
    assert "end" not in addable({"title": "PS4", "preset": "Assignment", "due": "2026-10-30T23:59"}, presets)
