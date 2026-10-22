"""Gmail (DESIGN §22.4): only mail passing the pre-filter (your sender domains or keywords) reaches the AI, with
its PDFs as documents of their own; the rest is kept but never sent; a message is fetched once."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.ingest import llm
from friday.sim.fakes import FakeGmail, mail
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient

NOTHING = {"is_syllabus": False, "items": []}


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="gmail", value={"enabled": True, "sender_domains": ["cornell.edu"]})
    return app


def inbox() -> FakeGmail:
    return FakeGmail(
        [
            mail("m1", "Prof <prof@cs.cornell.edu>", "Problem set 5", "<p>PS5 is out.</p><style>p{}</style>", b"%PDF"),
            mail("m2", "Shop <deals@store.com>", "Big sale", "<p>Everything 50% off</p>"),
            mail("m3", "Sam <sam@gmail.com>", "Lunch?", "<div>Can we move our meeting to Thursday?</div>"),
        ]
    )


def statuses(app: App) -> dict[str, str]:
    return {r["external_id"]: r["status"] for r in app.table("raw_inputs")}


def test_only_mail_passing_the_prefilter_is_read_by_the_ai(app: App) -> None:
    client = FakeClient(NOTHING)
    sync(app.conn, app.now_utc, mail=inbox(), client=client)
    assert statuses(app) == {"m1": "extracted", "m1#ps5.pdf": "extracted", "m2": "ignored", "m3": "extracted"}
    sent = [c["messages"][0]["content"][0] for c in client.calls]
    assert [b["type"] for b in sent] == ["text", "document", "text"]
    assert "PS5 is out." in sent[0]["text"] and "<p>" not in sent[0]["text"] and "p{}" not in sent[0]["text"]


def test_a_message_is_fetched_once(app: App) -> None:
    gmail = inbox()
    sync(app.conn, app.now_utc, mail=gmail, client=FakeClient(NOTHING))
    sync(app.conn, app.now_utc + 60, mail=gmail, client=FakeClient(NOTHING))
    assert gmail.fetched == ["m1", "m2", "m3"]


def test_bulk_mail_needs_its_keyword_in_the_subject_and_every_skip_says_why(app: App) -> None:
    gmail = FakeGmail(
        [
            mail(
                "ad",
                "Admissions <hi@college.edu>",
                "Your future is waiting",
                "<p>Apply by the deadline!</p>",
                bulk=True,
            ),
            mail("ed", "Ed <noreply@edstem.org>", "[CS 1110] New assignment released", "<p>A4 is out</p>", bulk=True),
            mail("lunch", "Sam <sam@gmail.com>", "Lunch?", "<p>Tomorrow?</p>"),
        ]
    )
    sync(app.conn, app.now_utc, mail=gmail, client=FakeClient(NOTHING))
    log = {m["subject"]: m for m in app.do("mail_log")}
    assert log["[CS 1110] New assignment released"]["status"] == "read"
    assert log["Your future is waiting"]["status"] == "skipped" and "Bulk" in log["Your future is waiting"]["why"]
    assert log["Lunch?"]["why"].startswith("No keyword")
    assert log["Lunch?"]["sender"] == "Sam <sam@gmail.com>"


def test_a_skipped_message_can_be_read_anyway(app: App) -> None:
    sync(app.conn, app.now_utc, mail=inbox(), client=FakeClient(NOTHING))
    sale = next(m for m in app.do("mail_log") if m["subject"] == "Big sale")
    app.do("mail_retry", id=sale["id"])
    client = FakeClient(NOTHING)
    sync(app.conn, app.now_utc + 60, mail=inbox(), client=client)
    assert len(client.calls) == 1 and statuses(app)["m2"] == "extracted"


def test_without_an_api_key_mail_waits_and_the_source_says_why(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "client", lambda: None)
    sync(app.conn, app.now_utc, mail=inbox())
    assert "No Anthropic API key" in next(s for s in app.table("sources") if s["kind"] == "gmail")["last_error"]
    assert statuses(app)["m3"] == "new"
