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
        (
            "no work between 11:30pm and 7am",
            Reading("window", "work", rel="not_between", at="23:30", until="07:00"),
            "Prefer",
        ),
        (
            "no reading in the morning",
            Reading("window", "reading", rel="not_between", at="08:00", until="12:00"),
            "Prefer",
        ),
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


def test_no_work_between_two_times_avoids_those_hours_not_the_rest() -> None:
    night = Reading("window", "work", rel="not_between", at="07:00", until="10:00")
    assert sentence(night) == "No work between 7am and 10am"
    assert spec(night, "Strongly", "you:mornings", [], [])["params"] == {"start": "07:00", "end": "10:00", "price": 6.0}
    gym = spec(Reading("window", "gym", rel="between", at="17:00", until="19:00"), "Prefer", "you:gym", [], [])
    assert (gym["params"]["start"], gym["params"]["end"]) == ("19:00", "17:00")  # the other hours


def test_what_it_cannot_read_is_none() -> None:
    assert read("make me a sandwich")[0] is None


def test_a_reading_becomes_a_planner_rule_in_your_words() -> None:
    lunch = Reading("window", "lunch", rel="before", at="13:00")
    assert sentence(lunch) == "Lunch before 1pm"
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


@pytest.mark.parametrize(
    ("text", "paces"),
    [
        ("go easier on saturday and go harder on sunday", (("sat", "Easy"), ("sun", "Push"))),
        ("take it easy on weekends", (("sat", "Easy"), ("sun", "Easy"))),
        ("saturdays are easy, sundays are hard", (("sat", "Easy"), ("sun", "Push"))),
        ("go easy on saturdays and sundays", (("sat", "Easy"), ("sun", "Easy"))),
        ("push on sundays", (("sun", "Push"),)),
    ],
)
def test_a_pace_for_some_weekdays_every_week(text: str, paces: tuple) -> None:
    reading, _ = read(text)
    assert reading is not None and reading.kind == "pace" and reading.paces == paces


def test_pace_words_alone_or_beside_other_rules_read_as_before() -> None:
    assert read("no work on sundays")[0] == Reading("days", "work", rel="not_on", days=("sun",))
    mixed = read("go easier on saturday and no work on sunday")[0]
    assert mixed is None or mixed.kind != "pace"  # half a pace isn't read as all of one
    assert sentence(read("go easier on saturday and go harder on sunday")[0]) == "Easy on Saturdays, Push on Sundays"


@pytest.mark.parametrize(
    "text",
    ["push when neccessary for work not to be late", "push when necessary for work not to be late",
     "don't let work be late", "work harder if needed so nothing is late"],
)  # fmt: skip
def test_working_more_so_nothing_is_late_reads_as_deadlines_first(text: str) -> None:
    reading, _ = read(text)
    assert reading is not None and reading.kind == "deadlines" and sentence(reading) == "Deadlines come first"


def test_rules_that_mention_due_dates_still_read_as_themselves() -> None:
    assert read("finish essays 2 days before they're due")[0] == Reading("early", "essays", amount=2.0)


@pytest.mark.parametrize(
    "text",
    [
        "gym and climbing club are optional",
        "make the gym sessions on tuesday and thursday as well as climbing club be not mandatory",
        "skip gym and climbing club if there is too much work",
        "gym and climbing club can be skipped",
    ],
)
def test_events_that_give_way_to_work(text: str) -> None:
    reading, _ = read(text)
    assert reading == Reading("optional", "events", events=("gym", "climbing club"))
    assert sentence(reading) == "Gym and Climbing Club are optional: work takes the time when it must"
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["params"]["titles"]) == ("skippable", ["gym", "climbing club"])


@pytest.mark.parametrize(
    "text",
    [
        "i usually don't go to the climbing club becasue of my workload so I will only go if I am ahead of my work",
        "climbing club only if i'm ahead",
        "Climbing club only when I'm caught up on work",
        "only go to climbing club when I'm on top of my work",
        "I only go to the climbing club if I have time",
        "skip climbing club unless I'm ahead",
        "I usually skip climbing club because of work",
        "I usually skip climbing club",
    ],
)
def test_events_you_go_to_only_when_ahead(text: str) -> None:
    reading, _ = read(text)
    assert reading == Reading("ahead", "events", events=("climbing club",))
    assert sentence(reading) == "Climbing Club only when you’re ahead: work takes its time first"
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["stage"]) == ("skippable", "preferences")  # below every late night, not above it
    assert rule["params"] == {"titles": ["climbing club"], "price": 1.0, "ahead": True}


def test_optional_and_ahead_read_apart() -> None:
    assert read("gym and climbing club only if I am ahead of my work")[0] == Reading(
        "ahead", "events", events=("gym", "climbing club")
    )
    assert read("skip gym if there is too much work")[0] == Reading("optional", "events", events=("gym",))
    assert read("gym is optional")[0].kind == "optional"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("text", "strength"),
    [
        ("if i am going to climbing club the next day then the previous day must end at 10:00", "Always"),
        ("no work after 10pm the night before climbing club", "Prefer"),
        ("stop working at 10 the night before climbing club", "Prefer"),
    ],
)
def test_the_night_before_an_event_ends_early(text: str, strength: str) -> None:
    reading, read_strength = read(text)
    assert (
        reading == Reading("night_before", "work", at="22:00", events=("climbing club",)) and read_strength == strength
    )
    assert sentence(reading) == "No work after 10pm the night before Climbing Club"
    rule = spec(reading, "Always", "you:x", [], [])
    assert (rule["type"], rule["params"]) == (
        "before_event",
        {"titles": ["climbing club"], "after": "22:00", "price": "forbid"},
    )


def test_a_lighter_stretch_keeps_about_half_of_it_free() -> None:
    reading, _ = read("Keep Friday and Saturday nights lighter")
    assert reading == Reading("free", "work", rel="between", at="22:00", until="02:00", days=("fri", "sat"), amount=0.5)
    assert sentence(reading) == "Keep Fri, Sat 10pm–2am lighter"
    rule = spec(reading, "Prefer", "you:x", [], [])
    assert (rule["type"], rule["params"]["free"]) == ("reserve", "2h")  # half of four hours: less work, not none
    assert read("lighter friday evenings")[0].amount == 0.5 and read("keep saturday mornings free")[0].amount is None
