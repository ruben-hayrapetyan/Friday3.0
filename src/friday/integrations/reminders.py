"""Apple Reminders (C96, your choice: both ways; C100), the one integration on the Mac itself: no account, no token,
nothing over the internet. Friday's Mac app reads your open reminders through EventKit (Mac/Sources/RemindersBridge)
once you connect it here, and posts them (`reminders_sync`); they go through the same shared sync as Todoist's.
The other way, done or opened again in Friday waits in the outbox like any integration's, but the Mac app is what
sends it: it asks for them (`reminder_writes`), ticks the reminder in Reminders, and says so (`reminder_written`).

A reminder's due date is its deadline (Reminders keeps one date); a whole-day one is due by the end of its day.

Which lists come in (13 Nov, a client's Shopping List came in as tasks to plan): every list has a switch in the box,
all on, a new list on (`config["lists"]`, as Notion's). A list is known by EventKit's calendarIdentifier, which stays
when you rename it; one that comes back under a new id (iCloud rebuilt its copy) keeps the choice made for its name.
Your answer: a list switched off takes its to-dos out of Friday at once (they stay in Reminders, nothing is ticked),
and so does one moved there in Reminders; switched on again, they come back as Reminders has them."""

import dataclasses
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, Remote, Transport

KV = "mac_reminders"  # what the Mac app last sent: {"at": …, "lists": […], "reminders": […]}


@dataclass(frozen=True)
class MacList:
    """One of your lists in Reminders, as the box shows it."""

    id: str  # EventKit's calendarIdentifier; its title, from a Mac app that didn't send ids
    name: str
    team: bool = False


def list_of(r: dict[str, Any]) -> str:
    """The list a reminder is in: its id, or its title from a Mac app that didn't send ids."""
    return str(r.get("list_id") or r.get("list") or "")


class Reminders:
    kind: ClassVar[str] = "reminders"
    name: ClassVar[str] = "Apple Reminders"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Task", on_mac=True, lists=True, off_removes=True)
    kv: ClassVar[str] = KV

    def __init__(self, token: str = "", config: dict[str, Any] | None = None, transport: Transport = None):
        self.sent: dict[str, Any] | None = None  # filled by `load`: the Mac app's last reading
        self.chosen: dict[str, bool] = dict((config or {}).get("lists") or {})
        self.names: dict[str, str] = dict((config or {}).get("list_names") or {})  # a choice's list, by its title

    def load(self, conn: sqlite3.Connection, user_id: int) -> None:
        found = conn.execute("SELECT value FROM kv WHERE user_id = ? AND key = ?", [user_id, self.kv]).fetchone()
        self.sent = json.loads(found[0]) if found else None

    def check(self) -> str:
        return f"this Mac's {self.name.removeprefix('Apple ')}"

    def read(self) -> list[Remote]:
        """The open reminders the Mac app last sent; none yet when it hasn't (so nothing is taken as done)."""
        if self.sent is None:
            raise WaitingForMac
        reading = self.reading()
        return [self.remote(r) for r in self.open() if reading(list_of(r))]

    def open(self) -> list[dict[str, Any]]:
        return [r for r in (self.sent or {}).get("reminders", []) if not r.get("completed")]

    def lists(self) -> list[MacList]:
        """Your lists as the Mac app last sent them; none before it has (or from a Mac app that didn't send them)."""
        sent = (self.sent or {}).get("lists") or []
        return [MacList(str(x), str(x)) if isinstance(x, str) else MacList(str(x["id"]), str(x.get("title") or ""))
                for x in sent]  # fmt: skip

    def on(self, t: MacList, here: set[str] | None = None) -> bool:
        """Read now: as you switched it; one you haven't, on, unless a list of that name you switched is gone (the
        same list under a new id). `here`: the ids of the lists there now."""
        if t.id in self.chosen:
            return self.chosen[t.id]
        here = here if here is not None else {x.id for x in self.lists()}
        gone = [i for i, name in self.names.items() if name == t.name and i not in here and i in self.chosen]
        same = [self.chosen[i] for i in gone]
        return same[-1] if same else True

    def reading(self) -> Callable[[str], bool]:
        """Whether a list (by id) is read now; every one, for Things, whose lists are views (Today, Upcoming) a to-do
        moves between by itself."""
        if not self.caps.lists:
            return lambda _: True
        lists = self.lists()
        here = {t.id for t in lists}
        on = {t.id: self.on(t, here) for t in lists}
        return lambda list_id: on.get(list_id, self.chosen.get(list_id, True))

    def members(self, list_id: str) -> set[str]:
        """The open to-dos in one of its lists, by id (Reminders' ids don't carry their list, as Notion's do)."""
        return {str(r["id"]) for r in self.open() if list_of(r) == list_id}

    def held_back(self) -> set[str]:
        """Open in Reminders, in a list switched off: not done, only not in Friday."""
        reading = self.reading()
        return {str(r["id"]) for r in self.open() if not reading(list_of(r))}

    @staticmethod
    def remote(r: dict[str, Any]) -> Remote:
        return remote(r)

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        raise AssertionError("the Mac app sends Reminders' changes (reminder_writes), not the server")


class WaitingForMac(Exception):
    """Connected, but the Mac app hasn't sent your reminders yet (it asks macOS first)."""


class Things(Reminders):
    """Things 3 (C96, your choice: both ways; C108), read and ticked by Friday's Mac app through Things' AppleScript
    (Mac/Sources/ThingsBridge.swift), as Reminders is through EventKit: its Inbox, Today, Anytime and Upcoming, not
    Someday. A Things deadline is the deadline; a "When" date alone is the day you meant to do it, soft (C97: follow
    the service, as Todoist's due beside its deadline)."""

    kind: ClassVar[str] = "things"
    name: ClassVar[str] = "Things"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Task", on_mac=True)
    kv: ClassVar[str] = "mac_things"

    @staticmethod
    def remote(r: dict[str, Any]) -> Remote:
        made = remote(r, where="Things")
        if made.due or not r.get("when"):
            return made
        return dataclasses.replace(made, due=str(r["when"])[:16], firm=False)


def remote(r: dict[str, Any], where: str = "Reminders") -> Remote:
    due = r.get("due") or None
    notes = str(r.get("notes") or "")
    place = str(r.get("list") or "")
    return Remote(
        external_id=str(r["id"]),
        title=str(r.get("title") or "Untitled reminder").strip(),
        due=due[:16] if due else None,
        notes=(f"{notes}\n\nIn {where}: {place}" if place else notes).strip(),
        url=r.get("url") or None,
        done=bool(r.get("completed")),
        firm=True,
    )
