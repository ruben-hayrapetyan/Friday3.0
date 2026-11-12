"""Outlook mail by Microsoft's sign-in (C109): Outlook.com and Hotmail, and school or work Microsoft 365 mail, which no
longer take an app password over IMAP (C99). Read through Microsoft Graph with read-only access (Mail.Read) the way
the IMAP readers are (sync/imap_any.py): the inbox's newest messages since a day, each known by an id that doesn't
change when it's moved (Graph's immutable ids), its thread by its conversation; everything after (the pre-filter, PDFs,
the AI reading, your Inbox) is Gmail's (commands/mail.py). Nothing is marked read, moved or deleted.

Each mailbox signed in is kept in secrets.toml as `[outlook_mail]`, `[outlook_mail_2]`…: its address and its tokens."""

import json
import os
import tomllib
from dataclasses import dataclass
from datetime import date
from typing import Any

from friday.core.paths import secrets_path
from friday.integrations.base import ConnectorError, Http, Transport
from friday.integrations.microsoft import API, AUTHORITY, client_id
from friday.integrations.oauth import Provider, Session
from friday.sync.gmail import MAX_BODY_CHARS, MAX_PDF_BYTES, Mail, Pdf, strip_html
from friday.sync.imap_any import since_of

SECTION = "outlook_mail"
NAME = "Outlook"
OUTLOOK = Provider(
    kind="outlook_mail", name="Outlook", authorize=f"{AUTHORITY}/authorize", token=f"{AUTHORITY}/token",
    client_id=client_id, scopes=("offline_access", "User.Read", "Mail.Read"), extra={"prompt": "select_account"},
)  # fmt: skip
IMMUTABLE = {"Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"'}
TRANSPORT: list[Transport] = [None]  # a fake Graph, in tests


class GraphMailService:
    """A mailbox read through Graph, as the mail pipeline reads one by app password (`by_imap`: its own calls)."""

    by_imap = True
    provider = OUTLOOK
    mail = True  # signing in keeps a mailbox, not an integration's source (commands/integrations.py signed_in)

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None,
                 today: date | None = None):  # fmt: skip
        config = config or {}
        self.session = Session(OUTLOOK, token, config.get("_keep"))
        self.today = today or date.today()
        base = os.environ.get("FRIDAY_API_GRAPH") or API
        self.http = Http(NAME, base, IMMUTABLE, transport or TRANSPORT[0],
                         fresh=lambda: {"Authorization": f"Bearer {self.session.access()}"})  # fmt: skip

    def check(self) -> str:
        me = self.http.json("GET", "/me", params={"$select": "mail,userPrincipalName"})
        found = str((me or {}).get("mail") or (me or {}).get("userPrincipalName") or "").strip().lower()
        if "@" not in found:
            raise ConnectorError("answer", "Microsoft didn't say which mailbox this is")
        return found

    def message_ids(self, query: str, limit: int) -> list[tuple[str, str]]:
        """(message, thread) of the inbox's newest `limit` messages since the query's day, newest first."""
        since = since_of(query, self.today).isoformat()
        found = self.http.json("GET", "/me/mailFolders/inbox/messages", params={
            "$filter": f"receivedDateTime ge {since}T00:00:00Z", "$orderby": "receivedDateTime desc",
            "$top": limit, "$select": "id,conversationId"})  # fmt: skip
        listed = (found or {}).get("value")
        if not isinstance(listed, list):
            raise ConnectorError("answer", "Outlook's list of mail came back in a shape Friday doesn't know")
        return [(str(m["id"]), str(m.get("conversationId") or m["id"])) for m in listed[:limit]]

    def read(self, message_id: str) -> Mail:
        m = self.http.json("GET", f"/me/messages/{message_id}", params={"$select": (
            "subject,from,toRecipients,receivedDateTime,body,hasAttachments,internetMessageHeaders")})  # fmt: skip
        sender = str(((m.get("from") or {}).get("emailAddress") or {}).get("address") or "").lower()
        to = ", ".join(str((r.get("emailAddress") or {}).get("address") or "") for r in m.get("toRecipients") or [])
        body = (m.get("body") or {}).get("content") or ""
        if (m.get("body") or {}).get("contentType") == "html":
            body = strip_html(body)
        headers = {
            str(h.get("name", "")).lower(): str(h.get("value", "")) for h in m.get("internetMessageHeaders") or []
        }
        pdfs: list[Pdf] = []
        names: list[str] = []
        if m.get("hasAttachments"):
            listed = self.http.json("GET", f"/me/messages/{message_id}/attachments",
                                    params={"$select": "id,name,contentType,size"})  # fmt: skip
            for a in (listed or {}).get("value") or []:
                names.append(str(a.get("name") or ""))
                if a.get("contentType") == "application/pdf" and int(a.get("size") or 0) <= MAX_PDF_BYTES:
                    pdfs.append(Pdf(str(a["id"]), str(a.get("name") or "attachment.pdf")))
        subject = str(m.get("subject") or "")
        text = (f"From: {sender}\nTo: {to}\nDate: {m.get('receivedDateTime', '')}\nSubject: {subject}\n"
                + (f"Attachments: {', '.join(n for n in names if n)}\n" if names else "")
                + f"\n{body.strip()[:MAX_BODY_CHARS]}")  # fmt: skip
        bulk = "list-unsubscribe" in headers or headers.get("precedence", "").lower() in ("bulk", "list", "junk")
        return Mail(message_id, sender, subject, text, pdfs, bulk)

    def attachment(self, message_id: str, attachment_id: str) -> str:
        """The file as standard base64, as documents are stored."""
        found = self.http.json("GET", f"/me/messages/{message_id}/attachments/{attachment_id}")
        return str((found or {}).get("contentBytes") or "")

    def close(self) -> None:
        pass


@dataclass(frozen=True)
class Account:
    section: str
    address: str
    tokens: str


def kept() -> dict[str, Any]:
    path = secrets_path()
    return tomllib.loads(path.read_text()) if path.exists() else {}


def accounts() -> list[Account]:
    """Each Outlook mailbox signed in, from secrets.toml."""
    return [Account(k, str(v["address"]).lower(), str(v["tokens"])) for k, v in kept().items()
            if (k == SECTION or k.startswith(f"{SECTION}_")) and isinstance(v, dict) and v.get("tokens")]  # fmt: skip


def keep(address: str, tokens: str) -> None:
    """A mailbox's tokens, kept (again, when renewed) under its section."""
    from friday.commands.ai import toml_of
    from friday.sync.google_auth import SECRETS_HELD, write_private

    with SECRETS_HELD:  # one change to secrets.toml at a time (audit, 12 Nov)
        all_kept = kept()
        mine = next((a.section for a in accounts() if a.address == address.lower()), None)
        section = mine or next(s for s in [SECTION, *(f"{SECTION}_{n}" for n in range(2, 99))] if s not in all_kept)
        all_kept[section] = {
            "address": address.lower(),
            "tokens": tokens if isinstance(tokens, str) else json.dumps(tokens),
        }
        write_private(secrets_path(), toml_of(all_kept))
