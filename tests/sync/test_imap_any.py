"""Mail beyond Gmail by app password (C99): iCloud Mail, Yahoo, Fastmail, other IMAP. Glass box on the reading, against
a stand-in mail server that speaks plain IMAP (no Gmail extensions): the inbox opened read-only, the newest since a
day found by SINCE, each message known by its Message-ID and its thread by the first it answers, a message found
again in a new session. Black box through the commands: a wrong password refused in words naming where app passwords
are made, the right one kept only in secrets.toml, and the mail going the way Gmail's goes."""

import imaplib
import re
from datetime import date
from email.message import EmailMessage
from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.sync import imap_any, imap_mail
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient

ADDRESS = "maria@icloud.com"
PASSWORD = "abcd-efgh-ijkl-mnop"
NOTHING = {"is_syllabus": False, "items": []}


def message(sender: str, subject: str, body: str, mid: str, refs: str | None = None) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, ADDRESS, subject
    m["Date"], m["Message-ID"] = "Mon, 19 Oct 2026 10:00:00 -0400", f"<{mid}>"
    if refs:
        m["References"] = refs
    m.set_content(body)
    return m.as_bytes()


class FakeMailServer:
    """A mail server's IMAP, plain: no X-GM-anything, as much as Friday asks of it."""

    def __init__(self, mails: list[bytes], host: str = "imap.mail.me.com", password: str = PASSWORD) -> None:
        self.mails = dict(enumerate(mails, 1))
        self.host, self.password = host, password
        self.readonly: bool | None = None
        self.selected: str | None = None
        self.searches: list[tuple] = []
        self.logged_out = False

    def __call__(self, host: str) -> "FakeMailServer":
        assert host == self.host, host
        return self

    def login(self, user: str, password: str) -> None:
        if password != self.password:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Authentication failed.")

    def select(self, name: str, readonly: bool = False) -> None:
        self.selected, self.readonly = name, readonly

    def uid(self, verb: str, *args: object) -> tuple[str, list]:
        if verb == "SEARCH":
            self.searches.append(args)
            if "HEADER" in args:  # a header's own value, as a server searches it: not the same id in References
                wanted = str(args[-1]).encode().lower()
                hits = [u for u, raw in self.mails.items()
                        if any(line.lower() == b"message-id: " + wanted for line in raw.splitlines())]  # fmt: skip
                return "OK", [b" ".join(str(u).encode() for u in hits)]
            return "OK", [b" ".join(str(u).encode() for u in self.mails)]
        uids, what = args[0], str(args[1])
        asked = [int(u) for u in (uids if isinstance(uids, bytes) else str(uids).encode()).split(b",")]
        if what == "(BODY.PEEK[])":
            return "OK", [(f"1 (UID {u} BODY[] {{1}}".encode(), self.mails[u]) for u in asked] + [b")"]
        assert what.startswith("(BODY.PEEK[HEADER.FIELDS"), what
        headers = []
        for i, u in enumerate(asked, 1):
            head = self.mails[u].split(b"\n\n")[0]
            keep = b"\r\n".join(line for line in head.splitlines()
                                if line.lower().startswith((b"message-id", b"references", b"in-reply-to")))  # fmt: skip
            headers += [(f"{i} (UID {u} BODY[HEADER.FIELDS (MESSAGE-ID REFERENCES IN-REPLY-TO)] {{1}}".encode(),
                         keep + b"\r\n\r\n"), b")"]  # fmt: skip
        return "OK", headers

    def logout(self) -> None:
        self.logged_out = True


MAILS = [
    message("Prof <prof@cs.cornell.edu>", "Problem set 5", "PS5 is out, due Friday.", "ps5@cornell.edu"),
    message("Shop <deals@store.com>", "Big sale", "Everything 50% off", "sale-1@store.com"),
    message("Prof <prof@cs.cornell.edu>", "Re: Problem set 5", "Extended to Monday.", "ps5-re@cornell.edu",
            "<ps5@cornell.edu>"),
]  # fmt: skip


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> FakeMailServer:
    fake = FakeMailServer(MAILS)
    monkeypatch.setattr(imap_mail, "CONNECT", [fake])
    return fake


def service() -> imap_any.AnyImapService:
    return imap_any.AnyImapService("icloud", ADDRESS, PASSWORD, today=date(2026, 10, 20))


class TestGlassBox:
    def test_the_inbox_is_read_only_and_searched_since_a_day_the_standard_way(self, server: FakeMailServer) -> None:
        ids = service().message_ids("newer_than:14d", 50)
        assert server.selected == "INBOX" and server.readonly is True  # EXAMINE: nothing marked read
        assert server.searches[0] == (None, "SINCE", "06-Oct-2026")
        assert ids == [("ps5-re@cornell.edu", "ps5@cornell.edu"), ("sale-1@store.com", "sale-1@store.com"),
                       ("ps5@cornell.edu", "ps5@cornell.edu")]  # fmt: skip

    @pytest.mark.parametrize(("query", "back"), [("newer_than:2d", 2), ("newer_than:1w", 7), ("", imap_any.DAYS),
                                                  ('in:inbox -category:"promotions"', imap_any.DAYS)])  # fmt: skip
    def test_how_far_back_follows_the_mail_settings(self, query: str, back: int) -> None:
        assert (date(2026, 10, 20) - imap_any.since_of(query, date(2026, 10, 20))).days == back

    def test_a_message_is_found_again_in_a_new_session_by_its_message_id(self, server: FakeMailServer) -> None:
        mail = service().read("ps5@cornell.edu")  # a session that never listed it: found by its header
        assert mail.subject == "Problem set 5" and "PS5 is out" in mail.text
        assert server.searches[-1] == (None, "HEADER", "Message-ID", "<ps5@cornell.edu>")

    def test_a_refusal_names_where_app_passwords_are_made(self, server: FakeMailServer) -> None:
        with pytest.raises(imap_mail.ImapRefused, match=re.escape("account.apple.com → Sign-In and Security")):
            imap_any.check("icloud", ADDRESS, "my usual password")
        assert server.logged_out

    @pytest.mark.parametrize(("raw", "key"), [("<a@b.c>", "a@b.c"), ("  <x.y@z>  ", "x.y@z"), ("bare@id", "bare@id"),
                                              ("", None), (None, None)])  # fmt: skip
    def test_a_message_id_is_kept_without_its_angle_brackets(self, raw: str | None, key: str | None) -> None:
        assert imap_any.message_key(raw) == key

    def test_every_provider_says_its_server_and_where_passwords_are_made(self) -> None:
        assert {k: p.host for k, p in imap_any.PROVIDERS.items()} == {
            "icloud": "imap.mail.me.com", "yahoo": "imap.mail.yahoo.com", "fastmail": "imap.fastmail.com",
            "other": None,
        }  # fmt: skip
        assert all(p.passwords and p.steps for p in imap_any.PROVIDERS.values())
        assert "outlook" not in imap_any.PROVIDERS  # Microsoft refuses app passwords over IMAP (C99)


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path)
    app.do("settings_set", key="gmail", value={"enabled": False, "sender_domains": ["cornell.edu"]})
    return app


class TestBlackBox:
    def test_a_wrong_password_is_refused_in_words_and_nothing_is_kept(self, app: App, server: FakeMailServer) -> None:
        with pytest.raises(FieldError, match="App-Specific Passwords"):
            app.do("mail_app_set", provider="icloud", address=ADDRESS, password="wrong")
        with pytest.raises(FieldError, match="isn't an email address"):
            app.do("mail_app_set", provider="icloud", address="maria", password=PASSWORD)
        assert not secrets_path().exists() and app.do("mail_app_accounts") == []

    def test_other_mail_needs_its_server(self, app: App, server: FakeMailServer) -> None:
        with pytest.raises(FieldError, match="IMAP server's name"):
            app.do("mail_app_set", provider="other", address="me@uni.edu", password=PASSWORD)

    def test_connected_its_mail_goes_the_way_gmails_goes(self, app: App, server: FakeMailServer) -> None:
        said = app.do("mail_app_set", provider="icloud", address=" Maria@iCloud.com ", password=PASSWORD)
        assert "iCloud Mail connected" in said["message"]
        assert app.do("mail_app_accounts") == [{"provider": "icloud", "name": "iCloud Mail", "address": ADDRESS}]
        assert PASSWORD not in str(app.table("settings")) + str(app.table("command_log"))  # only in secrets.toml
        assert oct(secrets_path().stat().st_mode)[-3:] == "600"
        sync(app.conn, app.now_utc, client=FakeClient(NOTHING))
        found = {r["title"]: r["status"] for r in app.table("raw_inputs")}
        assert found["Big sale"] == "ignored"  # the pre-filter, as for Gmail: not a sender you listed
        assert found["Re: Problem set 5"] == "extracted"  # the newest of its thread is read
        (source,) = [s for s in app.table("sources") if s["kind"] == "mail"]
        assert source["name"] == "iCloud Mail" and source["last_error"] is None and ADDRESS in source["config"]

    def test_removed_its_mail_is_no_longer_read(self, app: App, server: FakeMailServer) -> None:
        app.do("mail_app_set", provider="icloud", address=ADDRESS, password=PASSWORD)
        sync(app.conn, app.now_utc, client=FakeClient(NOTHING))
        assert "no longer reads" in app.do("mail_app_forget", address=ADDRESS)["message"]
        assert app.do("mail_app_accounts") == [] and imap_any.accounts() == []
        assert not [s for s in app.table("sources") if s["kind"] == "mail" and s["enabled"]]
