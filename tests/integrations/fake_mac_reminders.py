"""A stand-in for Friday's Mac app reading Apple Reminders (C100): it keeps reminders as EventKit would give them,
pushes the open ones (`reminders_sync`) when Friday syncs, with your lists by EventKit's calendarIdentifier, and does
what waits for Reminders (`reminder_writes`), reporting each (`reminder_written`); told to, it fails one, as a reminder
deleted meanwhile would."""

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
        self.lists: dict[str, str] = {}  # calendarIdentifier: title, as EventKit has them

    def add(self, title: str, due: str | None = None, minutes: int | None = None, where: str | None = None) -> str:
        rid = f"x-apple-reminder://{next(self.ids):04X}"
        self.reminders[rid] = {"id": rid, "title": title, "due": due, "completed": False}
        self.move_to(rid, where or self.list_name)
        return rid

    def list_id(self, title: str) -> str:
        """The list of that title, made if it isn't there yet (an id like EventKit's, which a rename keeps)."""
        found = next((i for i, t in self.lists.items() if t == title), None)
        if found is None:
            found = f"CAL-{len(self.lists) + 1:04d}-{title.upper().replace(' ', '')}"
            self.lists[found] = title
        return found

    def move_to(self, rid: str, title: str) -> None:
        """Into another list, as dragging it in Reminders does."""
        self.reminders[rid].update(list=title, list_id=self.list_id(title))

    def rename_list(self, title: str, to: str) -> None:
        list_id = self.list_id(title)
        self.lists[list_id] = to
        for r in self.reminders.values():
            if r.get("list_id") == list_id:
                r["list"] = to

    def sent_lists(self) -> list[Any]:
        return [{"id": i, "title": t} for i, t in self.lists.items()]

    def fail_next(self, status: int = 0, times: int = 1, headers: Any = None) -> None:
        self.failing += times

    def push(self, app: Any) -> None:
        """As the app does: only while Friday wants Reminders read (it stops once you disconnect)."""
        if not app.do("reminder_writes", kind=self.kind)["wanted"]:
            return
        open_ = [r for r in self.reminders.values() if not r["completed"]]
        app.do("reminders_sync", kind=self.kind, reminders=open_, lists=self.sent_lists())

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
