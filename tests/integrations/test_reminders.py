"""Apple Reminders through the Mac app (C100), glass box: what a reminder reads as, macOS saying no, the Mac app asked
only while Reminders is connected, a change the Mac app couldn't make retried and then said, and the server never
sending Reminders' changes itself."""

from pathlib import Path

import pytest

from friday.commands.reminders import DENIED
from friday.core.items import FieldError
from friday.integrations import sync
from friday.integrations.reminders import Reminders, list_of, remote
from tests.commands.helpers import new_app
from tests.integrations.contract import THU, World
from tests.integrations.fake_mac_reminders import HARNESS


@pytest.fixture
def w(tmp_path: Path) -> World:
    return World(HARNESS, new_app(tmp_path), HARNESS.fake(""))


def test_a_reminder_reads_with_its_list_in_its_notes_and_its_due_to_the_minute() -> None:
    r = remote({"id": "x-1", "title": " Pay rent ", "notes": "Landlord's account", "due": "2026-11-01T09:00:00",
                "list": "Home", "url": "https://bank.example"})  # fmt: skip
    assert (r.title, r.due, r.url, r.firm) == ("Pay rent", "2026-11-01T09:00", "https://bank.example", True)
    assert r.notes == "Landlord's account\n\nIn Reminders: Home"
    assert remote({"id": "x-2", "title": "Laundry", "due": "2026-11-02"}).due == "2026-11-02"


def test_it_is_a_to_do_app_on_the_mac_with_no_token_and_both_ways() -> None:
    caps = Reminders.caps
    assert caps.on_mac and caps.two_way and caps.kind == "Task" and not caps.lengths
    assert Reminders().check() == "this Mac's Reminders"


def test_the_mac_app_is_asked_to_read_only_while_reminders_is_connected(w: World) -> None:
    assert w.app.do("reminder_writes") == {"wanted": False, "jobs": []}
    with pytest.raises(FieldError, match="isn't connected"):
        w.app.do("reminders_sync", reminders=[])
    source = w.connect()
    assert w.app.do("reminder_writes")["wanted"] is True
    w.app.do("integration_disconnect", id=source, keep=True)
    assert w.app.do("reminder_writes")["wanted"] is False


def test_macos_saying_no_is_said_on_the_box_with_where_to_allow_it(w: World) -> None:
    source = w.connect()
    w.app.do("reminders_sync", denied=True)
    (said,) = [c["last_error"] for c in w.app.do("integrations") if c["id"] == source]
    assert said == DENIED and "Privacy & Security → Reminders" in said


def test_a_change_the_mac_app_couldnt_make_is_kept_tried_again_then_said(w: World) -> None:
    rid = w.h.add(w.fake, "Call mom", THU)
    source = w.connect()
    w.sync()
    w.app.do("done", id=w.item("Call mom")["id"])
    w.fake.fail_next(times=sync.MAX_TRIES)
    for _ in range(sync.MAX_TRIES):
        w.send()
    assert not w.h.is_done(w.fake, rid)
    (said,) = [c["last_error"] for c in w.app.do("integrations") if c["id"] == source]
    assert said and "couldn't be saved" in said
    assert w.app.do("reminder_writes")["jobs"] == []  # given up after MAX_TRIES, not asked forever


def test_the_server_never_sends_reminders_changes_itself(w: World) -> None:
    w.h.add(w.fake, "Call mom", THU)
    w.connect()
    w.sync()
    w.app.do("done", id=w.item("Call mom")["id"])
    assert sync.send_writes(w.app.conn, w.app.now_utc) == 0  # left for the Mac app
    assert len(w.app.do("reminder_writes")["jobs"]) == 1
    with pytest.raises(AssertionError, match="the Mac app sends Reminders' changes"):
        Reminders().write("x-1", "done")  # were it ever asked to, it refuses rather than sending nothing silently


def test_a_report_on_a_change_that_isnt_reminders_is_refused(w: World) -> None:
    with pytest.raises(FieldError, match="no such change"):
        w.app.do("reminder_written", id=999, ok=True)


# Which lists come in (13 Nov), glass box: the connector's own reading of the lists the Mac app sent


def sent(*reminders: dict, lists: list | None = None) -> Reminders:
    """A connector as `load` leaves it, the Mac app having sent these, with `config` set on it by the caller."""
    connector = Reminders()
    connector.sent = {"reminders": list(reminders), "lists": lists or []}
    return connector


HOME = {"id": "CAL-HOME", "title": "Home"}
SHOPPING = {"id": "CAL-SHOP", "title": "Shopping List"}
MILK = {"id": "r-1", "title": "Milk", "list": "Shopping List", "list_id": "CAL-SHOP"}
RENT = {"id": "r-2", "title": "Pay rent", "list": "Home", "list_id": "CAL-HOME"}


def test_lists_are_known_by_eventkits_id_and_by_title_from_a_mac_app_that_sent_no_ids() -> None:
    assert [(t.id, t.name, t.team) for t in sent(lists=[HOME, SHOPPING]).lists()] == [
        ("CAL-HOME", "Home", False), ("CAL-SHOP", "Shopping List", False)]  # fmt: skip
    assert [(t.id, t.name) for t in sent(lists=["Home"]).lists()] == [("Home", "Home")]
    assert sent().lists() == []
    assert list_of(MILK) == "CAL-SHOP"
    assert list_of({"id": "r", "list": "Home"}) == "Home"  # no id sent: its title
    assert list_of({"id": "r"}) == ""


def test_every_list_is_read_until_switched_off_and_a_new_one_is_on() -> None:
    connector = sent(MILK, RENT, lists=[HOME, SHOPPING])
    assert {r.title for r in connector.read()} == {"Milk", "Pay rent"}
    connector.chosen = {"CAL-SHOP": False}
    assert [r.title for r in connector.read()] == ["Pay rent"]
    assert connector.held_back() == {"r-1"}
    assert connector.members("CAL-SHOP") == {"r-1"} and connector.members("CAL-HOME") == {"r-2"}
    assert [connector.on(t) for t in connector.lists()] == [True, False]


def test_a_list_back_under_a_new_id_keeps_the_choice_made_for_its_name() -> None:
    connector = sent(dict(MILK, list_id="CAL-NEW"), lists=[HOME, {"id": "CAL-NEW", "title": "Shopping List"}])
    connector.chosen, connector.names = {"CAL-SHOP": False}, {"CAL-SHOP": "Shopping List"}
    assert [r.title for r in connector.read()] == []  # iCloud rebuilt it: still off
    renamed = sent(lists=[{"id": "CAL-SHOP", "title": "Groceries"}, {"id": "CAL-2", "title": "Shopping List"}])
    renamed.chosen, renamed.names = {"CAL-SHOP": False}, {"CAL-SHOP": "Shopping List"}
    # the list switched off is still there, renamed: a new list that took its old name is a new list, on
    assert [renamed.on(t) for t in renamed.lists()] == [False, True]


def test_things_reads_every_list_whatever_is_switched() -> None:
    from friday.integrations.reminders import Things

    things = Things(config={"lists": {"Today": False}})
    things.sent = {"reminders": [{"id": "t-1", "title": "Call", "list": "Today"}], "lists": ["Today"]}
    assert [r.title for r in things.read()] == ["Call"] and things.held_back() == set()
    assert not Things.caps.lists and Reminders.caps.lists and Reminders.caps.off_removes
