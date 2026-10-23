import pytest

from friday.core.settings import TextSettings
from friday.core.textnorm import identity_text, norm, similarity, type_text

RULES = TextSettings().rules()


@pytest.mark.parametrize(
    ("title", "area", "words"),
    [
        ("PS4 (CS 1110)", "CS 1110", "problem set 4"),
        ("Problem Set #4", "CS 1110", "problem set 4"),
        ("HW IV – Part ii", "CS 1110", "homework 4 part 2"),
        ("Reading for Week 03", "CS 1110", "reading week 3"),
        ("ps4", None, "problem set 4"),
        ("PSET 12", None, "problem set 12"),
        ("cs1110 ps 4", "CS 1110", "problem set 4"),
        ("CS1110 Lab 3", "cs 1110", "lab 3"),
        ("Psych reading", None, "psych reading"),
        ("What I learned", None, "what i learned"),
        ("Part iii notes", None, "part 3 notes"),
        ("Chapter Seven", None, "chapter 7"),
        ("ch. 4 reading", None, "chapter 4 reading"),
        ("Lecture XII review", None, "lecture 12 review"),
        ("Exam II prep", None, "exam 2 prep"),
        ("Module 007", None, "module 7"),
        ("Week 0", None, "week 0"),
        ("Café run", None, "cafe run"),
        ("Résumé draft", None, "resume draft"),
        ("ＰＳ５", None, "problem set 5"),
        ("Shower", None, "shower"),
        ("shower!", None, "shower"),
        ("  The Shower  ", None, "shower"),
        ("Read the book on a train", None, "read book train"),
        ("Book IV", None, "book 4"),
        ("Henry V essay", None, "henry v essay"),
        ("Go to the store", None, "go store"),
        ("twenty questions", None, "20 questions"),
        ("Lab3b", None, "lab 3 b"),
        ("e-mail Prof. Lee", None, "e mail prof lee"),
        ("hw_2", None, "homework 2"),
        ("lec 10/14 notes", None, "lecture 10 14 notes"),
    ],
)
def test_titles_normalize_to_plain_words(title: str, area: str | None, words: str) -> None:
    assert identity_text(norm(title, RULES, area)) == words


def test_type_text_drops_numbers_so_problem_sets_count_as_one_kind() -> None:
    assert type_text(norm("PS3", RULES)) == type_text(norm("Problem Set 4", RULES)) == "problem set"
    assert identity_text(norm("PS3", RULES)) != identity_text(norm("PS4", RULES))


def test_abbreviations_replace_whole_words_only() -> None:
    assert norm("psych", RULES) == ["psych"]


@pytest.mark.parametrize(
    ("a", "b", "low", "high"),
    [
        ("problem set", "problem set", 1.0, 1.0),
        ("problem set", "problem set review", 1.0, 1.0),  # one word set contains the other
        ("reading", "lab report", 0.0, 0.4),
        ("lab report", "lab writeup", 0.5, 0.9),
    ],
)
def test_similarity(a: str, b: str, low: float, high: float) -> None:
    assert low <= similarity(a, b) <= high


def test_a_course_title_names_its_tag_spelled_as_you_already_spell_it() -> None:
    from friday.core.textnorm import course_tag

    assert course_tag("CS 2110 A5: Graphs", []) == "CS 2110"
    assert course_tag("MATH2940 HW 8", ["Math 2940"]) == "Math 2940"
    assert course_tag("Laundry", ["CS 2110"]) is None
