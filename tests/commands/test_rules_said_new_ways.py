"""Rules said new ways (core/rule_more.py, 8 Nov), through the whole system: typed into the Rules box, added, and the
plan following them, with no AI connected."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_a_pace_said_in_clauses_sets_each_days_pace(app: App) -> None:
    said = "fridays: easy. saturdays: push. sundays: normal"
    assert app.do("rule_read", text=said)["reading"]["kind"] == "pace"
    app.do("rule_add", text=said)
    weekly = app.do("settings")["pace"]["weekly"]
    assert (weekly.get("fri"), weekly.get("sat"), weekly.get("sun", "Normal")) == ("Easy", "Push", "Normal")


def test_an_event_only_when_ahead_becomes_a_rule_about_that_event(app: App) -> None:
    app.do("rule_add", text="book club is an only-if-im-ahead thing")
    (mine,) = [r for r in app.do("rules") if r["source"] == "you"]
    assert "book club" in mine["sentence"].lower()


def test_free_time_said_with_its_hours_is_kept_free_not_the_only_hours_for_work(app: App) -> None:
    out = app.do("rule_read", text="i want 6 to 7pm free every weekday for family time")
    assert out["reading"]["kind"] == "free" and out["reading"]["at"] == "18:00"
