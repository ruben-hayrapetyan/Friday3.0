"""A stand-in for Friday's Mac app reading Things 3 through its AppleScript (C108), as the Reminders one does
EventKit: to-dos as Things gives them (an id, a name, notes, a deadline as `due`, a When date as `when`, the list
they're in), pushed while Friday wants Things read, and done or opened again in Things when Friday asks."""

import itertools

from tests.integrations.fake_mac_reminders import FakeMacReminders
from tests.integrations.kit import Harness


class FakeMacThings(FakeMacReminders):
    kind = "things"
    list_name = "Anytime"

    def __init__(self, token: str = ""):
        super().__init__(token)
        self.ids = itertools.count(1)

    def add(self, title: str, due: str | None = None, minutes: int | None = None, when: str | None = None,
            where: str = "Anytime") -> str:  # fmt: skip
        tid = f"7Yb{next(self.ids):05d}Qx"  # Things' ids: short, opaque
        self.reminders[tid] = {"id": tid, "title": title, "due": due, "when": when, "list": where, "completed": False}
        return tid

    def sent_lists(self) -> list[str]:
        return [self.list_name]  # Things' lists by title, as ThingsBridge sends them


def _move(fake: FakeMacThings, tid: str, due: str) -> None:
    fake.reminders[tid]["due"] = due


HARNESS = Harness(
    kind="things",
    token="",
    fake=FakeMacThings,
    add=lambda fake, title, due=None, minutes=None: fake.add(title, due, minutes),
    move=_move,
    rename=lambda fake, tid, title: fake.reminders[tid].update(title=title),
    finish=lambda fake, tid: fake.reminders[tid].update(completed=True),
    is_done=lambda fake, tid: fake.reminders[tid]["completed"],
    two_way=True,
    lengths=False,
    on_mac=True,
)
