"""The two built-in rules for meals, routines and tasks with a range (15 Nov: both read "Give flexible items their
ideal time", and "full length" was no better: "whenever you're using a variable in parenthesis just say what it's
currently set to"). One gives each its ideal length, a preference folded among the planner's workings; the other
never cuts one below its shortest, and protects you, so it's listed with the rules you tune. Each names the lengths
as they are now."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)  # Monday 19 October, 09:00


def said(app: App) -> dict[str, dict]:
    return {r["name"]: r for r in app.do("rules")}


def meal(app: App, title: str, least: int, ideal: int, at: int) -> int:
    window = {"release_offset_min": at * 60 - 4 * 60, "due_offset_min": at * 60 - 2 * 60}  # from the 4am day start
    return app.do("series_add", title=title, preset="Routine", every="day", min_min=least, ideal_min=ideal,
                  max_min=ideal, **window)["id"]  # fmt: skip


def test_every_built_in_rule_says_something_of_its_own(app: App) -> None:
    for adding in (False, True):  # with nothing to name, and with meals
        if adding:
            meal(app, "Lunch", 30, 45, 12)
        defaults = [r["sentence"] for r in app.do("rules") if r["source"] == "default"]
        assert len(defaults) == len(set(defaults)), defaults


def test_they_say_each_meals_lengths_as_they_are(app: App) -> None:
    meal(app, "Dinner", 30, 60, 18)
    lunch = meal(app, "Lunch", 30, 45, 12)
    rules = said(app)
    assert (
        rules["elastic_shortfall"]["sentence"]
        == "Give meals and routines their ideal length: Lunch 45 min and Dinner 1 h"
    )
    assert (
        rules["elastic_minimum"]["sentence"]
        == "Never cut meals and routines below their shortest: Lunch 30 min and Dinner 30 min"
    )
    # the preference is folded among the planner's workings; never cutting a meal short is with the rules you tune
    assert rules["elastic_shortfall"]["background"] and not rules["elastic_minimum"]["background"]
    app.do("series_edit", id=lunch, min_min=45, ideal_min=60, max_min=60)
    rules = said(app)
    assert rules["elastic_shortfall"]["sentence"].endswith(": Lunch 1 h and Dinner 1 h")
    assert rules["elastic_minimum"]["sentence"].endswith(": Lunch 45 min and Dinner 30 min")


def test_many_are_a_few_and_how_many_more_and_tasks_with_a_range_are_named(app: App) -> None:
    for title, at in (("Breakfast", 8), ("Lunch", 12), ("Dinner", 18)):
        meal(app, title, 15, 30, at)
    app.do("add", text="essay draft ~1-2h due fri")
    rules = said(app)
    assert rules["elastic_shortfall"]["sentence"] == (
        "Give meals, routines and tasks with a range their ideal length: Breakfast 30 min, Lunch 30 min, Dinner 30 min "
        "and 1 more"
    )
    assert rules["elastic_minimum"]["sentence"].startswith(
        "Never cut meals, routines and tasks with a range below their shortest: Breakfast 15 min,"
    )
