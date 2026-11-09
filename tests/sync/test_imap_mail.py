"""Gmail with an app password (8 Nov: users "can add their own gmails - right now it just errors out for them"). Glass
box on the IMAP reading, against a stand-in Gmail: Gmail's own search runs on the server, ids are the API's, the
mailbox is opened read-only, a PDF comes with its message. Black box through the commands: a wrong password is
refused in words, the right one is kept out of settings and the log, and the mail goes the way all Gmail goes."""

import imaplib
import re
from email.message import EmailMessage
from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.sync import imap_mail
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient

ADDRESS = "student@gmail.com"
PASSWORD = "abcdefghijklmnop"
NOTHING = {"is_syllabus": False, "items": []}


def message(sender: str, subject: str, body: str, pdf: bytes | None = None) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = sender, ADDRESS, subject, "Sun, 08 Nov 2026 10:00:00 -0500"
    m.set_content(body)
    if pdf:
        m.add_attachment(pdf, maintype="application", subtype="pdf", filename="ps5.pdf")
    return m.as_bytes()


class FakeImap:
    """Gmail's IMAP, as much as Friday asks of it."""

    def __init__(self, mails: list[tuple[int, int, bytes]], password: str = PASSWORD, said: str = "") -> None:
        self.mails = {uid: (uid * 1000 + 7, thread, raw) for uid, (_, thread, raw) in enumerate(mails, 1)}
        self.password, self.said = password, said
        self.readonly: bool | None = None
        self.queries: list[str] = []
        self.peeked: list[bytes] = []

    def __call__(self, host: str) -> "FakeImap":
        assert host == "imap.gmail.com"
        return self

    def login(self, user: str, password: str) -> None:
        if password != self.password:
            raise imaplib.IMAP4.error(self.said or "[AUTHENTICATIONFAILED] Invalid credentials (Failure)")

    def list(self) -> tuple[str, "list[bytes]"]:
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All \\HasNoChildren) "/" "[Gmail]/All Mail"']

    def select(self, name: str, readonly: bool = False) -> None:
        assert name == '"[Gmail]/All Mail"'
        self.readonly = readonly

    def uid(self, verb: str, *args: object) -> tuple[str, "list[object]"]:
        if verb == "SEARCH" and "X-GM-RAW" in args:
            self.queries.append(str(args[-1]))
            return "OK", [b" ".join(str(u).encode() for u in self.mails)]
        if verb == "SEARCH":
            wanted = int(str(args[-1]))
            return "OK", [b" ".join(str(u).encode() for u, m in self.mails.items() if m[0] == wanted)]
        uids, what = args[0], str(args[1])
        asked = [int(u) for u in (uids if isinstance(uids, bytes) else str(uids).encode()).split(b",")]
        if what == "(BODY.PEEK[])":
            self.peeked += [str(u).encode() for u in asked]
            return "OK", [(f"1 (UID {u} BODY[] {{1}}".encode(), self.mails[u][2]) for u in asked] + [b")"]
        return "OK", [f"{i} (X-GM-THRID {self.mails[u][1]} X-GM-MSGID {self.mails[u][0]} UID {u})".encode()
                      for i, u in enumerate(asked, 1)]  # fmt: skip

    def logout(self) -> None:
        pass


@pytest.fixture
def gmail(monkeypatch: pytest.MonkeyPatch) -> FakeImap:
    fake = FakeImap([
        (1, 501, message("Prof <prof@cs.cornell.edu>", "Problem set 5", "PS5 is out, due Friday.", b"%PDF-1.4")),
        (2, 502, message("Shop <deals@store.com>", "Big sale", "Everything 50% off")),
    ])  # fmt: skip
    monkeypatch.setattr(imap_mail, "CONNECT", [fake])
    return fake


class TestGlassBox:
    def test_the_search_is_gmails_own_and_the_ids_are_the_apis(self, gmail: FakeImap) -> None:
        service = imap_mail.ImapService(ADDRESS, PASSWORD)
        ids = service.message_ids('newer_than:14d -category:"promotions"', 50)
        assert ids == [(f"{2007:x}", f"{502:x}"), (f"{1007:x}", f"{501:x}")]  # newest first, hex as the API's
        assert gmail.queries == ['"newer_than:14d -category:\\"promotions\\""']
        assert gmail.readonly is True  # EXAMINE: nothing is marked read

    def test_a_message_and_its_pdf(self, gmail: FakeImap) -> None:
        service = imap_mail.ImapService(ADDRESS, PASSWORD)
        mail = service.read(f"{1007:x}")
        assert mail.sender == "prof@cs.cornell.edu" and mail.subject == "Problem set 5" and not mail.bulk
        assert "PS5 is out" in mail.text and "Attachments: ps5.pdf" in mail.text
        (pdf,) = mail.pdfs
        assert service.attachment(mail.id, pdf.attachment_id) == "JVBERi0xLjQ="  # base64 of %PDF-1.4
        assert all(u == b"1" for u in gmail.peeked)  # BODY.PEEK: read without marking it read

    @pytest.mark.parametrize(
        ("said", "words"),
        [("", "16 letters made at https://myaccount.google.com/apppasswords"),
         ("[ALERT] Application-specific password required", "not your usual one"),
         ("[ALERT] IMAP access is disabled for your account", "Enable IMAP")],
    )  # fmt: skip
    def test_a_refusal_says_what_to_do(self, monkeypatch: pytest.MonkeyPatch, said: str, words: str) -> None:
        monkeypatch.setattr(imap_mail, "CONNECT", [FakeImap([], said=said)])
        with pytest.raises(imap_mail.ImapRefused, match=re.escape(words)):
            imap_mail.check(ADDRESS, "wrongwrongwrongw")


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="gmail", value={"enabled": False, "sender_domains": ["cornell.edu"]})
    return app


class TestBlackBox:
    def test_a_wrong_password_is_refused_in_words_and_nothing_is_kept(self, app: App, gmail: FakeImap) -> None:
        with pytest.raises(FieldError, match="16 letters"):
            app.do("gmail_app_set", address=ADDRESS, password="my usual password")
        with pytest.raises(FieldError, match="didn't accept"):
            app.do("gmail_app_set", address=ADDRESS, password="zzzz zzzz zzzz zzzz")
        assert not secrets_path().exists() and app.do("gmail_app_accounts") == []

    def test_connected_its_mail_goes_the_way_all_gmail_goes(self, app: App, gmail: FakeImap) -> None:
        said = app.do("gmail_app_set", address=" Student@Gmail.com ", password="abcd efgh ijkl mnop")
        assert "student@gmail.com" in said["message"] and app.do("gmail_app_accounts") == [ADDRESS]
        assert PASSWORD not in str(app.table("settings")) + str(app.table("command_log"))  # only in secrets.toml
        assert oct(secrets_path().stat().st_mode)[-3:] == "600"
        sync(app.conn, app.now_utc, client=FakeClient(NOTHING))
        found = {r["title"]: r["status"] for r in app.table("raw_inputs")}
        assert found == {"Problem set 5": "extracted", "ps5.pdf": "extracted", "Big sale": "ignored"}
        (source,) = [s for s in app.table("sources") if s["kind"] == "gmail"]
        assert source["last_error"] is None and ADDRESS in source["config"]

    def test_removed_its_mail_is_no_longer_read(self, app: App, gmail: FakeImap) -> None:
        app.do("gmail_app_set", address=ADDRESS, password=PASSWORD)
        sync(app.conn, app.now_utc, client=FakeClient(NOTHING))
        assert "no longer reads" in app.do("gmail_app_set", address=ADDRESS, password="")["message"]
        assert app.do("gmail_app_accounts") == [] and imap_mail.accounts() == {}
