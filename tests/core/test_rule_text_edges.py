"""Rules from sentences, at the edges: what the grammar declines to read, the smaller ways a cap or a buffer is
said, sentences naming two stretches of the day, and the scope a rule's subject becomes."""

import pytest

from friday.core.rule_text import (
    Reading,
    bare_hour,
    buffer_said,
    read,
    read_all,
    read_cap,
    scope_of,
    singular,
    span_said,
)

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")


@pytest.mark.parametrize(
    "text",
    [
        "no work 2 hours before bed",  # about your night, not an event called bed
        "at least 2 hours of sleep",  # too little to be a floor anyone plans
        "at least 13 hours of sleep",  # too much
        "I work best in the morning",  # a liking, not a rule
        "space it 2 days apart",  # no subject to space
    ],
)
def test_sentences_the_grammar_leaves_unread(text: str) -> None:
    assert read(text) == (None, "Prefer")


def test_an_hour_with_minutes_and_pm_reads_as_said() -> None:
    assert read("no work after 9:30pm")[0] == Reading("window", "work", rel="before", at="21:30")


def test_a_day_range_ending_in_a_word_that_is_no_day_keeps_the_first_day() -> None:
    assert read("no work mon through funday")[0] == Reading("days", "work", rel="not_on", days=("mon",))


def test_a_day_max_for_some_work_is_a_cap_on_that_work() -> None:
    assert read("2h/day max for client work")[0] == Reading("cap", "client work", amount=2.0)


def test_hours_max_on_some_days_is_a_cap_on_those_days() -> None:
    assert read("3h max on weekdays")[0] == Reading("cap", "work", amount=3.0, days=WEEKDAYS)
    assert read("3 hours max")[0] == Reading("cap", "work", amount=3.0)


def test_a_cap_said_after_its_hours_reads_as_a_cap_on_its_own() -> None:
    # A whole sentence is rewritten first ("2h a day max" is "at most 2h a day"); the cap reads either.
    assert read_cap(" 2h/day max for client work ", False) == Reading("cap", "client work", amount=2.0)
    assert read_cap(" 3h max on weekdays ", False) == Reading("cap", "work", amount=3.0, days=WEEKDAYS)


def test_an_hour_said_with_its_half_of_the_day_is_left_as_said() -> None:
    assert bare_hour("after", "9pm") == "9pm"
    assert (bare_hour("before", "6"), bare_hour("after", "12"), bare_hour("after", "9")) == ("6am", "12am", "9")


def test_spacing_says_days_apart() -> None:
    assert read("space gym 2 days apart")[0] == Reading("spacing", "gym", amount=2.0)


def test_the_same_stretch_said_twice_is_read_as_the_whole_sentence() -> None:
    assert read_all("no work between 7 and 8am and no work between 7 and 8am") == ([], "Prefer")


def test_two_stretches_with_their_own_subjects_are_two_rules() -> None:
    found, _ = read_all("no work between 7 and 8am and gym between 9 and 10am")
    assert found == [
        Reading("window", "work", rel="not_between", at="07:00", until="08:00"),
        Reading("window", "gym", rel="between", at="09:00", until="10:00"),
    ]


def test_a_buffer_and_a_span_are_said_back_in_their_own_unit() -> None:
    assert [buffer_said(m) for m in (90, 60, 120, 1440, 2880)] == ["90 min", "1 hour", "2 hours", "1 day", "2 days"]
    assert [span_said(m) for m in (45, 60, 90)] == ["45 min", "1 h", "90 min"]


@pytest.mark.parametrize(
    ("word", "one"),
    [("exams", "exam"), ("studies", "study"), ("classes", "class"), ("boxes", "box"), ("matches", "match")],
)
def test_a_plural_finds_its_singular(word: str, one: str) -> None:
    assert singular(word) == one


def test_work_during_some_time_is_scoped_to_the_work_alone() -> None:
    assert scope_of("work during lunch", [], []) is None
    assert scope_of("reading during lunch", [], []) == {"title": "reading"}


def test_either_of_two_subjects_scopes_by_both() -> None:
    assert scope_of("math or history", ["Math", "History"], []) == {"subject": ["Math", "History"]}
    assert scope_of("reading or chores", [], ["Reading", "Chore"]) == {"preset": ["Reading", "Chore"]}


def test_a_subject_mixing_a_course_and_a_kind_has_no_scope() -> None:
    assert scope_of("math or reading", ["Math"], ["Reading"]) is None
