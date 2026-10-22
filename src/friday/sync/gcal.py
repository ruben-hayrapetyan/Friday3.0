"""Google Calendar (DESIGN §22.2–22.3) through the API client: read the calendars you picked, and publish the plan
one way into a "Friday" calendar that only Friday writes. Turning events into items is `ingest/ics.py`'s job;
deciding what to publish is `commands/google.py`'s."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from googleapiclient.errors import HttpError

from friday.core.time import format_utc

KEY = "friday"  # the block key, in extendedProperties.private


def rfc3339(moment: int) -> str:
    return format_utc(moment).replace("Z", ":00Z")


def paged(request: Any, **params: Any) -> list[dict[str, Any]]:
    out, token = [], None
    while True:
        page = request.list(**params, pageToken=token).execute()
        out += page.get("items", [])
        token = page.get("nextPageToken")
        if not token:
            return out


def calendars(service: Any) -> list[dict[str, Any]]:
    """Every calendar in the account: id, name and whether it is the primary one."""
    return [
        {
            "id": c["id"],
            "name": c.get("summaryOverride") or c.get("summary") or c["id"],
            "primary": bool(c.get("primary")),
        }
        for c in paged(service.calendarList())
    ]


def events(service: Any, calendar_id: str, time_min: str, time_max: str | None = None) -> list[dict[str, Any]]:
    """Single instances (recurring events expanded by Google) ending after `time_min`."""
    window = {"timeMin": time_min} | ({"timeMax": time_max} if time_max else {})
    return paged(service.events(), calendarId=calendar_id, singleEvents=True, maxResults=2500, **window)


def repeat_rules(service: Any, calendar_id: str, series_ids: set[str]) -> dict[str, str]:
    """Each repeating event's RRULE (like `FREQ=YEARLY`), from the event its instances come from; instances alone
    can't tell a yearly birthday from a weekly lecture. One that can't be read is left out."""
    out = {}
    for series_id in sorted(series_ids):
        try:
            master = service.events().get(calendarId=calendar_id, eventId=series_id).execute()
        except HttpError:
            continue
        found = [r.removeprefix("RRULE:") for r in master.get("recurrence", []) if r.startswith("RRULE:")]
        if found:
            out[series_id] = found[0]
    return out


@dataclass
class Block:
    key: str
    title: str
    start: str  # RFC 3339
    end: str
    tentative: bool
    link: str | None = None


def own_calendar(service: Any, calendar_id: str | None, tz: str) -> str:
    """The "Friday" calendar, made again if you deleted it."""
    if calendar_id:
        try:
            service.calendars().get(calendarId=calendar_id).execute()
            return calendar_id
        except HttpError as error:
            if error.resp.status not in (404, 410):
                raise
    return service.calendars().insert(body={"summary": "Friday", "timeZone": tz}).execute()["id"]


def publish(service: Any, calendar_id: str, blocks: list[Block], time_min: str) -> tuple[int, int, int]:
    """Make the calendar from `time_min` on match the blocks; returns (created, changed, deleted).
    Events changed or added in Google are overwritten: the calendar is a view of the plan."""
    have: dict[str | None, list[dict[str, Any]]] = {}
    for e in events(service, calendar_id, time_min):
        have.setdefault(e.get("extendedProperties", {}).get("private", {}).get(KEY), []).append(e)
    created = changed = 0
    api = service.events()
    for block in blocks:
        body = event_body(block)
        existing = have.pop(block.key, [])
        if not existing:
            api.insert(calendarId=calendar_id, body=body).execute()
            created += 1
            continue
        first, *extra = existing
        have[None] = have.get(None, []) + extra
        if not same(first, body):
            api.update(calendarId=calendar_id, eventId=first["id"], body=body).execute()
            changed += 1
    stale = [e for group in have.values() for e in group]
    for e in stale:
        api.delete(calendarId=calendar_id, eventId=e["id"]).execute()
    return created, changed, len(stale)


def event_body(block: Block) -> dict[str, Any]:
    return {
        "summary": block.title,
        "start": {"dateTime": block.start},
        "end": {"dateTime": block.end},
        "status": "tentative" if block.tentative else "confirmed",
        "description": block.link or "",
        "extendedProperties": {"private": {KEY: block.key}},
    }


def same(event: dict[str, Any], body: dict[str, Any]) -> bool:
    # Google gives times back in the calendar's offset, so compare instants rather than strings.
    def moment(part: dict[str, Any]) -> datetime | None:
        return datetime.fromisoformat(part["dateTime"]) if "dateTime" in part else None

    return (
        event.get("summary") == body["summary"]
        and event.get("status") == body["status"]
        and (event.get("description") or "") == body["description"]
        and moment(event.get("start", {})) == moment(body["start"])
        and moment(event.get("end", {})) == moment(body["end"])
    )
