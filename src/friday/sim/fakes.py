"""Stand-ins for Google Calendar, Gmail and the Anthropic client, for tests and `fridayd demo`: calendars and mail
held in memory with the same call chains (`service.events().list(...).execute()`), times given back in the
calendar's offset as Google does, and an AI that answers from a script."""

import base64
import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

EASTERN = timezone(timedelta(hours=-4))


class Call:
    def __init__(self, answer: Callable[[], Any]):
        self.answer = answer

    def execute(self) -> Any:
        return self.answer()


def instant(part: dict[str, str]) -> datetime:
    return datetime.fromisoformat(part.get("dateTime") or part["date"] + "T00:00:00+00:00")


class FakeGoogle:
    def __init__(
        self,
        calendars: dict[str, list[dict[str, Any]]] | None = None,
        primary: str | None = None,
        names: dict[str, str] | None = None,
        rules: dict[str, str] | None = None,
    ):
        self.calendars_by_id = calendars or {}
        self.rules = rules or {}  # a repeating event's id → its RRULE, for the event its instances come from
        self.primary = primary
        self.names = {cid: cid.split("@")[0] for cid in self.calendars_by_id} | (names or {})
        self.ids = itertools.count(1)
        self.writes: list[str] = []

    def calendarList(self) -> "FakeGoogle":  # noqa: N802 (Google's name)
        return self

    def calendars(self) -> "FakeGoogle":
        return self

    def events(self) -> "Events":
        return Events(self)

    def list(self, pageToken: str | None = None) -> Call:  # noqa: N803
        listed = [{"id": c, "summary": self.names[c], "primary": c == self.primary} for c in self.calendars_by_id]
        return Call(lambda: {"items": listed})

    def get(self, calendarId: str) -> Call:  # noqa: N803
        return Call(lambda: {"id": calendarId})

    def insert(self, body: dict[str, Any]) -> Call:
        def make() -> dict[str, Any]:
            cid = f"friday{next(self.ids)}@group"
            self.calendars_by_id[cid], self.names[cid] = [], body["summary"]
            return {"id": cid}

        return Call(make)


class Events:
    def __init__(self, google: FakeGoogle):
        self.google = google

    def list(self, calendarId: str, pageToken: str | None = None, **params: Any) -> Call:  # noqa: N803
        def found() -> dict[str, Any]:
            low, high = params.get("timeMin"), params.get("timeMax")
            return {
                "items": [
                    e
                    for e in self.google.calendars_by_id[calendarId]
                    if (low is None or instant(e["end"]) > datetime.fromisoformat(low))
                    and (high is None or instant(e["start"]) < datetime.fromisoformat(high))
                ]
            }

        return Call(found)

    def get(self, calendarId: str, eventId: str) -> Call:  # noqa: N803
        rule = self.google.rules.get(eventId)
        return Call(lambda: {"id": eventId} | ({"recurrence": [f"RRULE:{rule}"]} if rule else {}))

    def insert(self, calendarId: str, body: dict[str, Any]) -> Call:  # noqa: N803
        event = local(body) | {"id": f"e{next(self.google.ids)}"}
        return Call(lambda: self.google.calendars_by_id[calendarId].append(event) or self.write("insert", event))

    def update(self, calendarId: str, eventId: str, body: dict[str, Any]) -> Call:  # noqa: N803
        def change() -> dict[str, Any]:
            events = self.google.calendars_by_id[calendarId]
            events[:] = [local(body) | {"id": eventId} if e["id"] == eventId else e for e in events]
            return self.write("update", body)

        return Call(change)

    def delete(self, calendarId: str, eventId: str) -> Call:  # noqa: N803
        def remove() -> None:
            events = self.google.calendars_by_id[calendarId]
            events[:] = [e for e in events if e["id"] != eventId]
            self.write("delete", {})

        return Call(remove)

    def write(self, kind: str, event: dict[str, Any]) -> dict[str, Any]:
        self.google.writes.append(kind)
        return event


def local(body: dict[str, Any]) -> dict[str, Any]:
    """Times as Google gives them back: in the calendar's offset, not UTC."""
    moved = {k: {"dateTime": instant(body[k]).astimezone(EASTERN).isoformat()} for k in ("start", "end")}
    return body | moved


def event(eid: str, summary: str, start: str, end: str, **extra: Any) -> dict[str, Any]:
    """An event at local New York times like `2026-10-20T14:00`."""
    return {
        "id": eid,
        "summary": summary,
        "start": {"dateTime": f"{start}:00-04:00"},
        "end": {"dateTime": f"{end}:00-04:00"},
    } | extra


def b64(text: str | bytes) -> str:
    raw = text.encode() if isinstance(text, str) else text
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def mail(
    mid: str,
    sender: str,
    subject: str,
    html: str,
    pdf: bytes | None = None,
    bulk: bool = False,
    thread: str | None = None,
) -> dict[str, Any]:
    """A message as `format=full` gives it: an HTML body, maybe a PDF, and for bulk mail an unsubscribe link."""
    parts: list[dict[str, Any]] = [{"mimeType": "text/html", "filename": "", "body": {"data": b64(html)}}]
    if pdf is not None:
        parts.append(
            {"mimeType": "application/pdf", "filename": "ps5.pdf", "body": {"attachmentId": "att", "size": len(pdf)}}
        )
    headers = [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]
    if bulk:
        headers.append({"name": "List-Unsubscribe", "value": "<https://example.com/unsubscribe>"})
    payload = {"mimeType": "multipart/mixed", "headers": headers, "parts": parts}
    return {"id": mid, "threadId": thread or mid, "payload": payload}


class FakeGmail:
    """users().messages().list/get and .attachments().get over messages held newest first."""

    def __init__(self, messages: list[dict[str, Any]], pdf: bytes = b"%PDF-1.4"):
        self.messages_by_id = {m["id"]: m for m in messages}
        self.pdf = pdf
        self.fetched: list[str] = []

    def users(self) -> "FakeGmail":
        return self

    def messages(self) -> "FakeGmail":
        return self

    def attachments(self) -> "Attachments":
        return Attachments(self)

    def list(self, userId: str, q: str, maxResults: int) -> Call:  # noqa: N803
        newest = list(self.messages_by_id.values())[:maxResults]
        return Call(lambda: {"messages": [{"id": m["id"], "threadId": m.get("threadId", m["id"])} for m in newest]})

    def get(self, userId: str, id: str, format: str) -> Call:  # noqa: A002, N803
        return Call(lambda: self.fetched.append(id) or self.messages_by_id[id])


class Attachments:
    def __init__(self, gmail: FakeGmail):
        self.gmail = gmail

    def get(self, userId: str, messageId: str, id: str) -> Call:  # noqa: A002, N803
        return Call(lambda: {"data": base64.urlsafe_b64encode(self.gmail.pdf).decode()})


NOTHING = {"is_syllabus": False, "items": []}


@dataclass
class ScriptedClient:
    """The AI from a script: reading mail or a document, the answer whose key appears in it (nothing otherwise);
    sorting events, the kind and title given for each title; a quick-add line, read as just its title."""

    answers: dict[str, dict[str, Any]]
    sorts: dict[str, tuple[str, str]] = field(default_factory=dict)  # an event's title → its kind and title
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def messages(self) -> "ScriptedClient":
        return self

    def create(self, **request: Any) -> Any:
        self.calls.append(request)
        asked = json.dumps(request["messages"])
        schema = request["output_config"]["format"]["schema"]["properties"]
        if "is_syllabus" in schema:
            answer = next((a for key, a in self.answers.items() if key in asked), NOTHING)
        elif "items" in schema:
            events = json.loads(request["messages"][0]["content"][0]["text"])
            picked = [(e["id"], self.sorts.get(e["title"])) for e in events]
            answer = {"items": [{"id": i, "kind": k_t[0], "title": k_t[1]} for i, k_t in picked if k_t]}
        elif "ok" in schema:  # Settings' "Test the AI"
            answer = {"ok": True}
        else:
            answer = {"title": request["messages"][0]["content"][0]["text"][:80]}
        return answered(answer)


def answered(answer: dict[str, Any]) -> Any:
    """A reply as structured output gives it: the JSON in a text block."""
    block = SimpleNamespace(type="text", text=json.dumps(answer))
    return SimpleNamespace(content=[block], usage=SimpleNamespace(input_tokens=900, output_tokens=100))
