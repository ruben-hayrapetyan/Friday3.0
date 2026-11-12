"""Rules that contradict each other, from the rules themselves: before a rule is added (`rule_read`) and on the list
(`rules`), with your answer to "Which should win?" settling a pair."""

from pathlib import Path
from typing import Any

import pytest

from friday.core.rule_text import DAYS
from friday.planner.contradictions import Conflict, against, contradictions, no_time
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def said(app: App, text: str) -> list[tuple[str, str, bool]]:
    return [(c["other_sentence"], c["why"], c["overlap"]) for c in app.do("rule_read", text=text)["conflicts"]]


def mine(app: App) -> dict[str, dict[str, Any]]:
    return {r["sentence"]: r for r in app.do("rules") if r["source"] == "you"}


def test_two_rules_that_leave_some_work_no_time_at_all_contradict(app: App) -> None:
    app.do("rule_add", text="deep work in the morning", strength="Prefer")
    assert said(app, "no work before noon") == [
        ("Deep work between 8am and 12pm", "together they leave no time for deep work", False)
    ]


def test_days_that_together_cover_the_whole_week_contradict(app: App) -> None:
    app.do("rule_add", text="reading only on weekends", strength="Prefer")
    assert said(app, "no reading on weekends") == [
        ("Reading only on weekends", "together they leave no time for reading", False)
    ]
    assert said(app, "no reading on saturdays") == []  # Sundays are left


def test_a_contradiction_on_some_days_names_them(app: App) -> None:
    app.do("rule_add", text="keep saturday mornings free", strength="Prefer")
    assert said(app, "reading between 9 and 11am on saturdays") == [
        ("Keep Sat 8am–12pm free", "together they leave no time for reading on Saturdays", False)
    ]
    (conflict,) = app.do("rule_read", text="reading between 9 and 11am on saturdays")["conflicts"]
    assert conflict["days"] == ["sat"]


def test_a_day_one_rule_rules_out_on_its_own_is_no_contradiction(app: App) -> None:
    app.do("rule_add", text="no work on sundays", strength="Always")
    assert said(app, "deep work in the morning") == []
    assert said(app, "reading only on sundays") == [  # but reading would have no day at all
        ("No work on Sun", "together they leave no time for reading", False)
    ]


def test_rules_about_different_work_dont_contradict(app: App) -> None:
    app.do("rule_add", text="reading in the morning", strength="Prefer")
    assert said(app, "no gym in the morning") == []
    assert said(app, "gym in the evening") == []


def test_a_window_across_midnight_is_compared_by_the_clock(app: App) -> None:
    app.do("rule_add", text="deep work between 10pm and 1am", strength="Prefer")
    assert said(app, "no work after 11pm") == []  # 10 to 11pm is left
    assert [why for _, why, _ in said(app, "no work after 10pm")] == ["together they leave no time for deep work"]


def test_a_lighter_stretch_isnt_kept_free_so_it_contradicts_nothing(app: App) -> None:
    app.do("rule_add", text="reading in the evening", strength="Prefer")
    assert said(app, "keep evenings lighter") == []
    assert [why for _, why, _ in said(app, "keep evenings free")] == ["together they leave no time for reading"]


def test_the_same_rule_twice_and_different_amounts_overlap(app: App) -> None:
    app.do("rule_add", text="deep work in the morning", strength="Prefer")
    assert said(app, "deep work in the morning") == [
        ("Deep work between 8am and 12pm", "the same hours for deep work", True)
    ]
    assert said(app, "at most 6 hours a day") == [
        ("At most 8 h of work a day", "both limit work a day (6 h and 8 h); the lower one is what counts", True)
    ]
    assert said(app, "finish things 2 days early") == [
        (
            "Finish work a day before it’s due",
            "both say how early to finish work (1 and 2 days before it’s due); the earlier one is what counts",
            True,
        )
    ]
    assert said(app, "at most 2 hours of reading a day") == []  # a limit inside the day's limit


def test_the_list_shows_contradictions_on_both_rules_but_not_overlaps(app: App) -> None:
    app.do("rule_add", text="deep work in the morning", strength="Prefer")
    app.do("rule_add", text="no work before noon", strength="Strongly")
    app.do("rule_add", text="at most 6 hours a day", strength="Prefer")
    rules = mine(app)
    deep, noon = rules["Deep work between 8am and 12pm"], rules["No work before 12pm"]
    assert [c["other"] for c in deep["contradicts"]] == [noon["name"]]
    assert [c["other"] for c in noon["contradicts"]] == [deep["name"]]
    assert noon["contradicts"][0]["other_sentence"] == "Deep work between 8am and 12pm"
    assert rules["At most 6 h a day"]["contradicts"] == []


def test_saying_which_wins_settles_it_and_switching_one_off_does_too(app: App) -> None:
    app.do("rule_add", text="deep work in the morning", strength="Prefer")
    app.do("rule_add", text="no work before noon", strength="Prefer")
    rules = mine(app)
    deep, noon = rules["Deep work between 8am and 12pm"]["name"], rules["No work before 12pm"]["name"]
    answer = app.full("rule_win", payload={"winner": noon, "loser": deep}, provisional=False)
    assert all(not r["contradicts"] for r in mine(app).values())
    app.do("undo", command_id=answer.command_id)
    assert mine(app)["No work before 12pm"]["contradicts"]
    app.do("rule_set", name=deep, enabled=False)
    assert all(not r["contradicts"] for r in mine(app).values())
    # Nor does a switched-off rule count before adding: no "same hours" for the one switched off.
    assert said(app, "deep work in the morning") == [
        ("No work before 12pm", "together they leave no time for deep work", False)
    ]


def test_a_pace_says_which_days_pace_it_replaces(app: App) -> None:
    app.do("rule_add", text="go harder on saturdays")
    out = app.do("rule_read", text="go easier on saturdays and harder on sundays")
    assert out["effect"].endswith(". Replaces Push on Saturdays")
    assert out["conflicts"] == []
    assert "Replaces" not in app.do("rule_read", text="go harder on saturdays")["effect"]


def test_no_time_needs_both_rules() -> None:
    full, empty = (1 << 96) - 1, 0
    morning = sum(1 << q for q in range(32, 48))  # 8am to noon
    rest = full ^ morning
    assert no_time([morning] * 7, [rest] * 7) == ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    assert no_time([full] + [empty] * 6, [rest] * 7) is None  # Monday is ruled out by the first alone
    assert no_time([morning] * 7, [rest] * 6 + [full]) == DAYS  # Sunday by the second alone, but no time all week
    assert no_time([morning] * 7, [rest] * 6 + [empty]) == ("mon", "tue", "wed", "thu", "fri", "sat")


def test_a_kind_a_general_rule_leaves_out_isnt_compared_with_it() -> None:
    meals = {"type": "time_preference", "name": "meals", "scope": {"preset": "Routine"},
             "params": {"start": "14:00", "end": "11:00"}}  # fmt: skip
    work = {"type": "time_preference", "name": "work", "scope": {"except_preset": ["Routine"]},
            "params": {"start": "10:00", "end": "15:00"}}  # fmt: skip
    assert against(meals, [work]) == []
    assert [c.other for c in against(meals, [work | {"scope": None}])] == ["work"]
    assert contradictions([meals, work | {"scope": None}], []) == {
        "meals": [Conflict("work", "together they leave no time for routine")],
        "work": [Conflict("meals", "together they leave no time for routine")],
    }


def test_one_event_one_rule_a_new_optional_rule_takes_its_events_from_the_others(app: App) -> None:
    app.do("rule_add", text="gym and climbing club are optional")
    preview = app.do("rule_read", text="climbing club only if i'm ahead")["effect"]
    assert preview.endswith(". Takes it out of “Gym and Climbing Club are optional: work takes the time when it must”")
    out = app.do("rule_add", text="climbing club only if i'm ahead")
    assert out["message"] == (
        "Added: Climbing Club only when you’re ahead: work takes its time first. "
        "Taken out of “Gym and Climbing Club are optional: work takes the time when it must”"
    )
    rules = mine(app)
    assert set(rules) == {
        "Gym is optional: work takes the time when it must",
        "Climbing Club only when you’re ahead: work takes its time first",
    }
    titles = [r["params"]["titles"] for r in app.do("settings")["rules"] if r["type"] == "skippable"]
    assert sorted(titles) == [["climbing club"], ["gym"]]
    app.do("rule_set", name=rules["Gym is optional: work takes the time when it must"]["name"], strength="Strongly")
    assert "Gym is optional: work takes the time when it must" in mine(app)  # its kept reading says gym alone

    app.do("rule_add", text="gym only if i'm ahead")  # gym was all that rule had left: it goes
    assert set(mine(app)) == {
        "Climbing Club only when you’re ahead: work takes its time first",
        "Gym only when you’re ahead: work takes its time first",
    }


def test_the_same_amount_twice_overlaps_as_the_same_rule(app: App) -> None:
    app.do("rule_add", text="sleep at least 7 hours a night", strength="Prefer")
    assert said(app, "sleep at least 7 hours a night") == [
        ("At least 7 h of sleep a night", "the same night's sleep", True)
    ]
    app.do("rule_add", text="finish things 2 days early", strength="Prefer")
    assert ("Finish things 2 days before they're due", "the same head start for work", True) in said(
        app, "finish things 2 days early"
    )


def test_an_amount_rule_without_its_amount_is_compared_with_nothing() -> None:
    cap = {"type": "daily_load", "name": "cap", "params": {"threshold": "8h"}}
    unsaid = {"type": "daily_load", "name": "unsaid", "params": {}}
    assert against(unsaid, [cap]) == [] and contradictions([cap, unsaid], []) == {}
