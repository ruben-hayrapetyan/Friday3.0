"""Sorting what calendars bring in, by the small model (M13): each new event's kind among yours and a tidy title,
in one call per calendar per sync. Only a suggestion: the fixed rules stand in when there is no key or budget, and
you still accept everything. The client is passed in (the Anthropic SDK's, or a fake)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from friday.ingest.extract import MEANING, Client, call, maybe, told
from friday.ingest.ics import Event

SORTED = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "description": "Exactly one of the kinds listed"},
                    "title": {"type": "string", "description": "Short and plain, keeping course codes"},
                    "skip": {
                        "type": "boolean",
                        "description": "True only when the person's notes say this entry needs nothing from them",
                    },
                    "minutes": maybe("integer", "How long it takes, only when the person's notes say"),
                },
                "required": ["id", "kind", "title", "skip", "minutes"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Sorted:
    kind: str
    title: str
    skip: bool = False  # the person's notes say it needs nothing from them
    minutes: int | None = None  # how long, from the person's notes


def system(today: date, kinds: Mapping[str, bool], notes: Sequence[str] = ()) -> str:
    listed = "\n".join(
        f"- {name}: {MEANING.get(name, 'one of their own kinds')} ({'a set time' if fixed else 'due by a time'})"
        for name, fixed in kinds.items()
    )
    return (
        f"Today is {today:%A %Y-%m-%d}. These are entries from a student's calendars. For each, pick the one kind "
        f"that fits it best:\n{listed}\nAn entry with no length, or saying it is due, is something due by then. "
        "A calendar's name is a strong hint (a 'Homework' calendar holds things due). Give a short, plain title: "
        "keep course codes, drop words like 'Due' and bracketed course tags only when the title keeps the course."
    ) + told(notes)


def described(e: Event, calendar: str) -> dict[str, Any]:
    if e.start:
        when = f"{e.start[:10]} {e.start[11:16]}" + (
            f"–{e.end[11:16]}" if e.end and e.end != e.start else " (no length)"
        )
    else:
        when = f"{e.day}, all day"
    return {"title": e.summary, "calendar": calendar, "when": when, "repeats": bool(e.series or e.every)}


def sort_events(
    client: Client,
    model: str,
    events: Sequence[tuple[str, Event]],
    calendar: str,
    kinds: Mapping[str, bool],
    today: date,
    notes: Sequence[str] = (),
) -> tuple[dict[str, Sorted], int]:
    """Each event's kind and title (and what the notes say of it) by id, only kinds that exist; the tokens spent."""
    asked = [{"id": key} | described(e, calendar) for key, e in events]
    text = [{"type": "text", "text": json.dumps(asked, ensure_ascii=False)}]
    found, used = call(client, model, system(today, kinds, notes), text, SORTED)
    out = {}
    for item in found.get("items", []):
        if item.get("kind") in kinds and item.get("id") and item.get("title"):
            minutes = item.get("minutes")
            sized = minutes if isinstance(minutes, int) and 0 < minutes <= 24 * 60 else None
            out[str(item["id"])] = Sorted(item["kind"], item["title"].strip(), bool(item.get("skip")), sized)
    return out, used
