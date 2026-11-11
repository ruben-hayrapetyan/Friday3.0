"""Things 3 through the Mac app (C108), glass box: a deadline is the deadline, a When date alone is a soft due, the
list it's in said in the notes; Things missing from the Mac, or macOS saying no to Automation, said on the box in
words with what to do; the Mac app asked to read Things only while it's connected, Reminders' asks kept apart."""

from pathlib import Path

import pytest

from friday.integrations.reminders import Things
from tests.commands.helpers import new_app
from tests.integrations.contract import World
from tests.integrations.fake_mac_things import HARNESS


@pytest.fixture
def w(tmp_path: Path) -> World:
    return World(HARNESS, new_app(tmp_path), HARNESS.fake(""))


def test_a_deadline_is_firm_and_a_when_date_alone_is_the_day_you_meant() -> None:
    firm = Things.remote({"id": "a", "title": "File taxes", "due": "2026-11-20", "when": "2026-11-18", "list": "Today"})
    assert (firm.due, firm.firm, firm.notes) == ("2026-11-20", True, "In Things: Today")
    soft = Things.remote({"id": "b", "title": "Call mom", "when": "2026-11-18", "list": "Upcoming"})
    assert (soft.due, soft.firm) == ("2026-11-18", False)
    assert Things.remote({"id": "c", "title": "Someday-ish", "list": "Anytime"}).due is None


def test_things_missing_or_automation_refused_is_said_with_what_to_do(w: World) -> None:
    source = w.connect()
    w.app.do("reminders_sync", kind="things", missing=True)
    assert "install Things 3" in w.app.do("integrations")[0]["last_error"]
    w.app.do("reminders_sync", kind="things", denied=True)
    assert "Privacy & Security → Automation" in w.app.do("integrations")[0]["last_error"]
    w.fake.add("Write", "2026-10-22")
    w.sync()
    assert [c["last_error"] for c in w.app.do("integrations") if c["id"] == source] == [None]  # allowed: cleared


def test_the_mac_app_is_asked_for_things_only_while_things_is_connected(w: World) -> None:
    assert w.app.do("reminder_writes", kind="things")["wanted"] is False
    w.connect()
    assert w.app.do("reminder_writes", kind="things")["wanted"] is True
    assert w.app.do("reminder_writes")["wanted"] is False  # Reminders' own ask is apart: not connected
