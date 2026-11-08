"""Whether work may take an event's time, set from the event's editor (8 Nov: everything about one event in its
editor; a rule naming it shown and changed there). Glass box: the mode read from the rules, broader rules found by a
word. Black box through the commands: optional, then only when ahead, then kept, one rule at a time; a broader rule
left for the Rules page and said; and the plan using an optional event's time when work needs it."""

from pathlib import Path

import pytest

from friday.commands.optional_events import mode_of
from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app

GYM = "Gym with Sam"


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-11-02T09:00", horizon_days=3)
    app.do("add", text=GYM, when="fixed", start="2026-11-02T13:00", end="2026-11-02T18:00")
    return app


def skippable(app: App) -> list[dict]:
    return [r for r in app.do("settings")["rules"] if r["type"] == "skippable"]


class TestGlassBox:
    def test_the_mode_is_read_from_the_rule_naming_the_event(self) -> None:
        rules = [
            {"type": "skippable", "params": {"titles": ["gym with sam"], "ahead": True}, "reason": "Only if ahead"}
        ]
        assert mode_of(rules, GYM) == ("ahead", "Only if ahead")
        assert mode_of([], GYM) == ("kept", None)
        off = [{**rules[0], "enabled": False}]
        assert mode_of(off, GYM) == ("kept", None)


class TestBlackBox:
    def test_optional_then_ahead_then_kept_one_rule_at_a_time(self, app: App) -> None:
        said = app.do("event_optional", title=GYM, mode="optional")["message"]
        assert said.startswith("Gym with Sam is optional")  # your capitals, not "Gym With Sam"
        assert app.do("event_mode", title=GYM)["mode"] == "optional"
        assert [r["params"]["titles"] for r in skippable(app)] == [[GYM]]
        app.do("event_optional", title=GYM, mode="ahead")
        mode = app.do("event_mode", title=GYM)
        assert mode["mode"] == "ahead" and "ahead" in (mode["rule"] or "").lower()
        assert [r["params"].get("ahead") for r in skippable(app)] == [True]  # taken out of the optional one
        said = app.do("event_optional", title=GYM, mode="kept")["message"]
        assert said == f"{GYM}: work keeps off it" and skippable(app) == []
        assert app.do("event_mode", title=GYM) == {"mode": "kept", "rule": None, "covered_by": []}

    def test_a_broader_rule_stays_and_is_said(self, app: App) -> None:
        app.do("rule_add", text="gym is optional")
        assert app.do("event_mode", title=GYM)["covered_by"]  # reached by the word "gym"
        said = app.do("event_optional", title=GYM, mode="kept")["message"]
        assert "still covers it: change that one in Rules" in said
        assert any("gym" in t.lower() for r in skippable(app) for t in r["params"]["titles"])

    def test_a_title_is_needed(self, app: App) -> None:
        with pytest.raises(FieldError, match="Which event"):
            app.do("event_optional", title="  ", mode="optional")


def test_work_takes_an_optional_events_time_only_once_it_must(app: App) -> None:
    """The whole system: an essay due at 6pm with only the gym's afternoon free goes into the gym's time once the gym
    is optional, and not before."""
    app.do("add", text="Busy morning", when="fixed", start="2026-11-02T09:00", end="2026-11-02T13:00")
    essay = app.do("add", title="Essay", duration_min=180, due="2026-11-02T18:00")["item"]["id"]
    replan(app.conn, app.now_utc)
    assert not [b for b in app.table("blocks") if b["item_id"] == essay and b["start_utc"] < "2026-11-02T23:00Z"]
    app.do("event_optional", title=GYM, mode="optional")
    replan(app.conn, app.now_utc)
    assert [b for b in app.table("blocks") if b["item_id"] == essay]
