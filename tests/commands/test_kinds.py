"""Kinds you add and delete (M12b): deleting moves its items, series, priority place, buffer and calendars."""

import json
from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_a_new_kind_starts_as_a_copy_and_names_are_unique(app: App) -> None:
    app.do("kind_add", name="Lab report", like="Assignment")
    assert app.do("settings")["presets"]["Lab report"] == app.do("settings")["presets"]["Assignment"]
    with pytest.raises(FieldError, match="already"):
        app.do("kind_add", name="lab REPORT", like="Errand")


def test_deleting_a_kind_moves_what_used_it(app: App) -> None:
    errand = app.do("add", title="post office", preset="Errand", due="2026-10-23T17:00")["item"]["id"]
    app.do("add", title="groceries", preset="Errand", every="sat")
    app.do("settings_set", key="kind_order", value=["Errand", "Assignment"])
    app.conn.execute(
        "INSERT INTO sources (user_id, kind, name, config) VALUES (1, 'gcal', 'Errands', ?)",
        [json.dumps({"kind": "Errand"})],
    )
    app.do("kind_remove", name="Errand", move_to="Chore")
    assert "Errand" not in app.do("settings")["presets"]
    assert app.do("settings")["kind_order"] == ["Assignment"]
    assert {i["preset"] for i in app.table("items") if i["id"] == errand or i["series_id"]} == {"Chore"}
    assert json.loads(app.table("series")[0]["template"])["preset"] == "Chore"
    assert json.loads(app.table("sources")[0]["config"])["kind"] is None


def test_kinds_reading_depends_on_and_kinds_a_rule_names_stay(app: App) -> None:
    with pytest.raises(FieldError, match="read into"):
        app.do("kind_remove", name="Class", move_to="Event")
    app.do("rule_add", text="no errands after 8pm")
    with pytest.raises(FieldError, match="rule"):
        app.do("kind_remove", name="Errand", move_to="Chore")


def test_suggestions_waiting_in_the_inbox_move_with_a_deleted_kind(app: App) -> None:
    app.do("document_add", name="note", content="x")
    app.conn.execute(
        "INSERT INTO suggestions (user_id, raw_input_id, command, input, quotes, created_utc) VALUES "
        "(1, 1, 'add', '{\"title\": \"RA application\", \"preset\": \"Errand\"}', '{}', '2026-10-19T13:00Z')"
    )
    app.do("kind_remove", name="Errand", move_to="Chore")
    assert json.loads(app.table("suggestions")[-1]["input"])["preset"] == "Chore"


def test_a_new_kind_needs_a_name_and_a_kind_to_copy(app: App) -> None:
    with pytest.raises(FieldError, match="give it a name"):
        app.do("kind_add", name="  ", like="Assignment")
    with pytest.raises(FieldError, match="no kind called Homework"):
        app.do("kind_add", name="Lab report", like="Homework")


def test_deleting_needs_a_kind_that_exists_and_another_to_move_to(app: App) -> None:
    with pytest.raises(FieldError, match="no kind called Homework"):
        app.do("kind_remove", name="Homework", move_to="Chore")
    with pytest.raises(FieldError, match="pick another kind"):
        app.do("kind_remove", name="Errand", move_to="Errand")


def test_deleting_a_kind_drops_its_buffer(app: App) -> None:
    rules = app.do("settings")["rules"]
    for r in rules:
        if r["type"] == "buffer":
            r["params"]["by_preset"] = {"Errand": "1d", "Chore": "2h"}
    app.do("settings_set", key="rules", value=rules)
    app.do("kind_remove", name="Errand", move_to="Chore")
    (buffer,) = [r for r in app.do("settings")["rules"] if r["type"] == "buffer"]
    assert buffer["params"]["by_preset"] == {"Chore": "2h"}
