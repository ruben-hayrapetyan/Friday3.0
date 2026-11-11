"""Mail beyond Gmail, by app password (C96, your choice; C99): iCloud Mail, Yahoo, Fastmail, or any mail server that
speaks IMAP. Outlook.com isn't here: Microsoft no longer lets an app password read its mail over IMAP (it goes
through Microsoft's own sign-in, a later integration).

The Gmail reader's way (sync/imap_mail.py), without Gmail's own extensions: the inbox opened read-only (EXAMINE, so
nothing is marked read, moved or deleted), the newest messages since a date found by standard SEARCH, and each known
by its own Message-ID, its thread by the first message it answers (References / In-Reply-To), so reading it again, or
fetching it again later ("read it after all"), finds the same message. Everything after (the keyword pre-filter, PDFs,
the AI reading, your Inbox) is Gmail's: commands/mail.py."""

import contextlib
import email
import imaplib
import re
import tomllib
from dataclasses import dataclass
from datetime import date, timedelta
from email.policy import default
from typing import Any

from friday.core.paths import secrets_path
from friday.sync.imap_mail import ImapRefused, ImapService

DAYS = 7  # how far back a first read looks, when the query names no `newer_than:`


@dataclass(frozen=True)
class Provider:
    name: str
    host: str | None  # None: you give the server (Other mail)
    passwords: str  # where its app password is made, said plainly
    steps: str


PROVIDERS = {
    "icloud": Provider(
        "iCloud Mail", "imap.mail.me.com", "account.apple.com → Sign-In and Security → App-Specific Passwords",
        "Use your full iCloud address and an app-specific password (it needs two-factor authentication on).",
    ),
    "yahoo": Provider(
        "Yahoo Mail", "imap.mail.yahoo.com", "Yahoo's Account Security page → Generate app password",
        "Use your full Yahoo address and an app password; your usual password won't work.",
    ),
    "fastmail": Provider(
        "Fastmail", "imap.fastmail.com", "Fastmail's Settings → Privacy & Security → App passwords",
        "Use your full address and an app password (Fastmail's Basic plan has no IMAP).",
    ),
    "other": Provider(
        "Other mail", None, "your mail provider's settings (often called app password)",
        "Your provider's IMAP server (it must use SSL, port 993), your address, and an app password if it has them.",
    ),
}  # fmt: skip


def since_of(query: str, today: date) -> date:
    """The day a read goes back to: Gmail's `newer_than:7d` (or `2w`, `1m`) in the mail settings, else DAYS."""
    found = re.search(r"newer_than:(\d+)([dwmy])", query)
    if not found:
        return today - timedelta(days=DAYS)
    n, unit = int(found.group(1)), found.group(2)
    return today - timedelta(days=n * {"d": 1, "w": 7, "m": 31, "y": 366}[unit])


def message_key(value: str | None) -> str | None:
    """A Message-ID as Friday keeps it: what's inside the <>, or None."""
    if not value:
        return None
    found = re.search(r"<([^<>\s]+)>", value) or re.search(r"(\S+@\S+)", value)
    return found.group(1) if found else None


class AnyImapService(ImapService):
    """A mailbox read by app password, its inbox as Gmail's is read (the same calls, `by_imap`)."""

    def __init__(self, provider: str, address: str, password: str, host: str | None = None, today: date | None = None,
                 connect: Any = None):  # fmt: skip
        super().__init__(address, password, connect)
        self.provider = PROVIDERS[provider]
        self.host = host or self.provider.host or ""
        self.today = today or date.today()
        self.uids: dict[str, bytes] = {}

    def open(self) -> Any:
        if self.box is None:
            box = self.connect(self.host)
            try:
                box.login(self.address, self.password.strip())
            except imaplib.IMAP4.error as error:
                with contextlib.suppress(OSError, imaplib.IMAP4.error):
                    box.logout()
                raise ImapRefused(refusal(self.provider, str(error))) from error
            box.select("INBOX", readonly=True)
            self.box = box
        return self.box

    def message_ids(self, query: str, limit: int) -> list[tuple[str, str]]:
        """(message, thread) of the newest `limit` messages in the inbox since the query's day, newest first."""
        box = self.open()
        since = since_of(query, self.today).strftime("%d-%b-%Y")
        found = box.uid("SEARCH", None, "SINCE", since)[1]
        uids = (found[0].split() if found and found[0] else [])[-limit:][::-1]
        if not uids:
            return []
        fetched = box.uid("FETCH", b",".join(uids), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID REFERENCES IN-REPLY-TO)])")
        ids: dict[bytes, tuple[str, str]] = {}
        for part in fetched[1] or []:
            if not isinstance(part, tuple):
                continue
            uid = re.search(rb"UID (\d+)", part[0])
            if not uid:
                continue
            header = email.message_from_bytes(part[1], policy=default)
            own = message_key(header.get("Message-ID")) or f"uid-{uid.group(1).decode()}@{self.host}"
            first = (str(header.get("References") or "").split() or [str(header.get("In-Reply-To") or "")])[0]
            ids[uid.group(1)] = (own, message_key(first) or own)
            self.uids[own] = uid.group(1)
        return [ids[u] for u in uids if u in ids]

    def uid_of(self, message_id: str) -> bytes:
        if message_id in self.uids:
            return self.uids[message_id]
        if message_id.startswith("uid-"):
            return message_id[4:].split("@")[0].encode()
        found = self.open().uid("SEARCH", None, "HEADER", "Message-ID", f"<{message_id}>")[1]
        uids = found[0].split() if found and found[0] else []
        if not uids:
            raise LookupError(f"{self.provider.name} no longer has that message")
        return uids[-1]


def refusal(provider: Provider, said: str) -> str:
    """What to do when the mail server refuses the sign-in."""
    return (
        f"{provider.name} didn't accept that address and password. Make an app password at {provider.passwords} and "
        f"paste it here: your usual password won't work" + (f" (it said: {said.strip()[:120]})" if said.strip() else "")
    )


SECTION = "mail_app"  # secrets.toml: [mail_app], [mail_app_2], …, each a provider, address, password (and host)


@dataclass(frozen=True)
class Account:
    provider: str
    address: str
    password: str
    host: str | None


def accounts() -> list[Account]:
    """Each mailbox read by app password, from secrets.toml."""
    path = secrets_path()
    kept = tomllib.loads(path.read_text()) if path.exists() else {}
    return [
        Account(str(v["provider"]), str(v["address"]).strip().lower(), str(v["password"]), v.get("host") or None)
        for k, v in kept.items()
        if (k == SECTION or k.startswith(f"{SECTION}_")) and isinstance(v, dict) and v.get("provider") in PROVIDERS
    ]


def check(provider: str, address: str, password: str, host: str | None = None) -> None:
    """Sign in once and let go: ImapRefused in words when it's refused, OSError when the server can't be reached."""
    service = AnyImapService(provider, address, password, host)
    try:
        service.open()
    finally:
        service.close()
