"""A stand-in for Friday's Mac app reading Apple Reminders (C100): it keeps reminders as EventKit would give them,
pushes the open ones (`reminders_sync`) when Friday syncs, and does what waits for Reminders (`reminder_writes`),
reporting each (`reminder_written`); told to, it fails one, as a reminder deleted meanwhile would."""

import itertools
from typing import Any

from tests.integrations.kit import Harness


class FakeMacReminders:
    host = "this Mac"
    transport = None  # nothing over the internet
    kind = "reminders"
    list_name = "Reminders"

    def __init__(self, token: str = ""):
        self.reminders: dict[str, dict[str, Any]] = {}
        self.ids = itertools.count(1)
        self.done_log: list[str] = []
        self.failing = 0
        self.requests: list[Any] = []  # nothing goes over the internet

    def add(self, title: str, due: str | None = None, minutes: int | None = None) -> str:
        rid = f"x-apple-reminder://{next(self.ids):04X}"
        self.reminders[rid] = {"id": rid, "title": title, "due": due, "list": self.list_name, "completed": False}
        return rid

    def fail_next(self, status: int = 0, times: int = 1, headers: Any = None) -> None:
        self.failing += times

    def push(self, app: Any) -> None:
        """As the app does: only while Friday wants Reminders read (it stops once you disconnect)."""
        if not app.do("reminder_writes", kind=self.kind)["wanted"]:
            return
        open_ = [r for r in self.reminders.values() if not r["completed"]]
        app.do("reminders_sync", kind=self.kind, reminders=open_, lists=[self.list_name])

    def deliver(self, app: Any) -> int:
        made = 0
        for job in app.do("reminder_writes", kind=self.kind)["jobs"]:
            if self.failing:
                self.failing -= 1
                app.do("reminder_written", id=job["id"], ok=False, error="The reminder couldn't be saved")
                continue
            self.reminders[job["external_id"]]["completed"] = job["op"] == "done"
            self.done_log.append(f"{job['op']} {job['external_id']}")
            app.do("reminder_written", id=job["id"], ok=True)
            made += 1
        return made

    def writes(self) -> list[str]:
        return list(self.done_log)


def _move(fake: FakeMacReminders, rid: str, due: str) -> None:
    fake.reminders[rid]["due"] = due


HARNESS = Harness(
    kind="reminders",
    token="",
    fake=FakeMacReminders,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due, minutes),
    move=_move,
    rename=lambda fake, rid, title: fake.reminders[rid].update(title=title),
    finish=lambda fake, rid: fake.reminders[rid].update(completed=True),
    is_done=lambda fake, rid: fake.reminders[rid]["completed"],
    two_way=True,
    lengths=False,
    on_mac=True,
)
