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


def test_a_skipped_message_read_anyway_comes_with_its_pdfs(app: App) -> None:
    # The audit (30 Oct): a skipped message never fetched its PDFs, so reading it anyway read it without them.
    gmail = FakeGmail([mail("s1", "Club <hi@club.org>", "Spring schedule", "<p>Attached.</p>", b"%PDF")])
    sync(app.conn, app.now_utc, mail=gmail, client=FakeClient(NOTHING))
    assert statuses(app) == {"s1": "ignored"}
    skipped = app.do("mail_log")[0]
    assert app.do("mail_retry", id=skipped["id"])["message"] == "It's read on the next sync, with its PDFs"
    client = FakeClient(NOTHING)
    sync(app.conn, app.now_utc + 1, mail=gmail, client=client)  # a minute on: the next reading of mail is now
    assert statuses(app) == {"s1": "extracted", "s1#ps5.pdf": "extracted"}
    assert [c["messages"][0]["content"][0]["type"] for c in client.calls] == ["text", "document"]


def test_a_message_read_with_nothing_found_can_be_read_again(app: App) -> None:
    # 30 Oct: an invitation to a Morgan Stanley webinar was read as marketing; one that made suggestions isn't
    # read twice.
    sync(app.conn, app.now_utc, mail=inbox(), client=FakeClient(NOTHING))
    read = [m for m in app.do("mail_log") if m["status"] == "read"]
    assert read and not read[0]["found"]
    app.do("mail_retry", id=read[0]["id"])
    client = FakeClient(NOTHING)
    sync(app.conn, app.now_utc + 60, mail=inbox(), client=client)
    assert len(client.calls) == 1
    app.conn.execute(
        "INSERT INTO suggestions (raw_input_id, command, input, created_utc) VALUES (?, 'add', '{}', ?)",
        [read[0]["id"], "2026-10-19T09:00Z"],
    )
    with pytest.raises(Exception, match="nothing found"):
        app.do("mail_retry", id=read[0]["id"])


def test_without_an_api_key_mail_waits_and_the_source_says_why(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "client", lambda *_: None)
    sync(app.conn, app.now_utc, mail=inbox())
    assert "an Anthropic API key" in next(s for s in app.table("sources") if s["kind"] == "gmail")["last_error"]
    assert statuses(app)["m3"] == "new"


CAREERS = "Invitation to Global Careers Week | Nov 2-6"
WEBINAR = "You're Invited | Morgan Stanley Research: AI and the Stock Market"


def test_an_email_about_an_event_is_read_from_a_list_and_the_forums_tab(tmp_path: Path) -> None:
    """29 Oct: a film screening sent to a Cornell list, bulk and in the Forums tab, never reached the Inbox."""
    from friday.core.integrations import GmailSettings  # noqa: PLC0415

    plain = new_app(tmp_path)
    plain.do("settings_set", key="gmail", value={"enabled": True})  # Friday's own keywords, no sender listed
    assert "-category:forums" not in GmailSettings().query
    screening = "Please Join us for an Advance Film Screening and Conversation with Shyam Sankar '03, CTO of Palantir"
    gmail = FakeGmail(
        [
            mail(
                "film", "Kristie Blake <kristie.blake@cornell.edu>", screening, "<p>Nov 4, 7pm, Statler</p>", bulk=True
            ),
            mail("talk", "CS <cs@cornell.edu>", "Talk: Robots that learn", "<p>Friday 4pm</p>", bulk=True),
            mail("sale", "Shop <deals@store.com>", "Big sale this weekend", "<p>Everything 50% off</p>", bulk=True),
            # 30 Oct: "invite" didn't match "Invitation" or "Invited", so these were skipped as bulk mail
            mail("careers", "Careers <careers@cornell.edu>", CAREERS, "<p>Nov 2-6</p>", bulk=True),
            mail("ms", "Olivia <olivia@morganstanley.com>", WEBINAR, "<p>Wed, Nov 11, 5-6pm ET</p>", bulk=True),
        ]
    )
    sync(plain.conn, plain.now_utc, mail=gmail, client=FakeClient(NOTHING))
    log = {m["subject"]: m["status"] for m in plain.do("mail_log")}
    assert log[screening] == "read" and log["Talk: Robots that learn"] == "read"
    assert log[CAREERS] == "read" and log[WEBINAR] == "read"
    assert log["Big sale this weekend"] == "skipped"
