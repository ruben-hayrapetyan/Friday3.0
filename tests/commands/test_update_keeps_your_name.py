"""Updating what you have from the Inbox keeps your name for it (9 Nov: "when I did 'update event' for one of the
events in my inbox, the event got deleted. it was chem pset 11"). It wasn't deleted: an email's "PS11", matched to
"Chem 2090 Problem Set 11", renamed it to "PS11" as it moved its due date, so it couldn't be found by its name."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.commands.inbox import source_named_it
from friday.commands.registry import Ctx
from friday.commands.writer import Writer
from friday.planner.store import load_settings
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app
from tests.commands.test_inbox_duplicates import propose, task, waiting


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 Oct 2026, 9am


def pset(app: App) -> int:
    return app.do("add", title="Chem 2090 Problem Set 11", due="2026-10-21T23:59", preset="Assignment")["item"]["id"]


# Black box: through the Inbox, as mail and calendars reach it.


def test_an_emails_update_moves_the_date_and_keeps_your_name(app: App) -> None:
    mine = pset(app)
    propose(app, task("Chem 2090 PS11", "2026-10-26T23:59"))
    (found,) = waiting(app).values()
    assert found["duplicate_of"] == mine
    app.do("suggestion_accept", id=found["id"])
    item = app.do("item", id=mine)["item"]
    assert (item["title"], item["due"], item["status"]) == ("Chem 2090 Problem Set 11", "2026-10-26T23:59", "todo")


def test_a_name_you_type_while_accepting_is_used(app: App) -> None:
    mine = pset(app)
    propose(app, task("Chem 2090 PS11", "2026-10-26T23:59"))
    (found,) = waiting(app).values()
    app.do("suggestion_accept", id=found["id"], edits={"title": "Chem PS11 (moved)"})
    assert app.do("item", id=mine)["item"]["title"] == "Chem PS11 (moved)"  # you chose it


def test_a_calendar_renaming_its_own_event_renames_it_here(app: App) -> None:
    e = event("e1", "Office hours", "2026-10-22T15:00", "2026-10-22T16:00")
    google = FakeGoogle({"Work@group": [e]})
    app.do("settings_set", key="gcal", value={"read": ["Work"], "trusted": ["Work"]})
    sync(app.conn, app.now_utc, google=google)
    e["summary"] = "Office hours (room 120)"
    sync(app.conn, app.at("2026-10-19T12:00").now_utc, google=google)
    assert [i["title"] for i in app.table("items") if i["status"] == "todo"] == ["Office hours (room 120)"]


def test_an_event_you_renamed_keeps_your_name_when_the_calendar_moves_it(app: App) -> None:
    e = event("e1", "Office hours", "2026-10-22T15:00", "2026-10-22T16:00")
    google = FakeGoogle({"Work@group": [e]})
    app.do("settings_set", key="gcal", value={"read": ["Work"], "trusted": ["Work"]})
    sync(app.conn, app.now_utc, google=google)
    item = next(i["id"] for i in app.table("items") if i["title"] == "Office hours")
    app.do("edit", id=item, title="CS office hours")
    e["start"], e["end"] = {"dateTime": "2026-10-22T16:00:00-04:00"}, {"dateTime": "2026-10-22T17:00:00-04:00"}
    sync(app.conn, app.at("2026-10-19T12:00").now_utc, google=google)
    shown = app.do("item", id=item)["item"]
    assert (shown["title"], shown["start"]) == ("CS office hours", "2026-10-22T16:00")


# Glass box: source_named_it.


def ctx(app: App) -> Ctx:
    return Ctx(app.conn, Writer(app.conn, 1), app.now_utc, "you", 1, load_settings(app.conn, 1))


def suggestion(**row: object) -> dict:
    return {"id": 0, "raw_input_id": 0, "duplicate_of": None, "command": "edit", "input": "{}"} | row


def test_a_match_to_yours_never_names_it(app: App) -> None:
    assert not source_named_it(ctx(app), suggestion(duplicate_of=1, command="add"), "Chem 2090 Problem Set 11")


def test_no_earlier_reading_means_no_rename(app: App) -> None:
    assert not source_named_it(ctx(app), suggestion(raw_input_id=999), "Office hours")


def test_the_name_the_last_reading_gave_may_change(app: App) -> None:
    e = event("e1", "Office hours", "2026-10-22T15:00", "2026-10-22T16:00")
    app.do("settings_set", key="gcal", value={"read": ["Work"], "trusted": ["Work"]})
    sync(app.conn, app.now_utc, google=FakeGoogle({"Work@group": [e]}))
    (raw,) = app.table("raw_inputs")
    assert source_named_it(ctx(app), suggestion(raw_input_id=raw["id"]), "Office hours")
    assert not source_named_it(ctx(app), suggestion(raw_input_id=raw["id"]), "CS office hours")


# The whole system: the server, as the Inbox's Update it button calls it.


def test_through_the_server(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from friday.server.app import create_app

    app = new_app(tmp_path)
    mine = pset(app)
    propose(app, task("Chem 2090 PS11", "2026-10-26T23:59"))
    (found,) = waiting(app).values()
    served = create_app(tmp_path / "friday.db", clock=lambda: app.now_utc, background=False, plugin_dir=tmp_path)
    with TestClient(served, base_url="http://127.0.0.1:8765") as web:
        assert web.post("/api/c/suggestion_accept", json={"id": found["id"]}).status_code == 200
        item = web.get("/api/q/item", params={"id": mine}).json()["item"]
        assert (item["title"], item["due"]) == ("Chem 2090 Problem Set 11", "2026-10-26T23:59")
