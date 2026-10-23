"""Stuck (DESIGN §18, COMBINED.md 66): saying you're stuck goes in the item's history and changes nothing else; the
Now bar then offers what else fits."""

import json
from pathlib import Path

import pytest

from friday.commands.progress import FRICTION_KEPT
from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


def test_only_the_latest_are_kept(app: App) -> None:
    essay = app.do("add", text="essay ~3h due fri")["item"]["id"]
    for n in range(FRICTION_KEPT + 3):
        app.do("stuck", id=essay, note=str(n))
    kept = friction(app)
    assert len(kept) == FRICTION_KEPT and kept[0]["note"] == "3" and kept[-1]["note"] == str(FRICTION_KEPT + 2)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def friction(app: App) -> list[dict]:
    found = [r for r in app.table("kv") if r["key"] == "friction"]
    return json.loads(found[0]["value"]) if found else []


def test_stuck_goes_in_the_items_history_and_changes_nothing_else(app: App) -> None:
    essay = app.do("add", text="essay ~3h due fri")["item"]["id"]
    before = (app.table("items"), app.table("progress"), app.table("timer"), app.table("plans"))
    out = app.do("stuck", id=essay, note="can't find the reading")
    assert out["message"] == "Noted that you're stuck on essay"
    assert (app.table("items"), app.table("progress"), app.table("timer"), app.table("plans")) == before
    assert friction(app) == [{"item_id": essay, "at": "2026-10-19T13:00Z", "note": "can't find the reading"}]
    history = app.do("log_list", item_id=essay, limit=5)
    assert history[0]["command"] == "stuck" and history[0]["input"]["note"] == "can't find the reading"


def test_stuck_while_timing_keeps_the_timer(app: App) -> None:
    essay = app.do("add", text="essay ~3h due fri")["item"]["id"]
    app.do("start", id=essay)
    app.do("stuck", id=essay)
    assert app.table("timer")[0]["item_id"] == essay


def test_stuck_can_be_undone_and_isnt_for_events(app: App) -> None:
    essay = app.do("add", text="essay ~3h due fri")["item"]["id"]
    said = app.full("stuck", payload={"id": essay}, provisional=False)
    app.do("undo", command_id=said.command_id)
    assert friction(app) == []
    lecture = app.do("add", title="CS 2110 Lec", when="fixed", start="2026-10-20T10:10", end="2026-10-20T11:00")
    with pytest.raises(FieldError, match="event"):
        app.do("stuck", id=lecture["item"]["id"])
    with pytest.raises(FieldError):
        app.do("stuck", id=9999)
