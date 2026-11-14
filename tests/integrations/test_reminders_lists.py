"""Which of your Reminders lists come into Friday (13 Nov: a client's Shopping List came in as tasks to plan), black
box, through the commands the box and the Mac app use: every list with a switch, all on, a new one on; one switched
off leaves Friday at once and stays in Reminders; switched on again, its to-dos come back as Reminders has them."""

from pathlib import Path

import pytest

from friday.integrations import sync
from friday.planner.store import load_settings
from tests.commands.helpers import new_app
from tests.integrations.contract import THU, World
from tests.integrations.fake_mac_reminders import HARNESS


@pytest.fixture
def w(tmp_path: Path) -> World:
    world = World(HARNESS, new_app(tmp_path), HARNESS.fake(""))
    world.fake.add("Milk", None, where="Shopping List")
    world.fake.add("Eggs", None, where="Shopping List")
    world.fake.add("Pay rent", THU, where="Home")
    world.connect()
    world.sync()
    return world


def titles(w: World) -> set[str]:
    return {i["title"] for i in w.items()}


def lists(w: World) -> dict[str, tuple[bool, int]]:
    return {t["name"]: (t["on"], t["made"]) for t in w.app.do("integration_lists", id=w.source_id)}


def shopping(w: World) -> str:
    return next(t["id"] for t in w.app.do("integration_lists", id=w.source_id) if t["name"] == "Shopping List")


def test_every_list_has_a_switch_all_on_with_what_each_brought_in(w: World) -> None:
    assert titles(w) == {"Milk", "Eggs", "Pay rent"}
    (box,) = w.app.do("integrations")
    assert box["lists"] is True and box["off_removes"] is True
    assert lists(w) == {"Shopping List": (True, 2), "Home": (True, 1)}
    assert shopping(w) == w.fake.list_id("Shopping List")  # known by EventKit's calendarIdentifier, not its title


def test_a_list_switched_off_leaves_friday_at_once_and_stays_in_reminders(w: World) -> None:
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    assert titles(w) == {"Pay rent"}, "its to-dos stayed until the next read"
    assert lists(w)["Shopping List"] == (False, 0)
    assert {i["title"] for i in w.items("dropped")} == {"Milk", "Eggs"}
    w.send()
    assert w.writes() == [] and not any(r["completed"] for r in w.fake.reminders.values()), "ticked in Reminders"
    w.sync()
    w.sync()
    assert titles(w) == {"Pay rent"} and not w.items("done"), "a list switched off came back, or was taken as done"


def test_switched_off_they_leave_even_when_asked_to_keep_them(w: World) -> None:
    """Notion's box asks keep or remove; Reminders' doesn't, so a keep sent anyway still takes them out."""
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False, keep=True)
    assert titles(w) == {"Pay rent"}


def test_switched_on_again_they_come_back_as_reminders_has_them(w: World) -> None:
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    milk = next(rid for rid, r in w.fake.reminders.items() if r["title"] == "Milk")
    eggs = next(rid for rid, r in w.fake.reminders.items() if r["title"] == "Eggs")
    w.fake.reminders[milk]["title"] = "Oat milk"
    w.fake.reminders[eggs]["completed"] = True
    w.fake.add("Bread", None, where="Shopping List")
    w.sync()
    assert titles(w) == {"Pay rent"}
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=True)
    w.sync()
    assert titles(w) == {"Pay rent", "Oat milk", "Bread"}
    assert lists(w)["Shopping List"] == (True, 2)


def test_one_moved_into_a_list_switched_off_leaves_friday_and_is_not_done(w: World) -> None:
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    rent = next(rid for rid, r in w.fake.reminders.items() if r["title"] == "Pay rent")
    w.fake.move_to(rent, "Shopping List")
    w.sync()
    assert titles(w) == set() and not w.items("done"), "moved into a list switched off, it was taken as done"
    w.send()
    assert not w.fake.reminders[rent]["completed"]
    w.fake.move_to(rent, "Home")
    w.sync()
    assert titles(w) == {"Pay rent"}


def test_a_new_list_comes_in_and_a_renamed_one_keeps_its_switch(w: World) -> None:
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    w.fake.add("Book flights", THU, where="Trip")
    w.fake.rename_list("Shopping List", "Groceries")
    w.sync()
    assert titles(w) == {"Pay rent", "Book flights"}
    assert lists(w) == {"Groceries": (False, 0), "Home": (True, 1), "Trip": (True, 1)}


def test_undo_brings_a_list_and_its_to_dos_back(w: World) -> None:
    out = w.app.full("integration_list_set", payload={"id": w.source_id, "list": shopping(w), "on": False},
                     provisional=False)  # fmt: skip
    w.app.do("undo", command_id=out.command_id)
    assert titles(w) == {"Milk", "Eggs", "Pay rent"} and lists(w)["Shopping List"] == (True, 2)
    w.sync()
    assert titles(w) == {"Milk", "Eggs", "Pay rent"}


def test_before_the_mac_app_has_sent_them_there_are_no_lists_and_nothing_is_read(tmp_path: Path) -> None:
    w = World(HARNESS, new_app(tmp_path), HARNESS.fake(""))
    w.connect()
    assert w.app.do("integration_lists", id=w.source_id) == []
    assert sync.sync_all(w.app.conn, load_settings(w.app.conn), w.app.now_utc, asked=True) == 0


def test_switched_on_again_they_are_back_at_once_with_what_friday_kept_of_them(w: World) -> None:
    milk = w.item("Milk")
    w.app.do("edit", id=milk["id"], duration_min=45)
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=True)
    assert titles(w) == {"Milk", "Eggs", "Pay rent"}, "back only at the next read"
    w.sync()
    assert titles(w) == {"Milk", "Eggs", "Pay rent"}
    assert w.item("Milk")["id"] == milk["id"] and w.item("Milk")["duration_min"] == 45


def test_one_you_dropped_yourself_stays_dropped_through_off_and_on(w: World) -> None:
    w.app.do("drop", id=w.item("Eggs")["id"])
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=True)
    w.sync()
    assert titles(w) == {"Milk", "Pay rent"}


def test_done_in_reminders_while_its_list_was_off_stays_out(w: World) -> None:
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=False)
    eggs = next(rid for rid, r in w.fake.reminders.items() if r["title"] == "Eggs")
    w.fake.reminders[eggs]["completed"] = True
    w.sync()
    w.app.do("integration_list_set", id=w.source_id, list=shopping(w), on=True)
    w.sync()
    assert titles(w) == {"Milk", "Pay rent"}
    config = next(s for s in w.app.table("sources") if s["id"] == w.source_id)["config"]
    assert '"held"' not in config, "the items held out weren't let go of once they were back or gone"
