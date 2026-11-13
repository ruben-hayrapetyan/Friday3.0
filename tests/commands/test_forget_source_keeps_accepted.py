"""A source removed with "forget" keeps the suggestions you accepted (audit, 12 Nov: it deleted them with
the rest, though they're yours now). Glass box: an accepted suggestion is let go of the source's raw input before
that goes (the input's delete would take it along), and undo puts both back. Black box through the commands: what
waited, and what you rejected, goes; what you accepted, and the to-do it made, stay. Through the HTTP API:
tests/server/test_forget_source_flow.py."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app
from tests.commands.test_inbox import feed, pending


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def accepted_one(app: App) -> tuple[int, int]:
    """Canvas read, PS4 accepted and the essay rejected: the source and the accepted suggestion."""
    feed(app)
    found = pending(app)
    app.do("suggestion_accept", id=found["PS4"]["id"])
    app.do("suggestion_reject", id=found["Essay draft"]["id"])
    return app.do("inbox")["sources"][0]["id"], found["PS4"]["id"]


# Glass box


def test_the_accepted_suggestion_is_let_go_of_its_input_and_the_rest_go(app: App) -> None:
    source, kept = accepted_one(app)
    app.do("source_remove", id=source, forget=True)
    assert [(s["id"], s["status"], s["raw_input_id"]) for s in app.table("suggestions")] == [(kept, "accepted", None)]
    assert app.table("raw_inputs") == [] and app.table("sources") == []


def test_undo_puts_the_source_its_inputs_and_every_suggestion_back(app: App) -> None:
    source, _ = accepted_one(app)
    before = (app.table("sources"), app.table("raw_inputs"), app.table("suggestions"))
    forgot = app.full("source_remove", payload={"id": source, "forget": True})
    app.do("undo", command_id=forgot.command_id)
    assert (app.table("sources"), app.table("raw_inputs"), app.table("suggestions")) == before


# Black box


def test_forgetting_keeps_what_you_accepted_and_its_to_do(app: App) -> None:
    source, kept = accepted_one(app)
    said = app.do("source_remove", id=source, forget=True)
    assert [s["id"] for s in app.table("suggestions") if s["status"] == "accepted"] == [kept]
    assert [i["title"] for i in app.do("items")] == ["PS4"]
    assert app.do("inbox")["suggestions"] == [] and app.do("inbox")["sources"] == []
    assert "accepted" in said["message"]


def test_forgetting_with_nothing_accepted_deletes_all_it_brought_in(app: App) -> None:
    feed(app)
    source = app.do("inbox")["sources"][0]["id"]
    said = app.do("source_remove", id=source, forget=True)
    assert app.table("suggestions") == [] and app.table("raw_inputs") == []
    assert said["message"] == "Removed Canvas and what it brought in"


def test_removing_without_forgetting_keeps_everything(app: App) -> None:
    source, _ = accepted_one(app)
    app.do("source_remove", id=source)
    assert len(app.table("suggestions")) == 3 and app.table("raw_inputs")
