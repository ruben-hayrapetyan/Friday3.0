"""Gmail (DESIGN §22.4) through the API client, read-only: the newest messages matching your query, each as its
headers, plain-text body (HTML stripped) and the PDFs attached to it. Deciding which go to the AI is
`commands/mail.py`'s job."""

import base64
from dataclasses import dataclass, field
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any

MAX_BODY_CHARS = 20_000  # a long thread's quoted history adds tokens, not tasks
MAX_PDF_BYTES = 5_000_000


@dataclass
class Pdf:
    attachment_id: str
    name: str


@dataclass
class Mail:
    id: str
    sender: str  # the address alone
    subject: str
    text: str  # headers and body, as the AI sees it
    pdfs: list[Pdf] = field(default_factory=list)
    bulk: bool = False  # a mailing list or newsletter: it has an unsubscribe link or says it is bulk


def message_ids(service: Any, query: str, limit: int) -> list[tuple[str, str]]:
    """(message, thread) ids, newest first."""
    if getattr(service, "by_imap", False):  # an app password's (sync/imap_mail.py)
        return service.message_ids(query, limit)  # type: ignore[no-any-return]
    found = service.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    return [(m["id"], m.get("threadId") or m["id"]) for m in found.get("messages", [])]


def read(service: Any, message_id: str) -> Mail:
    if getattr(service, "by_imap", False):
        return service.read(message_id)  # type: ignore[no-any-return]
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = message.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    parts = list(walk(payload))
    plain = [decode(p) for p in parts if p.get("mimeType") == "text/plain" and not p.get("filename")]
    html = [decode(p) for p in parts if p.get("mimeType") == "text/html" and not p.get("filename")]
    body = "\n".join(plain) if plain else "\n".join(strip_html(h) for h in html)
    names = [p["filename"] for p in parts if p.get("filename")]
    pdfs = [
        Pdf(p["body"]["attachmentId"], p["filename"])
        for p in parts
        if p.get("mimeType") == "application/pdf"
        and p.get("body", {}).get("attachmentId")
        and p["body"].get("size", 0) <= MAX_PDF_BYTES
    ]
    text = (
        f"From: {headers.get('from', '')}\nTo: {headers.get('to', '')}\nDate: {headers.get('date', '')}\n"
        f"Subject: {headers.get('subject', '')}\n"
        + (f"Attachments: {', '.join(names)}\n" if names else "")
        + f"\n{body.strip()[:MAX_BODY_CHARS]}"
    )
    bulk = "list-unsubscribe" in headers or headers.get("precedence", "").lower() in ("bulk", "list", "junk")
    sender = parseaddr(headers.get("from", ""))[1].lower()
    return Mail(message_id, sender, headers.get("subject", ""), text, pdfs, bulk)


def attachment(service: Any, message_id: str, attachment_id: str) -> str:
    """The file as standard base64, as documents are stored."""
    if getattr(service, "by_imap", False):
        return service.attachment(message_id, attachment_id)  # type: ignore[no-any-return]
    found = service.users().messages().attachments().get(userId="me", messageId=message_id, id=attachment_id).execute()
    return base64.b64encode(base64.urlsafe_b64decode(found["data"])).decode()


def walk(part: dict[str, Any]) -> Any:
    yield part
    for child in part.get("parts", []):
        yield from walk(child)


def decode(part: dict[str, Any]) -> str:
    data = part.get("body", {}).get("data", "")
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


class TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        self.hidden += tag in ("style", "script")
        if tag in ("br", "p", "div", "tr", "li"):
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        self.hidden -= tag in ("style", "script")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.out.append(data)


def strip_html(html: str) -> str:
    parser = TextOnly()
    parser.feed(html)
    lines = (" ".join(line.split()) for line in "".join(parser.out).splitlines())
    return "\n".join(line for line in lines if line)
