"""Calendars you hid, and what of theirs stays out of sight (14 Nov: a client set calendars to "Hide" in Setup's walk,
and their invitations still came into the Inbox). One notion, read by every place an event reaches you.

A calendar is hidden when its name is among `calendar_look.toolbar` (core/calendars.hidden_calendars): the
calendars with a Show button in the plan's header. Friday keeps reading it, and plans around its events when you
count it as busy (`busy.calendars`, a choice of its own), but nothing of it surfaces: not its events (shown in the plan
only while you switch it on under Show), not what it suggests (new events, changes, invitations), not an invitation
that came by mail too. It's all read at the moment it's asked for, so hiding a calendar takes its things away at once
and showing it again brings them back; nothing is deleted.

Where an event came from: the latest suggestion you (or a trusted calendar) accepted for it names its source, a
Google calendar, one of the Mac's or a calendar link (ics), by the source's name; an event made here and saved to a
calendar is that calendar's (`event_writes`), before the calendar reads it back."""

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from friday.core.calendars import hidden_calendars
from friday.core.db import rows
from friday.planner.store import kv_get

CALENDAR_KINDS = ("gcal", "mac", "ics")  # the sources that are calendars: Google's, the Mac's and calendar links


@dataclass(frozen=True)
class Hidden:
    """What a hidden calendar keeps out of sight, as it stands now."""

    names: frozenset[str] = frozenset()  # the calendars you hid
    sources: frozenset[int] = frozenset()  # their sources (any calendar kind) by id
    events: dict[int, str] = field(default_factory=dict)  # events on them, by item id: the calendar's name
    suggestions: frozenset[int] = frozenset()  # suggestions of theirs, waiting or set aside, by id

    def __bool__(self) -> bool:
        return bool(self.names)

    def calendar(self, item_id: int | None) -> str | None:
        """The hidden calendar an event is on, or None when it shows."""
        return self.events.get(item_id) if item_id is not None else None


NOTHING = Hidden()


def written_to(conn: sqlite3.Connection, user_id: int) -> dict[int, str | None]:
    """Each event made here on its way to a calendar (saved within the minute), by item id: the calendar's name.
    Google's calendars and the Mac's: your Gmail calendar is written through the Mac (28 Oct: until the Mac read it
    back it wore no calendar, so no color)."""
    names = {
        c["id"]: c.get("source_name", c["name"])
        for key in ("google_calendars", "mac_calendars")
        for c in kv_get(conn, key, [], user_id) or []
    }
    found = rows(
        conn, "SELECT item_id, calendar_id FROM event_writes WHERE user_id = ? AND calendar_id IS NOT NULL", [user_id]
    )
    return {r["item_id"]: names.get(r["calendar_id"]) for r in found}


def event_calendars(conn: sqlite3.Connection, user_id: int) -> dict[int, str]:
    """Each event's calendar by item id, every kind of calendar: the source of the latest suggestion accepted for it,
    else the calendar it's being saved to."""
    found = rows(
        conn,
        "SELECT s.item_id, src.name FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "JOIN sources src ON src.id = r.source_id JOIN items i ON i.id = s.item_id WHERE s.user_id = ? "
        f"AND s.status = 'accepted' AND i.when_kind = 'fixed' AND src.kind IN ({', '.join('?' * len(CALENDAR_KINDS))}) "
        "ORDER BY s.id",
        [user_id, *CALENDAR_KINDS],
    )
    linked = {r["item_id"]: r["name"] for r in found}
    return {k: v for k, v in written_to(conn, user_id).items() if v} | linked


def hidden_of(conn: sqlite3.Connection, settings: dict[str, Any], user_id: int) -> Hidden:
    """What the calendars you hid keep out of sight now; NOTHING when you hid none (nothing more is read)."""
    names = hidden_calendars(settings["calendar_look"])
    if not names:
        return NOTHING
    marks = ", ".join("?" * len(CALENDAR_KINDS))
    sources = frozenset(
        r["id"]
        for r in rows(
            conn, f"SELECT id, name FROM sources WHERE user_id = ? AND kind IN ({marks})", [user_id, *CALENDAR_KINDS]
        )  # fmt: skip
        if r["name"] in names
    )
    events = {k: name for k, name in event_calendars(conn, user_id).items() if name in names}
    return Hidden(names, sources, with_their_repeats(conn, events), hidden_suggestions(conn, user_id, sources, events))


def with_their_repeats(conn: sqlite3.Connection, events: dict[int, str]) -> dict[int, str]:
    """The events, and every other time of a repeat one of them belongs to (a repeating event imported from the
    calendar): its weeks are the calendar's too."""
    series = series_of(conn, events)
    if not series:
        return events
    found = rows(conn, f"SELECT id, series_id FROM items WHERE when_kind = 'fixed' AND series_id IN ({marks(series)})",
                 sorted(series))  # fmt: skip
    return {r["id"]: series[r["series_id"]] for r in found} | events


def series_of(conn: sqlite3.Connection, events: dict[int, str]) -> dict[int, str]:
    """The repeats these events belong to, by series id: the calendar's name."""
    if not events:
        return {}
    found = rows(conn, f"SELECT id, series_id FROM items WHERE series_id IS NOT NULL AND id IN ({marks(events)})",
                 sorted(events))  # fmt: skip
    return {r["series_id"]: events[r["id"]] for r in found}


def hidden_series(conn: sqlite3.Connection, hidden: Hidden) -> frozenset[int]:
    """The repeats a hidden calendar's events belong to (an imported repeating event), by series id."""
    return frozenset(series_of(conn, hidden.events))


def marks(ids: Any) -> str:
    return ", ".join("?" * len(ids))


def hidden_suggestions(
    conn: sqlite3.Connection, user_id: int, sources: frozenset[int], events: dict[int, str]
) -> frozenset[int]:
    """The suggestions waiting or set aside that belong to a hidden calendar: what it sent (new events, changes,
    invitations, the times of a repeat); a change, from anywhere, to one of its events; and one from mail (or anywhere
    else) for the same thing as one of its own, which the Inbox set aside as a twin (duplicates.set_aside_waiting): an
    invitation mailed to you and put on the calendar too is the calendar's."""
    found = rows(
        conn,
        "SELECT s.id, s.command, s.input, s.duplicate_of, r.source_id FROM suggestions s "
        "LEFT JOIN raw_inputs r ON r.id = s.raw_input_id WHERE s.user_id = ? AND s.status IN ('pending', 'superseded')",
        [user_id],
    )
    out = set()
    for s in found:
        target = json.loads(s["input"] or "{}").get("id") if s["command"] in ("edit", "drop") else None
        if s["source_id"] in sources or target in events or s["duplicate_of"] in events:
            out.add(s["id"])
    twins = kv_get(conn, "set_aside_twins", {}, user_id) or {}  # a later suggestion's id: the earlier one waiting
    for later, earlier in twins.items():
        if int(later) in out or earlier in out:
            out |= {int(later), earlier}
    return frozenset(out)
