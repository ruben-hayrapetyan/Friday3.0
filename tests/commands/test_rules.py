"""Rules in your words: read a sentence, add it, change its strength, switch it off, delete it; the plan follows."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def find(app: App, name: str) -> dict:
    return next(r for r in app.do("rules") if r["name"] == name)


def test_a_sentence_reads_as_a_rule_and_your_overrides_win(app: App) -> None:
    out = app.do("rule_read", text="I prefer eating lunch before 1pm")
    assert (out["sentence"], out["strength"]) == ("Lunch before 1pm", "Prefer")
    moved = app.do("rule_read", text="I prefer eating lunch before 1pm", overrides='{"at": "12:30", "days": ["sat"]}')
    assert moved["sentence"] == "Lunch before 12:30pm on Sat"
    assert app.do("rule_read", text="make me a sandwich")["reading"] is None


def test_an_always_rule_keeps_work_out_of_those_hours(app: App) -> None:
    app.do("rule_add", text="no work after 6pm", strength="Always")
    essay = app.do("add", text="essay due wed 23:00 ~4h")["item"]["id"]
    replan(app.conn, app.now_utc)
    blocks = app.do("item", id=essay)["blocks"]
    assert blocks and all(b["end"][11:] <= "18:00" for b in blocks)
    (mine,) = [r for r in app.do("rules") if r["source"] == "you"]
    assert (mine["sentence"], mine["strength"]) == ("No work after 6pm", "Always")


def test_strength_switch_and_delete(app: App) -> None:
    app.do("rule_add", text="keep saturday mornings free")
    name = next(r["name"] for r in app.do("rules") if r["source"] == "you")
    app.do("rule_set", name=name, strength="Strongly")
    assert find(app, name)["strength"] == "Strongly"
    app.do("rule_set", name="daily_load", enabled=False)
    assert find(app, "daily_load")["enabled"] is False
    with pytest.raises(FieldError):
        app.do("rule_set", name="late_work", strength="Prefer")  # deadlines don't bend... nor soften
    app.do("rule_remove", name=name)
    assert all(r["name"] != name for r in app.do("rules"))


def test_the_deadline_rules_cant_be_deleted(app: App) -> None:
    with pytest.raises(FieldError, match="deadlines"):
        app.do("rule_remove", name="late_work")
