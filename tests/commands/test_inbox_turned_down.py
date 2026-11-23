"""What you turned down isn't asked again (23 Nov: "keep a list of recently rejected/accepted events so that you don't
ask duplicates for rejected events too (similar to how friday does this for accepted events)"). Accepting makes an
item, and what you have isn't asked again (test_inbox_duplicates.py); turning one down made nothing, so the same thing
read again, from another source or the same, came back. Now a suggestion is the same as one you turned down in the
last 120 days as it's the same as an item you have (commands/duplicates.py): same name, same kind, dates that agree."""

from datetime import timedelta
from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app
from tests.commands.test_inbox_duplicates import event, propose, task, waiting

# Monday 19 Oct 2026, 9am (the helpers' now).


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def turn_down(app: App, title: str) -> None:
    app.do("suggestion_reject", id=waiting(app)[title]["id"])


def test_an_event_you_turned_down_read_again_from_another_source_isnt_asked(app: App) -> None:
    propose(app, event("Career fair", "2026-10-22T10:00", "2026-10-22T14:00"), source="Mail")
    turn_down(app, "Career fair")
    propose(app, event("Career Fair", "2026-10-22T10:00", "2026-10-22T14:00"), source="Calendar")
    assert waiting(app) == {}


def test_a_task_you_turned_down_read_again_isnt_asked(app: App) -> None:
    propose(app, task("Optional reading 3", "2026-10-23T17:00"))
    turn_down(app, "Optional reading 3")
    propose(app, task("Optional reading 3", "2026-10-23T23:59"), source="Canvas")
    assert waiting(app) == {}


def test_turning_one_down_takes_its_copy_waiting_from_another_source_too(app: App) -> None:
    propose(app, event("Career fair", "2026-10-22T10:00", "2026-10-22T14:00"), source="Mail")
    propose(app, event("Career fair", "2026-10-22T10:15", "2026-10-22T14:00"), source="Calendar")
    copies = [s for s in app.do("inbox")["suggestions"] if s["input"]["title"] == "Career fair"]
    turn_down(app, "Career fair")
    left = [s for s in app.do("inbox")["suggestions"] if s["input"]["title"] == "Career fair"]
    assert len(copies) >= 1 and left == []


def test_the_same_name_at_another_time_is_another_one_and_is_asked(app: App) -> None:
    propose(app, event("Office hours", "2026-10-20T15:00", "2026-10-20T16:00"))
    turn_down(app, "Office hours")
    propose(app, event("Office hours", "2026-10-27T15:00", "2026-10-27T16:00"), source="Calendar")
    assert "Office hours" in waiting(app)  # next week's: not the one you turned down


def test_turned_down_long_ago_is_asked_again(app: App) -> None:
    propose(app, task("Club newsletter", None))
    turn_down(app, "Club newsletter")
    app.now_utc += int(timedelta(days=121).total_seconds() // 60)
    propose(app, task("Club newsletter", None), source="Mail again")
    assert "Club newsletter" in waiting(app)  # remembered 120 days, as what you finished is
