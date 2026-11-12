"""Checking your tasks: copies of one task found and merged (its time logged kept), told apart, and everything
Friday brought in gone over again. The same event on two calendars makes one task."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import SINCE, UNTIL, calendar, mac_event


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def add(app: App, title: str, **fields: object) -> int:
    return int(
        app.do("add", title=title, preset="Assignment", due="2026-10-23T23:59", duration_min=120, **fields)["item"][
            "id"
        ]
    )


def test_copies_are_found_and_one_is_kept_with_the_time_logged_on_the_others(app: App) -> None:
    first, second = add(app, "Psych WA7 draft"), add(app, "psych  WA7 Draft")
    other = add(app, "Math HW9")
    app.do("log", id=second, start="2026-10-19T08:00", end="2026-10-19T08:30")
    out = app.do("duplicates")
    assert [(g["key"], g["keep"], [i["id"] for i in g["items"]]) for g in out["groups"]] == [
        ("psych wa 7 draft", second, [first, second])  # the one with time logged on it
    ]
    said = app.full("duplicates_merge", payload={"groups": [{"keep": first, "drop": [second]}]}, provisional=False)
    assert said.result["message"] == "Removed 1 copy; one of each kept"
    assert app.do("duplicates")["groups"] == []
    kept = app.do("item", id=first)["item"]
    assert kept["done_min"] == 30 and app.do("item", id=second)["item"]["status"] == "dropped"
    assert app.do("item", id=other)["item"]["status"] == "todo"
    app.do("undo", command_id=said.command_id)
    assert len(app.do("duplicates")["groups"]) == 1 and app.do("item", id=second)["item"]["done_min"] == 30


def test_ones_you_say_arent_the_same_stop_being_asked_about(app: App) -> None:
    ids = [add(app, "Reading"), add(app, "Reading")]
    app.do("not_duplicates", ids=ids)
    assert app.do("duplicates")["groups"] == []
    add(app, "Reading")  # a third one is a new question
    assert len(app.do("duplicates")["groups"]) == 1


def test_a_suggestion_asked_about_anyway_doesnt_break_the_check_for_copies(app: App) -> None:
    """29 Oct: copies failed to load ('int' object is not iterable): "Add anyway" kept a suggestion's id under the
    same key as the pairs kept apart. Both are kept now, and an old single id there is read as asked about anyway."""
    from friday.commands.duplicates import restored  # noqa: PLC0415

    ids = [add(app, "Reading"), add(app, "Reading")]
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'not_duplicates', '[2490]')")  # as it was saved
    assert len(app.do("duplicates")["groups"]) == 1
    app.do("not_duplicates", ids=ids)
    assert app.do("duplicates")["groups"] == []
    assert restored(app.conn, 1) == {2490}
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'suggestions_restored', '[7]')")
    assert restored(app.conn, 1) == {2490, 7}


def test_going_over_what_friday_brought_in_again(app: App) -> None:
    home = calendar("home", "Home")
    due = [mac_event(f"d{n}", "home", f"PS {n} due", f"2026-10-2{n}T23:59", f"2026-10-2{n}T23:59") for n in (2, 3)]
    app.do("mac_sync", calendars=[home], events=due, since=SINCE, until=UNTIL)
    sync(app.conn, app.now_utc)
    for s in app.do("inbox")["suggestions"]:
        app.do("suggestion_accept", id=s["id"])
    mine = add(app, "Typed by hand")
    assert app.do("to_review") == {"items": [], "sources": {}, "started": False}
    assert app.do("review_again")["message"] == "2 tasks to go over"
    listed = app.do("to_review")
    ids = [i["id"] for i in listed["items"]]
    assert mine not in ids and set(listed["sources"].values()) == {"Home"} and listed["started"]
    app.do("reviewed", ids=ids[:1])
    app.do("reviewed", ids=ids[1:], keep=False)
    assert app.do("to_review")["items"] == [] and app.do("item", id=ids[1])["item"]["status"] == "dropped"
    assert app.do("item", id=ids[0])["item"]["status"] == "todo"


def test_the_same_deadline_on_two_calendars_makes_one_task(app: App) -> None:
    google, icloud = calendar("g", "Gmail"), calendar("i", "Calendar")
    twin = [mac_event(f"{cal}:EVT", cal, "Psych WA7 due", "2026-10-23T23:59", "2026-10-23T23:59") for cal in ("g", "i")]
    app.do("mac_sync", calendars=[google, icloud], events=twin, since=SINCE, until=UNTIL)
    sync(app.conn, app.now_utc)
    assert len([s for s in app.do("inbox")["suggestions"] if s["command"] == "add"]) == 1


def test_a_copy_cant_be_both_kept_and_removed(app: App) -> None:
    first, second = add(app, "Psych WA7 draft"), add(app, "psych WA7 Draft")
    with pytest.raises(FieldError, match="can't be both kept and removed"):
        app.do("duplicates_merge", groups=[{"keep": first, "drop": [first, second]}])


def test_a_removed_copys_ties_move_to_the_kept_one_once_and_its_pins_go(app: App) -> None:
    kept, copy = add(app, "Essay draft"), add(app, "essay  draft")
    outline, reading, final, review = add(app, "Outline"), add(app, "Reading"), add(app, "Final"), add(app, "Review")
    app.do("depend", item_id=copy, depends_on_id=outline)  # the copy waits on the outline: moved to the kept one
    app.do("depend", item_id=kept, depends_on_id=reading)
    app.do("depend", item_id=copy, depends_on_id=reading)  # the kept one waits on it already: dropped
    app.do("depend", item_id=final, depends_on_id=copy)  # the final waits on the copy: now on the kept one
    app.do("depend", item_id=review, depends_on_id=kept)
    app.do("depend", item_id=review, depends_on_id=copy)  # waits on the kept one already: dropped
    app.do("depend", item_id=copy, depends_on_id=kept)  # the copy waits on the kept one: nothing waits on itself
    app.do("pin", id=copy, start="2026-10-20T14:00")
    app.do("duplicates_merge", groups=[{"keep": kept, "drop": [copy]}])
    assert [p for p in app.table("pins") if p["item_id"] == copy] == []  # its pin goes with it
    ties = sorted((d["item_id"], d["depends_on_id"]) for d in app.table("dependencies"))
    assert ties == sorted([(kept, outline), (kept, reading), (final, kept), (review, kept)])
