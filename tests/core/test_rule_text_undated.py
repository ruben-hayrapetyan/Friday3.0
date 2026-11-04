"""Rules about work with no due date, in your words (3 Nov: "the undated time slots thing should be completely
learned/dictated by rules"), and strength words kept out of what a rule is about."""

import pytest

from friday.core.rule_text import read, spec, undated_said


@pytest.mark.parametrize(
    "text",
    [
        "undated work only between 2pm and 10pm",
        "no undated work after 12am",
        "no work without a due date after midnight",
        "work with no due date only in the afternoon",
        "never do tasks without deadlines after 11pm",
        "no undated tasks on weekends",
        "prefer undated work in the afternoon",
    ],
)
def test_ways_of_saying_undated_work_are_a_rule_about_work_with_no_due(text: str) -> None:
    reading, strength = read(text)
    assert reading is not None
    assert spec(reading, strength, "x", [], ["Assignment"])["scope"] == {"dated": False}


def test_only_between_is_priced_outside_and_always_walls_it() -> None:
    reading, _ = read("undated work only between 2pm and 10pm")
    assert reading is not None
    rule = spec(reading, "Always", "x", [], [])
    assert rule["params"] == {"start": "22:00", "end": "14:00", "price": "forbid"}
    assert rule["reason"] == "Undated work between 2pm and 10pm"


def test_dated_and_titled_work_isnt_undated() -> None:
    assert undated_said("a dated report") == "a dated report"
    assert undated_said("No work after 10pm") == "No work after 10pm"
    reading, strength = read("no homework after 10pm")
    assert reading is not None and spec(reading, strength, "x", [], ["Assignment"])["scope"] == {"preset": "Assignment"}


@pytest.mark.parametrize(
    ("text", "scope"),
    [
        ("Strongly prefer deep work in the afternoon", {"energy": "deep"}),
        ("prefer homework in the afternoon", {"preset": "Assignment"}),
        ("ideally chem in the morning", {"title": "chem"}),
    ],
)
def test_a_strength_word_isnt_what_the_rule_is_about(text: str, scope: dict) -> None:
    # 3 Nov: "prefer homework in the afternoon" was a rule about work titled "prefer homework"
    reading, strength = read(text)
    assert reading is not None and spec(reading, strength, "x", [], ["Assignment"])["scope"] == scope
