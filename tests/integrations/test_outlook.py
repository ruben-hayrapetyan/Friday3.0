"""Outlook mail by Microsoft's sign-in (C109), against Graph's stand-in: signing in keeps the mailbox (its tokens only
in secrets.toml) and turns mail reading on; its new mail goes the way Gmail's goes (the pre-filter, the newest of a
thread read); the reader asks Graph for ids that don't change, reads the inbox since the mail settings' day, lists a
PDF and knows a newsletter; Remove stops it."""

from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from friday.commands.fetching import sync as read_all
from friday.commands.integrations import signed_in
from friday.core.paths import secrets_path
from friday.integrations import oauth, outlook
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient
from tests.integrations.fake_microsoft import REFRESH, TOKENS, FakeGraph
from tests.integrations.odd import odd

NOTHING = {"is_syllabus": False, "items": []}


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    fake = FakeGraph("")
    monkeypatch.setitem(oauth.TRANSPORTS, "outlook_mail", fake.transport)
    monkeypatch.setattr(outlook, "TRANSPORT", [fake.transport])
    fake.mail("prof@cs.cornell.edu", "Problem set 5", "PS5 is out, due Friday.", conversation="ps5")
    fake.mail("deals@store.com", "Big sale", "Everything 50% off", bulk=True)
    fake.mail("prof@cs.cornell.edu", "Re: Problem set 5", "Extended to Monday.", "2026-10-19T16:00:00Z", "ps5")
    return fake


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="gmail", value={"enabled": False, "sender_domains": ["cornell.edu"]})
    return app


def sign_in(app: App, graph: FakeGraph) -> tuple[bool, str]:
    url = app.do("integration_sign_in", kind="outlook_mail", origin="http://127.0.0.1:8765")["url"]
    asked = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert asked["scope"] == "offline_access User.Read Mail.Read"  # read only: nothing is sent or moved
    graph.codes["c"] = asked["code_challenge"]
    return signed_in(app.conn, asked["state"], "c", None)


def test_signing_in_keeps_the_mailbox_and_its_mail_goes_the_way_gmails_goes(app: App, graph: FakeGraph) -> None:
    ok, words = sign_in(app, graph)
    assert ok and "Friday reads maria@outlook.com's new mail" in words, words
    assert app.do("mail_app_accounts") == [{"provider": "outlook", "name": "Outlook", "address": "maria@outlook.com"}]
    assert REFRESH in secrets_path().read_text() and REFRESH not in str(app.table("command_log"))
    assert app.do("settings")["gmail"]["enabled"] is True  # mail reading on, as for an app password
    read_all(app.conn, app.now_utc, client=FakeClient(NOTHING))
    found = {r["title"]: r["status"] for r in app.table("raw_inputs")}
    assert found["Big sale"] == "ignored" and found["Re: Problem set 5"] == "extracted"
    (source,) = [s for s in app.table("sources") if s["kind"] == "mail"]
    assert source["name"] == "Outlook" and source["last_error"] is None


def test_the_reader_asks_for_lasting_ids_the_inbox_since_a_day_and_lists_a_pdf(graph: FakeGraph) -> None:
    pdf = graph.mail("prof@cs.cornell.edu", "Syllabus", "Attached.", "2026-10-18T09:00:00Z", pdf=True)
    reader = outlook.GraphMailService(TOKENS, {}, graph.transport, today=date(2026, 10, 20))
    ids = reader.message_ids("newer_than:2d", 50)
    assert [m for m, _ in ids] == ["AAkALg0003", "AAkALg0001", "AAkALg0002", pdf]
    assert reader.message_ids("newer_than:0d", 50) == []  # nothing yet today
    mail = reader.read(pdf)
    assert mail.sender == "prof@cs.cornell.edu" and [p.name for p in mail.pdfs] == ["Syllabus.pdf"]
    assert reader.attachment(pdf, "att-1") == "JVBERi0xLjQ="
    assert reader.read("AAkALg0002").bulk is True


def test_removed_its_mail_is_no_longer_read(app: App, graph: FakeGraph) -> None:
    sign_in(app, graph)
    read_all(app.conn, app.now_utc, client=FakeClient(NOTHING))
    assert "no longer reads" in app.do("mail_app_forget", address="maria@outlook.com")["message"]
    assert outlook.accounts() == [] and app.do("mail_app_accounts") == []
    assert not [s for s in app.table("sources") if s["kind"] == "mail" and s["enabled"]]


def test_an_html_mail_is_read_as_its_words_and_only_a_small_pdf_is_taken(graph: FakeGraph) -> None:
    sent = graph.mail("prof@cs.cornell.edu", "Lab 4", "", pdf=True)
    graph.messages[sent]["body"] = {"contentType": "html", "content": "<p>Lab 4 is <b>due Friday</b>.</p>"}
    attached = {"value": [
        {"id": "a1", "name": "Rubric.docx", "contentType": "application/msword", "size": 900},
        {"id": "a2", "name": "Scans.pdf", "contentType": "application/pdf", "size": outlook.MAX_PDF_BYTES + 1},
        {"id": "a3", "name": "Lab 4.pdf", "contentType": "application/pdf", "size": 1200},
    ]}  # fmt: skip
    reader = outlook.GraphMailService(TOKENS, {}, odd(graph, f"/me/messages/{sent}/attachments", attached))
    mail = reader.read(sent)
    assert "Lab 4 is due Friday." in mail.text and "<b>" not in mail.text
    assert "Attachments: Rubric.docx, Scans.pdf, Lab 4.pdf" in mail.text  # each named, for the reader
    assert [p.name for p in mail.pdfs] == ["Lab 4.pdf"]  # only the PDF small enough to read
    reader.close()  # nothing held open: a later read still works
    assert reader.read(sent).subject == "Lab 4"
