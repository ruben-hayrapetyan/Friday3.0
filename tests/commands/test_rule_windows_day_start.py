"""A rule's hours run to your day's start, not 4am (audit, 12 Nov: "No work after 10pm" kept work out from 10pm to
4am whatever time your day starts, so with a 6am start 4am to 6am was open). Glass box: the rule a reading becomes
ends (before) or begins (after) at the day start it's given; a new day start moves the rules that ran to the old one
and nothing else; the migration does it for rules made before. Black box through the commands: the rule the Rules
page shows runs to your day's start, before and after you change it, at every strength. Through the HTTP API, a plan:
tests/server/test_rule_windows_flow.py."""

import json
from pathlib import Path

import pytest

from friday.core.db import MIGRATIONS
from friday.core.rule_text import Reading, spec
from tests.commands.helpers import TZ, App, new_app

LATE = Reading("window", "work", rel="before", at="22:00")  # no work after 10pm: done before it
EARLY = Reading("window", "work", rel="after", at="09:00")  # no work before 9am: done after it


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def day_start(app: App, at: str) -> None:
    app.do("settings_set", key="time", value={"timezone": TZ, "horizon_days": 7, "day_start": at})


def hours(app: App, said: str) -> tuple[str, str]:
    (rule,) = [r for r in app.do("settings")["rules"] if r["reason"] == said]
    return rule["params"]["start"], rule["params"]["end"]


# Glass box


def test_before_a_time_is_from_it_to_the_day_start_given() -> None:
    assert spec(LATE, "Always", "you:late", [], [], day_start="06:00")["params"] == {
        "start": "22:00",
        "end": "06:00",
        "price": "forbid",
    }


def test_after_a_time_is_from_the_day_start_given_to_it() -> None:
    params = spec(EARLY, "Prefer", "you:early", [], [], day_start="05:30")["params"]
    assert (params["start"], params["end"]) == ("05:30", "09:00")


def test_without_a_day_start_it_is_the_settings_default() -> None:
    assert spec(LATE, "Prefer", "you:late", [], [])["params"]["end"] == "04:00"


def test_between_hours_keep_their_own_times() -> None:
    between = Reading("window", "work", rel="between", at="09:00", until="17:00")
    params = spec(between, "Prefer", "you:day", [], [], day_start="06:00")["params"]
    assert (params["start"], params["end"]) == ("17:00", "09:00")


def test_a_new_day_start_moves_only_the_hours_that_ran_to_the_old_one(app: App) -> None:
    app.do("rule_add", text="No work after 10pm")
    app.do("rule_add", text="No work before 9am")
    app.do("rule_add", text="No work between 11pm and 4am")  # its own 4am: stays
    edited = app.do("settings")["rules"]
    for r in edited:
        if r["reason"] == "No work before 9am":
            r["params"]["start"] = "05:00"  # set by hand on the Rules page: yours, stays
    app.do("settings_set", key="rules", value=edited)
    day_start(app, "06:00")
    assert hours(app, "No work after 10pm") == ("22:00", "06:00")
    assert hours(app, "No work before 9am") == ("05:00", "09:00")
    assert hours(app, "No work between 11pm and 4am") == ("23:00", "04:00")


def test_the_migration_moves_rules_made_before_to_the_day_start_you_have(app: App) -> None:
    app.do("rule_add", text="No work after 10pm")
    app.do("rule_add", text="No work before 9am")
    app.conn.execute("UPDATE settings SET value = json_set(value, '$.day_start', '06:00') WHERE key = 'time'")
    app.conn.executescript((MIGRATIONS / "033_rule_hours_day_start.sql").read_text())
    rules = json.loads(app.conn.execute("SELECT value FROM settings WHERE key = 'rules'").fetchone()[0])
    mine = {r["reason"]: (r["params"]["start"], r["params"]["end"]) for r in rules if r["name"].startswith("you:")}
    assert mine == {"No work after 10pm": ("22:00", "06:00"), "No work before 9am": ("06:00", "09:00")}
    assert len(rules) == len(app.do("settings")["rules"])  # the built-in rules are all still there


def test_the_migration_leaves_a_4am_day_start_alone(app: App) -> None:
    app.do("rule_add", text="No work after 10pm")
    before = app.conn.execute("SELECT value, version FROM settings WHERE key = 'rules'").fetchone()
    app.conn.executescript((MIGRATIONS / "033_rule_hours_day_start.sql").read_text())
    assert app.conn.execute("SELECT value, version FROM settings WHERE key = 'rules'").fetchone() == before


# Black box


@pytest.mark.parametrize("strength", ["Prefer", "Strongly", "Always"])
def test_no_work_after_10pm_runs_to_your_day_start(app: App, strength: str) -> None:
    day_start(app, "06:00")
    app.do("rule_add", text="No work after 10pm", strength=strength)
    assert hours(app, "No work after 10pm") == ("22:00", "06:00")


def test_a_changed_strength_keeps_your_day_start(app: App) -> None:
    day_start(app, "06:00")
    app.do("rule_add", text="No work before 9am")
    (rule,) = [r for r in app.do("settings")["rules"] if r["reason"] == "No work before 9am"]
    app.do("rule_set", name=rule["name"], strength="Always")
    assert hours(app, "No work before 9am") == ("06:00", "09:00")


def test_a_rule_made_before_follows_a_new_day_start(app: App) -> None:
    app.do("rule_add", text="No work after 10pm")
    assert hours(app, "No work after 10pm") == ("22:00", "04:00")
    day_start(app, "05:00")
    assert hours(app, "No work after 10pm") == ("22:00", "05:00")
    day_start(app, "04:00")
    assert hours(app, "No work after 10pm") == ("22:00", "04:00")


def test_the_rule_read_before_adding_shows_your_day_start(app: App) -> None:
    day_start(app, "06:00")
    said = app.do("rule_read", text="No work after 10pm")
    assert said["sentence"] == "No work after 10pm"
    app.do("rule_add", text="No work after 10pm", strength="Always")
    assert hours(app, "No work after 10pm") == ("22:00", "06:00")
