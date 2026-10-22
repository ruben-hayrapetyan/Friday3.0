"""Rules from sentences: what the grammar reads, and the planner rule each reading becomes."""

import pytest

from friday.core.rule_text import Reading, read, sentence, spec


@pytest.mark.parametrize(
    ("text", "reading", "strength"),
    [
        ("I prefer eating lunch before 1pm", Reading("window", "lunch", rel="before", at="13:00"), "Prefer"),
        (
            "No work after 10pm on weekdays",
            Reading("window", "work", rel="before", at="22:00", days=("mon", "tue", "wed", "thu", "fri")),
            "Prefer",
        ),
        (
            "deep work in the morning",
            Reading("window", "deep work", rel="between", at="08:00", until="12:00"),
            "Prefer",
        ),
        ("gym between 5 and 7", Reading("window", "gym", rel="between", at="17:00", until="19:00"), "Prefer"),
        ("never work on sundays", Reading("days", "work", rel="not_on", days=("sun",)), "Always"),
        ("reading only on weekends", Reading("days", "reading", rel="on", days=("sat", "sun")), "Prefer"),
        (
            "keep saturday mornings free",
            Reading("free", "work", rel="between", at="08:00", until="12:00", days=("sat",)),
            "Prefer",
        ),
        ("really keep evenings free", Reading("free", "work", rel="between", at="17:00", until="22:00"), "Strongly"),
        ("at most 6 hours a day", Reading("cap", "work", amount=6.0), "Prefer"),
        ("no more than 2h of reading a day", Reading("cap", "reading", amount=2.0), "Prefer"),
        ("finish things a day early", Reading("early", "work", amount=1.0), "Prefer"),
        ("gym right after class", Reading("after", "gym", event="class"), "Prefer"),
    ],
)
def test_the_grammar_reads(text: str, reading: Reading, strength: str) -> None:
    assert read(text) == (reading, strength)


def test_what_it_cannot_read_is_none() -> None:
    assert read("make me a sandwich")[0] is None


def test_a_reading_becomes_a_planner_rule_in_your_words() -> None:
    lunch = Reading("window", "lunch", rel="before", at="13:00")
    assert sentence(lunch) == "Lunch before 13:00"
    soft = spec(lunch, "Prefer", "you:lunch", [], ["Reading"])
    assert (soft["type"], soft["scope"], soft["params"]) == (
        "time_preference",
        {"title": "lunch"},
        {"start": "13:00", "end": "04:00", "price": 2.0},
    )
    assert spec(lunch, "Always", "you:lunch", [], [])["params"]["price"] == "forbid"
    cap = spec(Reading("cap", "reading", amount=2.0), "Strongly", "you:cap", [], ["Reading"])
    assert (cap["type"], cap["scope"], cap["weight"], cap["params"]) == (
        "daily_load",
        {"preset": "Reading"},
        15.0,
        {"threshold": "2h"},
    )
