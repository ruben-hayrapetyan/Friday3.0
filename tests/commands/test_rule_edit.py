"""Editing a rule where it stands (14 Nov: deleting one and adding it again lost its place and how often it was kept):
your words, Friday's reading of them and the strength, or a built-in rule's number. The same kind of rule keeps its
name, its place and its history; another kind takes its place as a new rule, said before you save; Undo puts the old
one back."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.service import replan
from friday.planner.snapshot import take_snapshot
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def names(app: App) -> list[str]:
    return [r["name"] for r in app.do("rules")]


def find(app: App, name: str) -> dict:
    return next(r for r in app.do("rules") if r["name"] == name)


def mine(app: App) -> list[dict]:
    return [r for r in app.do("rules") if r["source"] == "you"]


def added(app: App, text: str, **options: object) -> str:
    app.do("rule_add", text=text, **options)
    return mine(app)[-1]["name"]


def test_new_words_of_the_same_kind_keep_the_rule_in_its_place(app: App) -> None:
    first = added(app, "no work after 10pm")
    added(app, "lunch before 1pm")
    order = names(app)
    out = app.do("rule_edit", name=first, text="no work after 11pm on weekdays")
    assert out["message"] == "Saved: No work after 11pm on weekdays"
    assert names(app) == order  # same name, same place
    edited = find(app, first)
    assert (
        edited["sentence"] == "No work after 11pm on weekdays" and edited["words"] == "no work after 11pm on weekdays"
    )
    assert edited["reading"]["at"] == "23:00" and edited["reading"]["days"] == ["mon", "tue", "wed", "thu", "fri"]
    spec = next(r for r in take_snapshot(app.conn, app.now_utc).settings["rules"] if r.name == first)
    assert spec.params["start"] == "23:00" and spec.params["days"] == ["mon", "tue", "wed", "thu", "fri"]


def test_a_corrected_reading_and_a_strength_keep_the_words(app: App) -> None:
    name = added(app, "no gaming after 9pm")
    app.do("rule_edit", name=name, overrides={"days": ["sat", "sun"], "at": "22:00"}, strength="Always")
    rule = find(app, name)
    assert (rule["sentence"], rule["strength"], rule["words"]) == ("Gaming before 10pm on weekends", "Always",
                                                                  "no gaming after 9pm")  # fmt: skip
    assert (
        next(r for r in take_snapshot(app.conn, app.now_utc).settings["rules"] if r.name == name).params["price"]
        == "forbid"
    )


def test_a_switched_off_rule_stays_off_when_edited(app: App) -> None:
    name = added(app, "no work after 10pm")
    app.do("rule_set", name=name, enabled=False)
    app.do("rule_edit", name=name, text="no work after 11pm")
    assert find(app, name)["enabled"] is False


def test_another_kind_of_rule_takes_its_place_as_a_new_rule_and_says_so_first(app: App) -> None:
    first = added(app, "no work after 10pm")
    added(app, "lunch before 1pm")
    at = names(app).index(first)
    read = app.do("rule_read", text="gym in the morning", editing=first)
    assert read["starts_over"] is True and read["replaces"] == "No work after 10pm"
    assert app.do("rule_read", text="no work after 11pm", editing=first)["starts_over"] is False
    app.do("rule_win", winner=first, loser="chunk_cost")
    out = app.do("rule_edit", name=first, text="gym in the morning")
    assert out["message"].startswith("Replaced with a new rule: Gym between 8am and 12pm")
    assert "starts over" in out["message"]
    now = names(app)
    assert first not in now and now[at] == "you:gym-between-8am-and-12pm"  # the old one's place
    assert find(app, now[at])["wins_over"] == []  # its history starts over: what the old one won goes with it
    assert json.loads(next(r["value"] for r in app.table("kv") if r["key"] == "rule_wins")) == []


def test_an_edit_isnt_compared_with_the_rule_it_replaces(app: App) -> None:
    name = added(app, "at most 6 hours a day")
    others = [c["other"] for c in app.do("rule_read", text="at most 5 hours a day", editing=name)["conflicts"]]
    assert name not in others and "daily_load" in others
    assert name in [c["other"] for c in app.do("rule_read", text="at most 5 hours a day")["conflicts"]]  # a new one


def test_kept_history_carries_on_under_the_same_name(app: App) -> None:
    for n in range(8):
        app.do("add", text=f"problem set {n} ~5h due wed 23:59")
    name = added(app, "no work after 6pm")
    replan(app.conn, app.now_utc)
    before = find(app, name)["kept"]
    assert before.startswith("kept ")
    app.do("rule_edit", name=name, text="no work after 7pm")
    assert find(app, name)["kept"] == before  # counted on under its name until the next plan counts again
    replan(app.conn, app.now_utc)
    assert find(app, name)["kept"].startswith("kept ")


def test_undo_puts_the_old_rule_back(app: App) -> None:
    first = added(app, "no work after 10pm")
    rules_before, said_before = names(app), find(app, first)
    edit = app.full("rule_edit", payload={"name": first, "text": "gym in the morning"}, provisional=False)
    app.do("undo", command_id=edit.command_id)
    assert names(app) == rules_before
    assert find(app, first) == said_before


def test_a_built_in_rules_number_and_strength_change_but_not_its_words(app: App) -> None:
    deep = find(app, "deep_run")
    assert deep["number"]["value"] == 3 and deep["number"]["unit"] == "h"
    assert deep["number"]["said"] == "No more than {n} h of focused work in a row"
    order = names(app)
    app.do("rule_edit", name="deep_run", number=2, strength="Strongly")
    deep = find(app, "deep_run")
    assert (deep["sentence"], deep["strength"]) == ("No more than 2 h of focused work in a row", "Strongly")
    assert names(app) == order
    rule = next(r for r in take_snapshot(app.conn, app.now_utc).settings["rules"] if r.name == "deep_run")
    assert rule.params["threshold"] == "2h"
    with pytest.raises(FieldError, match="words stay"):
        app.do("rule_edit", name="deep_run", text="no work after 9pm")
    with pytest.raises(FieldError, match="between"):
        app.do("rule_edit", name="daily_load", number=40)


def test_finishing_early_is_said_with_its_days(app: App) -> None:
    early = find(app, "finish_early")
    assert early["sentence"] == "Finish work a day before it’s due"
    assert (early["number"]["one"], early["number"]["said"]) == ("Finish work a day before it’s due",
                                                                "Finish work {n} days before it’s due")  # fmt: skip
    app.do("rule_edit", name="finish_early", number=2)
    assert find(app, "finish_early")["sentence"] == "Finish work 2 days before it’s due"


def test_a_built_in_number_changes_the_plan(app: App) -> None:
    essay = app.do("add", text="history essay ~6h due fri 17:00")["item"]["id"]
    app.do("rule_set", name="deep_run", strength="Strongly")
    app.do("rule_edit", name="deep_run", number=1)
    replan(app.conn, app.now_utc)
    blocks = app.do("item", id=essay)["blocks"]
    lengths = [(datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"])).seconds / 60 for b in blocks]
    assert lengths and max(lengths) <= 75  # an hour at a time, give or take a quarter


def test_what_cant_be_edited(app: App) -> None:
    with pytest.raises(FieldError, match="no rule"):
        app.do("rule_edit", name="nonsense", number=2)
    with pytest.raises(FieldError, match="deadlines"):
        app.do("rule_edit", name="late_work", strength="Prefer")
    name = added(app, "no work after 10pm")
    with pytest.raises(FieldError, match="can’t read"):
        app.do("rule_edit", name=name, text="make me a sandwich")
    with pytest.raises(FieldError, match="more than one rule"):
        app.do("rule_edit", name=name, text="no work between 7:10 am and 7:20 am and between 7:30 am and 7:40 am")
    with pytest.raises(FieldError, match="no number"):
        app.do("rule_edit", name="same_course", number=2)
    assert find(app, name)["sentence"] == "No work after 10pm"


def test_rules_set_in_the_config_file_are_edited_there(app: App) -> None:
    app.conn.execute("INSERT INTO kv (user_id, key, value) VALUES (1, 'config_keys', '[\"rules\"]')")
    with pytest.raises(FieldError, match="friday.toml"):
        app.do("rule_edit", name="deep_run", number=2)
