"""Kinds and courses read from titles (COMBINED.md 55), and the title keys and fallback ratings for skips (56)."""

import pytest

from friday.core.calendars import fallback_level, rating_key
from friday.core.guess import course_of, course_word, guess_preset

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
