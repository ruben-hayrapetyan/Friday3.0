"""Gmail over IMAP with an app password (8 Nov: users "can add their own gmails - right now it just errors out for
them"; your choice of the ways offered). Google's own connection lets in only the test users listed in the Google
Cloud project, and reading Gmail for anyone else needs Google's yearly paid review; an app password needs neither.

Read-only: the mailbox is opened with EXAMINE, so nothing is marked read, moved or deleted. Gmail's own search runs
on the server (X-GM-RAW), so `gmail.query` reads the same as through the API, and a message's and thread's ids are
the API's (the hex of X-GM-MSGID and X-GM-THRID): a message read both ways is one message. The same three calls as
`sync/gmail.py`'s, which hands them here for a service made by `ImapService`.
"""

import base64
import contextlib
import email
import imaplib
import re
import tomllib
from collections.abc import Callable
from email.message import EmailMessage
from email.policy import default
from email.utils import parseaddr
from typing import Any

from friday.core.paths import secrets_path
from friday.sync.gmail import MAX_BODY_CHARS, MAX_PDF_BYTES, Mail, Pdf, strip_html

HOST = "imap.gmail.com"
CONNECT: list[Callable[[str], Any]] = [imaplib.IMAP4_SSL]  # how Gmail is reached; tests put a stand-in Gmail here
APP_PASSWORDS = "https://myaccount.google.com/apppasswords"


class ImapRefused(Exception):
    """Gmail said no to the address and app password, in words you can act on."""


class ImapService:
    by_imap = True

    def __init__(self, address: str, password: str, connect: Callable[[str], Any] | None = None):
        self.address, self.password, self.connect = address, password, connect or CONNECT[0]
        self.box: Any = None

    def open(self) -> Any:
        if self.box is None:
            box = self.connect(HOST)
            try:
                box.login(self.address, self.password.replace(" ", ""))
            except imaplib.IMAP4.error as error:
                raise ImapRefused(refusal(str(error))) from error
            box.select(all_mail(box), readonly=True)
            self.box = box
        return self.box

    def close(self) -> None:
        if self.box is not None:
            with contextlib.suppress(OSError, imaplib.IMAP4.error):
                self.box.logout()
            self.box = None

    def uid_of(self, message_id: str) -> bytes:
        found = self.open().uid("SEARCH", None, "X-GM-MSGID", str(int(message_id, 16)))[1]
        uids = found[0].split() if found and found[0] else []
        if not uids:
            raise LookupError(f"Gmail no longer has that message ({message_id})")
        return uids[-1]

    def message_ids(self, query: str, limit: int) -> list[tuple[str, str]]:
        """(message, thread) ids of the newest `limit` messages Gmail's search finds, newest first."""
        box = self.open()
        said = query.replace("\\", "\\\\").replace('"', '\\"')
        found = box.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW", f'"{said}"')[1]
        uids = (found[0].split() if found and found[0] else [])[-limit:][::-1]
        if not uids:
            return []
        fetched = box.uid("FETCH", b",".join(uids), "(X-GM-MSGID X-GM-THRID)")[1]
        ids: dict[bytes, tuple[str, str]] = {}
        for line in fetched:
            raw = line[0] if isinstance(line, tuple) else line
            if not isinstance(raw, bytes):
                continue
            uid = re.search(rb"UID (\d+)", raw)
            msg, thread = re.search(rb"X-GM-MSGID (\d+)", raw), re.search(rb"X-GM-THRID (\d+)", raw)
            if uid and msg and thread:
                ids[uid.group(1)] = (f"{int(msg.group(1)):x}", f"{int(thread.group(1)):x}")
        return [ids[u] for u in uids if u in ids]

    def message(self, message_id: str) -> EmailMessage:
        fetched = self.open().uid("FETCH", self.uid_of(message_id), "(BODY.PEEK[])")[1]
        raw = next(part[1] for part in fetched if isinstance(part, tuple))
        return email.message_from_bytes(raw, policy=default)  # type: ignore[return-value]

    def read(self, message_id: str) -> Mail:
        message = self.message(message_id)
        parts = [p for p in message.walk() if not p.is_multipart()]
        plain = [text_of(p) for p in parts if p.get_content_type() == "text/plain" and not p.get_filename()]
        html = [text_of(p) for p in parts if p.get_content_type() == "text/html" and not p.get_filename()]
        body = "\n".join(plain) if plain else "\n".join(strip_html(h) for h in html)
        names = [p.get_filename() for p in parts if p.get_filename()]
        pdfs = [
            Pdf(str(i), p.get_filename() or "attachment.pdf")
            for i, p in enumerate(parts)
            if p.get_content_type() == "application/pdf" and len(p.get_payload(decode=True) or b"") <= MAX_PDF_BYTES
        ]
        header = {k.lower(): str(v) for k, v in message.items()}
        text = (
            f"From: {header.get('from', '')}\nTo: {header.get('to', '')}\nDate: {header.get('date', '')}\n"
            f"Subject: {header.get('subject', '')}\n"
            + (f"Attachments: {', '.join(n for n in names if n)}\n" if names else "")
            + f"\n{body.strip()[:MAX_BODY_CHARS]}"
        )
        bulk = "list-unsubscribe" in header or header.get("precedence", "").lower() in ("bulk", "list", "junk")
        sender = parseaddr(header.get("from", ""))[1].lower()
        return Mail(message_id, sender, header.get("subject", ""), text, pdfs, bulk)

    def attachment(self, message_id: str, attachment_id: str) -> str:
        """The file as standard base64, as documents are stored; `attachment_id` is its part's place in the message."""
        parts = [p for p in self.message(message_id).walk() if not p.is_multipart()]
        return base64.b64encode(parts[int(attachment_id)].get_payload(decode=True) or b"").decode()


def text_of(part: Any) -> str:
    try:
        return str(part.get_content())
    except (LookupError, UnicodeDecodeError):
        return (part.get_payload(decode=True) or b"").decode("utf-8", "replace")


def all_mail(box: Any) -> str:
    """Gmail's All Mail, whatever it's called in your language (it's flagged \\All), else the inbox."""
    for line in box.list()[1] or []:
        text = line.decode() if isinstance(line, bytes) else str(line)
        if "\\All" in text:
            name = text.rsplit(' "/" ', 1)[-1].strip()
            return name if name.startswith('"') else f'"{name}"'
    return "INBOX"


def refusal(said: str) -> str:
    """What to do when Gmail refuses the sign-in."""
    if "Application-specific password required" in said or "web login required" in said.lower():
        return f"Gmail wants an app password, not your usual one: make one at {APP_PASSWORDS} and paste its 16 letters"
    if "IMAP" in said and ("disabled" in said or "not enabled" in said):
        return "IMAP is off for this Gmail: in Gmail, Settings → Forwarding and POP/IMAP → Enable IMAP, then try again"
    return (
        "Gmail didn't accept that address and app password. An app password is 16 letters made at "
        f"{APP_PASSWORDS} (it needs 2-Step Verification on); your usual password won't work"
    )


SECTION = "gmail_app"  # secrets.toml: [gmail_app], [gmail_app_2], …, each an `address` and its `password`


def accounts() -> dict[str, str]:
    """Each Gmail read with an app password: its address and the password, from secrets.toml."""
    path = secrets_path()
    kept = tomllib.loads(path.read_text()) if path.exists() else {}
    return {
        str(v["address"]).strip().lower(): str(v["password"])
        for k, v in kept.items()
        if (k == SECTION or k.startswith(f"{SECTION}_"))
        and isinstance(v, dict)
        and v.get("address")
        and v.get("password")
    }


def check(address: str, password: str, connect: Callable[[str], Any] | None = None) -> None:
    """Sign in once and out again; raises ImapRefused in words, OSError when Gmail can't be reached."""
    service = ImapService(address, password, connect)
    try:
        service.open()
    finally:
        service.close()
