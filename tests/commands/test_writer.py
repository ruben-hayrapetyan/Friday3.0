"""Writes recorded for undo (commands/writer.py): a row already gone, a row that isn't there to change, and an undo
refused after something no command made changed the row."""

from pathlib import Path

import pytest

from friday.commands.writer import Writer
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_deleting_a_row_already_gone_records_nothing(app: App) -> None:
    db = Writer(app.conn, 1)
    db.delete("items", {"id": 99})
    assert db.changes == []


def test_changing_a_row_that_isnt_there_is_an_error(app: App) -> None:
    with pytest.raises(ValueError, match="items {'id': 99} doesn't exist"):
        Writer(app.conn, 1).update("items", {"id": 99}, {"title": "x"})


def test_an_undo_after_a_change_no_command_made_says_only_that_it_changed(app: App) -> None:
    added = app.full("add", payload={"title": "Essay", "duration_min": 60}, provisional=False)
    app.conn.execute("UPDATE items SET title = 'Essay (from the calendar)'")
    with pytest.raises(FieldError, match=r"changed since$"):
        app.do("undo", command_id=added.command_id)
