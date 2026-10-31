"""Kinds and courses read from titles (COMBINED.md 55), and the title keys and fallback ratings for skips (56)."""

import pytest

from friday.core.calendars import fallback_level, rating_key
from friday.core.guess import course_of, course_word, guess_preset, subject_of, subjects

PRESETS = {"Assignment", "Reading", "Exam prep", "Project", "Errand"}


@pytest.mark.parametrize(
    ("title", "preset"),
    [
        ("MATH 2940 HW 7", "Assignment"),
        ("CS 2800 Problem Set 7", "Assignment"),
        ("pset 3", "Assignment"),
        ("PS 4 odds", "Assignment"),
        ("Chem worksheet", "Assignment"),
        ("Study guide for prelim 2", "Exam prep"),
        ("Make review sheet", "Exam prep"),
        ("Practice prelim", "Exam prep"),
        ("Math quiz prep", "Exam prep"),
        ("Prep for midterm", "Exam prep"),
        ("ECON final exam", "Exam prep"),
        ("History essay draft", "Assignment"),
        ("Lab report 3", "Assignment"),
        ("Read chapter 7", "Reading"),
        ("Psych reading", "Reading"),
        ("Group project", "Project"),
        ("Buy groceries", None),
        ("Call mom", None),
        ("", None),
    ],
)
def test_a_title_says_its_kind(title: str, preset: str | None) -> None:
    assert guess_preset(title, PRESETS) == preset


def test_only_kinds_you_have_are_guessed() -> None:
    assert guess_preset("Study guide", {"Assignment"}) is None
    assert guess_preset("pset 3", set()) is None


@pytest.mark.parametrize(
    ("title", "course"),
    [("MATH 2940 HW 7", "MATH 2940"), ("CS2110 A5", "CS 2110"), ("cs 2110 a5", None), ("Essay", None)],
)
def test_a_course_code_is_read_from_the_title(title: str, course: str | None) -> None:
    assert course_of(title) == course


def test_the_course_word_falls_back_to_the_first_word() -> None:
    assert course_word("MATH 2940 Prelim") == "math"
    assert course_word("math 2940 quiz prep") == "math"
    assert course_word("Chem quiz prep") == "chem"
    assert course_word("") == ""


@pytest.mark.parametrize(
    ("title", "level"),
    [
        ("CS 2110 Lecture", "required"),
        ("ECON Discussion", "required"),
        ("Dentist appointment", "required"),
        ("Work shift", "required"),
        ("CS 2110 Office Hours", "optional"),
        ("Poker night", "optional"),
        ("Ping pong", "optional"),
        ("Info session: Jane Street", "optional"),
        ("Dinner with Sam", "likely"),
        ("Club meeting", "likely"),
    ],
)
def test_without_the_ai_a_title_says_how_much_an_event_matters(title: str, level: str) -> None:
    assert fallback_level(title) == level


def test_a_series_shares_one_rating_key() -> None:
    assert (
        rating_key("Big Red Hacks  committee #3") == rating_key("big red hacks committee") == "big red hacks committee"
    )
    assert rating_key("  Poker Night 2 ") == "poker night"


# What a week's hours went to, when nothing has a tag (31 Oct: one "No tag" row held the whole week).
TITLES = [
    "Chem 2090 Problem Set 9 Evens",
    "Chem Chapter 13",
    "CS read Sorting",
    "Prep for CS Oral Exam",
    "Math read 16.5",
    "Prep: MATH 1920 Quiz 3",
    "Math 1920 HW9",
    "Psych website",
    "Psych 1130 WA8 draft",
    "CATC Assignment 2 PR",
    "Read Papers for CUAI",
    "Jane Street application",
    "Jane Street coding round",
    "make schedule",
    "Jump Hour",
]


def test_subjects_come_from_course_codes_capitals_and_shared_first_words() -> None:
    known = subjects(TITLES)
    assert set(known.values()) >= {"Chem", "CS", "Math", "Psych", "CATC", "CUAI", "Jane Street"}
    assert "make" not in known and "jump" not in known  # a verb, and a word one title starts with
    assert "pr" not in known and "wa" not in known  # parts of a task, not what it's for


def test_a_to_do_goes_with_its_course_spelled_as_you_mostly_spell_it() -> None:
    known = subjects(TITLES)
    assert [subject_of(t, known) for t in ("Prep: MATH 1920 Quiz 3", "Math read 16.5", "Prep for CS Oral Exam")] == [
        "Math",
        "Math",
        "CS",
    ]
    assert subject_of("Read Papers for CUAI", known) == "CUAI"
    assert subject_of("CATC Assignment 2 PR", known) == "CATC"
    assert subject_of("make schedule", known) is None
