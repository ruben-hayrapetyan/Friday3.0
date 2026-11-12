"""An event's three choices (12 Nov: "the work through it button should not be the same as the skip button"): going,
working through it (there, but its time is work's, drawn as it is) and skipping it (not going, crossed out)."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def lecture(app: App) -> int:
    return app.do("add", title="Lecture", when="fixed", start="2026-10-20T10:00", end="2026-10-20T11:00")["item"]["id"]


def facts(app: App, item_id: int) -> dict:
    return app.do("item", id=item_id)["item"]


def test_working_through_frees_its_time_but_isnt_skipping(app: App) -> None:
    event = lecture(app)
    app.do("event_choice", id=event, choice="through")
    assert facts(app, event)["left_out"] == "through"
    assert app.conn.execute("SELECT blocks_time FROM items WHERE id = ?", [event]).fetchone()[0] == 0
    app.do("event_choice", id=event, choice="skip")
    assert facts(app, event)["left_out"] == "skipped"
    app.do("event_choice", id=event, choice="going")
    assert facts(app, event)["left_out"] is None
    assert app.conn.execute("SELECT blocks_time FROM items WHERE id = ?", [event]).fetchone()[0] == 1


def test_going_or_skipping_lets_go_of_the_to_do_its_time_was_for(app: App) -> None:
    event = lecture(app)
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    app.do("event_choice", id=event, choice="through")
    app.do("event_hold", id=event, task_id=essay)
    assert facts(app, event)["holds"]["id"] == essay
    app.do("event_choice", id=event, choice="skip")
    assert facts(app, event)["holds"] is None


def test_a_choice_is_undone_whole(app: App) -> None:
    event = lecture(app)
    made = app.full("event_choice", payload={"id": event, "choice": "through"})
    app.do("undo", command_id=made.command_id)
    assert facts(app, event)["left_out"] is None


def test_only_an_event_has_these_choices(app: App) -> None:
    essay = app.do("add", title="Essay", duration_min=60)["item"]["id"]
    with pytest.raises(FieldError, match="isn't an event"):
        app.do("event_choice", id=essay, choice="skip")
