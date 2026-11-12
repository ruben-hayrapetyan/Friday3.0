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


def test_rules_set_in_the_config_file_are_changed_there(app: App) -> None:
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'config_keys', '[\"rules\"]')")
    with pytest.raises(FieldError, match="rules are set in friday.toml"):
        app.do("rule_add", text="no work after 6pm")


def test_a_rule_said_only_by_its_fields_is_added(app: App) -> None:
    out = app.do("rule_add", text="", overrides={"kind": "free", "subject": "work", "at": "18:00", "rel": "after"})
    assert out["message"].startswith("Added")


def test_overrides_that_arent_json_are_refused(app: App) -> None:
    with pytest.raises(FieldError, match="not JSON"):
        app.do("rule_read", text="no work after 6pm", overrides="{at: 6}")


def test_letting_friday_decide_a_meal_says_meal_tracking_is_off(app: App) -> None:
    out = app.do("rule_read", text="Let Friday decide breakfast")
    assert "Meal tracking is off" in out["effect"]


def test_a_sentence_friday_cant_read_isnt_added(app: App) -> None:
    with pytest.raises(FieldError, match="can’t read that as a rule"):
        app.do("rule_add", text="make me a sandwich")


def test_a_rule_that_isnt_there_is_said_by_its_name(app: App) -> None:
    with pytest.raises(FieldError, match="no rule named nope"):
        app.do("rule_set", name="nope", enabled=False)
    with pytest.raises(FieldError, match="no rule named nope"):
        app.do("rule_remove", name="nope")


def test_breathing_room_once_set_says_how_much(app: App) -> None:
    rules = [r.model_dump() for r in app_rules(app)]
    next(r for r in rules if r["name"] == "buffer")["params"]["minutes"] = "10m"
    app.do("settings_set", key="rules", value=rules)
    assert find(app, "buffer")["sentence"] == "Breathing room between blocks: 10m"


def test_a_built_in_rule_missing_a_number_still_reads_as_itself(app: App) -> None:
    rules = [r.model_dump() for r in app_rules(app)]
    next(r for r in rules if r["name"] == "deep_run")["params"].pop("threshold")
    app.do("settings_set", key="rules", value=rules)
    assert find(app, "deep_run")["sentence"] == "No more than {threshold} of focused work in a row"


def app_rules(app: App) -> list:
    from friday.planner.store import load_settings

    return load_settings(app.conn, 1)["rules"]


def test_a_weekly_pace_needs_a_pace_by_that_name(app: App) -> None:
    paces = {k: v for k, v in app.do("settings")["paces"].items() if k != "Easy"}
    app.do("settings_set", key="paces", value=paces)
    with pytest.raises(FieldError, match="no pace named Easy"):
        app.do("rule_add", text="take it easy on weekends")
