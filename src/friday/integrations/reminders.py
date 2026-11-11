"""Apple Reminders (C96, your choice: both ways; C100), the one integration on the Mac itself: no account, no token,
nothing over the internet. Friday's Mac app reads your open reminders through EventKit (Mac/Sources/RemindersBridge)
once you connect it here, and posts them (`reminders_sync`); they go through the same shared sync as Todoist's.
The other way, done or opened again in Friday waits in the outbox like any integration's, but the Mac app is what
sends it: it asks for them (`reminder_writes`), ticks the reminder in Reminders, and says so (`reminder_written`).

A reminder's due date is its deadline (Reminders keeps one date); a whole-day one is due by the end of its day."""

import json
import sqlite3
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, Remote, Transport

KV = "mac_reminders"  # what the Mac app last sent: {"at": …, "lists": […], "reminders": […]}


class Reminders:
    kind: ClassVar[str] = "reminders"
    name: ClassVar[str] = "Apple Reminders"
    caps: ClassVar[Caps] = Caps(two_way=True, lengths=False, kind="Task", on_mac=True)

    def __init__(self, token: str = "", config: dict[str, Any] | None = None, transport: Transport = None):
        self.sent: dict[str, Any] | None = None  # filled by `load`: the Mac app's last reading

    def load(self, conn: sqlite3.Connection, user_id: int) -> None:
        found = conn.execute("SELECT value FROM kv WHERE user_id = ? AND key = ?", [user_id, KV]).fetchone()
        self.sent = json.loads(found[0]) if found else None

    def check(self) -> str:
        return "this Mac's Reminders"

    def read(self) -> list[Remote]:
        """The open reminders the Mac app last sent; none yet when it hasn't (so nothing is taken as done)."""
        if self.sent is None:
            raise WaitingForMac
        return [remote(r) for r in self.sent.get("reminders", []) if not r.get("completed")]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        raise AssertionError("the Mac app sends Reminders' changes (reminder_writes), not the server")


class WaitingForMac(Exception):
    """Connected, but the Mac app hasn't sent your reminders yet (it asks macOS first)."""


def remote(r: dict[str, Any]) -> Remote:
    due = r.get("due") or None
    notes = str(r.get("notes") or "")
    where = str(r.get("list") or "")
    return Remote(
        external_id=str(r["id"]),
        title=str(r.get("title") or "Untitled reminder").strip(),
        due=due[:16] if due else None,
        notes=(f"{notes}\n\nIn Reminders: {where}" if where else notes).strip(),
        url=r.get("url") or None,
        done=bool(r.get("completed")),
        firm=True,
    )
