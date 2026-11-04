"""Calendar feeds (DESIGN §22.2): an ICS text into proposed `add` inputs, by fixed rules (no LLM).

Feeds and Google Calendar share `classify`: an event of no length, or whose summary says it is due, is an
assignment due then (so is a `VTODO` with a `DUE`); an exam is an Exam with prep due before it; a timed event
that looks like a lesson is a class, and any other an event (with an `RRULE`, a series). A calendar can name
one kind for all its events instead. Times come out as local wall time in your timezone.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar


@dataclass
class Proposed:
    command: str  # a registry command, almost always "add"
    input: dict[str, Any]
    quotes: dict[str, str] = field(default_factory=dict)  # field → the source text it came from
    confidence: float = 1.0
    fixed: bool = False  # a fixed event: a trusted source's go straight in
    series: str | None = None  # the repeating event it is one instance of


@dataclass(frozen=True)
class Event:
    """What a calendar says of one event, for reading it again another way (the small model's kind and title)."""

    summary: str
    start: str | None  # local, for a timed event
    end: str | None
    day: str | None  # for an all-day one, to `day_end` (exclusive)
    day_end: str | None
    every: str | None = None
    series: str | None = None
    location: str | None = None  # where it is: a fixed event made of it is there (27 Oct)


def placed(proposals: list[Proposed], e: Event) -> list[Proposed]:
    """The event's place on what it makes that has a time: the calendar's say, so a place taken off there goes here."""
    for p in proposals:
        p.series = e.series
        if p.fixed:
            p.input["location"] = e.location
    return proposals


@dataclass
class Found:
    external_id: str
    content_hash: str
    title: str
    text: str
    proposals: list[Proposed]
    event: Event | None = None
    read: "Reading | None" = None

    def as_kind(self, kind: str, title: str) -> list[Proposed]:
        """Its proposals were it `kind`, titled `title` (the rules' reading otherwise)."""
        if self.event is None or self.read is None:
            return self.proposals
        e = self.event
        proposals = classify(
            e.summary, e.start, e.end, e.day, e.day_end, replace(self.read, kind=kind), e.every, title=title
        )
        return placed(proposals, e)


def fetch(url: str) -> str:
    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text


def local(value: Any, tz: str) -> str | None:
    """A DTSTART or DUE as local `YYYY-MM-DDTHH:MM`; None for an all-day date."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(ZoneInfo(tz))
    return value.strftime("%Y-%m-%dT%H:%M")


@dataclass(frozen=True)
class Reading:
    """How a calendar's events are read: `kind` (a kind's name) decides for every event when set; otherwise the
    patterns do, and what matches none is an event."""

    due: re.Pattern
    exam: re.Pattern
    lesson: re.Pattern
    kind: str | None = None
    fixed_kinds: frozenset[str] = frozenset({"Class", "Exam", "Meeting", "Appointment", "Event"})
    all_day: bool = False  # all-day events that aren't due or an exam go in, without blocking time


def reading(due: str, exam: str, lesson: str, **rest: Any) -> Reading:
    return Reading(*(re.compile(p, re.IGNORECASE) for p in (due, exam, lesson)), **rest)


def parse_feed(text: str, tz: str, read: Reading) -> list[Found]:
    calendar = Calendar.from_ical(text)
    out = []
    for component in calendar.walk():
        if component.name not in ("VEVENT", "VTODO"):
            continue
        raw = component.to_ical().decode("utf-8", "replace")
        uid = str(component.get("UID", hashlib.sha256(raw.encode()).hexdigest()[:16]))
        recurrence = component.get("RECURRENCE-ID")
        external = f"{uid}#{recurrence.dt.isoformat()}" if recurrence is not None else uid
        facts = event(component, tz) if component.name == "VEVENT" else None
        proposals = from_facts(facts, read) if facts else todo(component, tz) if component.name == "VTODO" else []
        summary = str(component.get("SUMMARY", "")).strip()
        out.append(Found(external, hashlib.sha256(raw.encode()).hexdigest(), summary, raw, proposals, facts, read))
    return out


def event(component: Any, tz: str) -> Event | None:
    summary = str(component.get("SUMMARY", "")).strip()
    start_raw = component.get("DTSTART")
    if not summary or start_raw is None:
        return None
    start = local(start_raw.dt, tz)
    end_raw = component.get("DTEND")
    duration = component.get("DURATION")
    end_dt = end_raw.dt if end_raw is not None else start_raw.dt + (duration.dt if duration else timedelta(0))
    where = str(component.get("LOCATION", "")).strip() or None
    if start is None:
        return Event(summary, None, None, start_raw.dt.isoformat(), end_dt.isoformat(), location=where)
    rule = component.get("RRULE")
    every = "rrule:" + rule.to_ical().decode() + skipped(component, tz) if rule is not None else None
    return Event(summary, start, local(end_dt, tz), None, None, every, location=where)


def skipped(component: Any, tz: str) -> str:
    """The rule's cancelled times (EXDATE, one property or several), as `;EXDATE=…` local, or nothing."""
    found = component.get("EXDATE")
    lists = found if isinstance(found, list) else [found] if found is not None else []
    moments = sorted({at for lst in lists for d in lst.dts if (at := local(d.dt, tz))})
    return ";EXDATE=" + ",".join(m.replace("-", "").replace(":", "") + "00" for m in moments) if moments else ""


def from_facts(e: Event, read: Reading) -> list[Proposed]:
    return placed(classify(e.summary, e.start, e.end, e.day, e.day_end, read, e.every), e)


def classify(
    summary: str,
    start: str | None,
    end: str | None,
    day: str | None,
    day_end: str | None,
    read: Reading,
    every: str | None = None,
    title: str | None = None,
) -> list[Proposed]:
    """One event as proposals, timed (`start`, `end` local) or all-day (`day` to `day_end`, exclusive): something
    due, an exam with its prep, a class, or an event. `title` is the small model's tidier one."""
    quotes = {"title": summary}  # the summary is the only words worth showing
    due_at, plain = end if start else f"{day}T23:59", title or read.due.sub("", summary).strip(" :-") or summary
    named = title or summary
    if read.kind is not None and read.kind not in read.fixed_kinds:
        return [Proposed("add", {"title": plain, "preset": read.kind, "due": due_at}, quotes)]
    if read.kind is None and ((start is not None and start == end) or read.due.search(summary)):
        return [Proposed("add", {"title": plain, "preset": "Assignment", "due": due_at}, quotes)]
    exam = read.kind == "Exam" or (read.kind is None and read.exam.search(summary) is not None)
    eve = f"{date.fromisoformat(day) - timedelta(days=1)}T23:59" if day else None  # an all-day exam's
    prep_fields = {"title": f"Prep: {named}", "preset": "Exam prep", "due": start or eve}
    prep = [Proposed("add", prep_fields, quotes)]
    if start is None:
        if not read.all_day:
            return prep if exam else []
        fixed = {"title": named, "preset": read.kind or ("Exam" if exam else "Event"), "start": f"{day}T00:00"}
        fixed |= {"end": f"{day_end}T00:00", "blocks_time": False}
        return [Proposed("add", fixed, quotes, fixed=True), *(prep if exam else [])]
    kind = read.kind or ("Exam" if exam else "Class" if read.lesson.search(summary) else "Event")
    fields: dict[str, Any] = {"title": named, "preset": kind, "start": start, "end": end}
    if days := whole_days(start, end):
        # A birthday the Mac gives as 12:00 AM to 11:59 PM (3 Nov: "don't make full day events actually look like they
        # take the full day"): a whole-day event, at the top of its day and not busy, kept as it came in before.
        fields |= {"start": f"{days[0]}T00:00", "end": f"{days[1]}T00:00", "blocks_time": False}
    if every:
        fields["every"] = every
    return [Proposed("add", fields, quotes, fixed=True), *(prep if exam else [])]


def whole_days(start: str, end: str | None) -> tuple[str, str] | None:
    """The days (the last exclusive) a timed event fills from midnight to 11:59 PM or the next midnight; None when it
    doesn't."""
    if end is None or start[11:] != "00:00" or end[11:] not in ("23:59", "00:00"):
        return None
    last = date.fromisoformat(end[:10]) + timedelta(days=1 if end[11:] == "23:59" else 0)
    return (start[:10], last.isoformat()) if last.isoformat() > start[:10] else None


def todo(component: Any, tz: str) -> list[Proposed]:
    summary = str(component.get("SUMMARY", "")).strip()
    due_raw = component.get("DUE")
    if not summary or due_raw is None:
        return []
    due = local(due_raw.dt, tz) or f"{due_raw.dt.isoformat()}T23:59"  # a date alone is due at day's end
    return [Proposed("add", {"title": summary, "preset": "Assignment", "due": due}, {"title": summary})]


def google_event(event: dict[str, Any], tz: str, read: Reading, rule: str | None = None) -> Found | None:
    """A Google Calendar event (one instance, `singleEvents`); None for one you declined. Instances of a repeating
    event share its id as `series`, and its `rule` is kept with them. Kept even when the rules propose nothing, for
    the small model to read."""
    if any(a.get("self") and a.get("responseStatus") == "declined" for a in event.get("attendees", [])):
        return None
    summary = (event.get("summary") or "").strip() or "Busy"
    start, end = event.get("start", {}), event.get("end", {})
    series = event.get("recurringEventId")
    # Where it is: in the text only when it has one, so events without a place read before aren't "changed" (27 Oct).
    location = (event.get("location") or "").strip()
    where = {"location": location} if location else {}
    if "dateTime" in start:
        timed = local(datetime.fromisoformat(start["dateTime"]), tz), local(datetime.fromisoformat(end["dateTime"]), tz)
        facts = Event(summary, *timed, None, None, series=series, location=location or None)
    else:
        facts = Event(summary, None, None, start.get("date"), end.get("date"), series=series, location=location or None)
    text = json.dumps({"summary": summary, "start": start, "end": end} | where, sort_keys=True)
    digest = hashlib.sha256(text.encode()).hexdigest()  # without the rule, so instances read before aren't "changed"
    if rule:
        text = json.dumps({"summary": summary, "start": start, "end": end, "recurrence": rule} | where, sort_keys=True)
    found = Found(event["id"], digest, summary, text, from_facts(facts, read))
    if event.get("transparency") == "transparent":
        # Marked free: kept, but not busy unless you count free events (COMBINED.md 28).
        for p in found.proposals:
            if p.fixed:
                p.input["free"] = True
    found.event, found.read = facts, read
    return found
