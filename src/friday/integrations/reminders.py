"""Apple Reminders (C96, your choice: both ways; C100), the one integration on the Mac itself: no account, no token,
nothing over the internet. Friday's Mac app reads your open reminders through EventKit (Mac/Sources/RemindersBridge)
once you connect it here, and posts them (`reminders_sync`); they go through the same shared sync as Todoist's.
The other way, done or opened again in Friday waits in the outbox like any integration's, but the Mac app is what
sends it: it asks for them (`reminder_writes`), ticks the reminder in Reminders, and says so (`reminder_written`).

A reminder's due date is its deadline (Reminders keeps one date); a whole-day one is due by the end of its day."""

import dataclasses
import json
import sqlite3
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, Remote, Transport

KV = "mac_reminders"  # what the Mac app last sent: {"at": …, "lists": […], "reminders": […]}


class Reminders:
    kind: ClassVar[str] = "reminders"
    name: ClassVar[str] = "Apple Reminders"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Task", on_mac=True)
    kv: ClassVar[str] = KV

    def __init__(self, token: str = "", config: dict[str, Any] | None = None, transport: Transport = None):
        self.sent: dict[str, Any] | None = None  # filled by `load`: the Mac app's last reading

    def load(self, conn: sqlite3.Connection, user_id: int) -> None:
        found = conn.execute("SELECT value FROM kv WHERE user_id = ? AND key = ?", [user_id, self.kv]).fetchone()
        self.sent = json.loads(found[0]) if found else None

    def check(self) -> str:
        return f"this Mac's {self.name.removeprefix('Apple ')}"

    def read(self) -> list[Remote]:
        """The open reminders the Mac app last sent; none yet when it hasn't (so nothing is taken as done)."""
        if self.sent is None:
            raise WaitingForMac
        return [self.remote(r) for r in self.sent.get("reminders", []) if not r.get("completed")]

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
