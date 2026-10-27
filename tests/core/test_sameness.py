"""Whether two titles name the same thing (27 Oct: "make many test suites testing many different potentially duplicate
situations because these can definitely get complicated although them still being duplicate"). Each suite is one
kind of difference between two titles of the same thing, and the near misses that look alike but aren't."""

import pytest

from friday.core.sameness import read_title, same_thing
from friday.core.settings import DEFAULTS

RULES = DEFAULTS["text"].rules()


def check(pairs: list[tuple[str, str]], same: bool) -> None:
    wrong = [(a, b) for a, b in pairs if same_thing(a, b, RULES) != same or same_thing(b, a, RULES) != same]
    assert wrong == [], f"{'not read as the same' if same else 'read as the same'}: {wrong}"


# Your inbox on 27 Oct: each was proposed though you had it.
FROM_YOUR_INBOX = [
    ("WWA 7: Material Write-Up 'B' Draft", "Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]"),
    ("Academic Integrity Quiz", "Academic Integrity Quiz - Complete Before Class Meeting [ENGRG1050]"),
    ("Core Values Impact", "Core Values Impact (Required) [ENGRG1050]"),
    ("Ethics Exit Reflection", "Ethics Exit Ticket Reflection [ENGRG1050]"),
    ("AI Module Proof of Completion", "AI Literacy Proof of Completion [ENGRG1050]"),
    ("Career Podcast Reflection", "Engineering Career Podcast Reflection [ENGRG1050]"),
    ("A4dd", "A4dd"),
    ("CS 2112 Lecture", "CS 2112 Lecture (room 155)"),
    ("ENGRG 1050 Seminar", "ENGRG 1050 Seminar"),
    ("Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]",
     "Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]"),
]  # fmt: skip


YOUR_TODOS = [  # pairs of your own to-dos on 27 Oct that are one thing
    ('Read book "Active Portfolio Management" by Grinold and Khan', 'Read "Active Portfolio Management"'),
    ("Chem Chapter 19", "Chem read chapter 19"),
    (
        "Psych 1130 WA7 Material Write-Up B draft",
        "Weekly Writing Assignment 7: Material Write-Up 'B' Draft [PSYCH1130]",
    ),
    ("Read", "read"),
    ("Cornell Poker", "Cornell Poker"),
]


def test_your_own_to_dos_that_are_one_thing_are_read_as_one() -> None:
    check(YOUR_TODOS, same=True)


def test_what_your_inbox_proposed_again_is_the_same_thing() -> None:
    check(FROM_YOUR_INBOX, same=True)


ABBREVIATIONS = [
    ("PS 4", "Problem Set 4"),
    ("Chem 2090 PS9", "CHEM 2090 Problem Set 9"),
    ("HW 3", "Homework 3"),
    ("Math HW9", "Math 1920 Homework 9"),
    ("Read ch. 14", "Read Chapter 14"),
    ("Chap 2 reading", "Chapter 2 reading"),
    ("Lec 5 notes", "Lecture 5 notes"),
    ("Proj 2 proposal", "Project 2 proposal"),
    ("WWA 8: Chapter Add-In B Draft", "Weekly Writing Assignment 8: Chapter Add-In B Draft"),
    ("CS A4 DD", "CS A4 Design Doc"),
    ("A4dd", "CS A4 Design Doc"),
    ("TA OH", "TA Office Hours"),
    ("ECE lab report 3", "ECE Lab Report 3"),
]


def test_abbreviations_and_initialisms_are_spelled_out() -> None:
    check(ABBREVIATIONS, same=True)


COURSES = [
    ("PS 9 [CHEM2090]", "CHEM 2090 PS 9"),
    ("CHEM2090 Problem Set 9", "Chem 2090: Problem Set 9"),
    ("Problem Set 9", "CHEM 2090 Problem Set 9"),  # one without a course may be the other's
    ("Prelim 2", "MATH 1920 Prelim 2"),
    ("[CS 2112] A4: Interpretation and Simulation", "A4: Interpretation and Simulation"),
    ("Weekly Writing Assignment 7 [PSYCH1130]", "PSYCH 1130 Weekly Writing Assignment 7"),
]

OTHER_COURSES = [
    ("CHEM 2090 Problem Set 9", "CHEM 2091 Problem Set 9"),
    ("MATH 1920 Prelim 2", "MATH 2940 Prelim 2"),
    ("CS 2112 Lecture", "CS 2110 Lecture"),
    ("PSYCH 1130 Weekly Writing Assignment 7", "ENGL 1130 Weekly Writing Assignment 7"),
]


def test_a_course_written_any_way_or_left_out_is_the_same_course() -> None:
    check(COURSES, same=True)


def test_another_course_is_another_thing() -> None:
    check(OTHER_COURSES, same=False)


NUMBERS = [
    ("Problem Set 09", "Problem Set 9"),
    ("Quiz three", "Quiz 3"),
    ("Exam III", "Exam 3"),
    ("Part II reading", "Part 2 reading"),
    ("A4: Interpretation and Simulation", "A4 Interpretation & Simulation"),
    ("Q3 quiz", "Q3 Quiz"),
]

OTHER_NUMBERS = [
    ("Problem Set 9", "Problem Set 10"),
    ("Chem 2090 Problem Set 9", "Chem 2090 Problem Set 10"),
    ("WWA 7: Material Write-Up 'B' Draft", "WWA 8: Material Write-Up 'B' Draft"),
    ("Prelim 1", "Prelim 2"),
    ("Quiz", "Quiz 3"),  # the generic isn't the third
    ("Chapter 13", "Chapter 14"),
    ("A3 Oral Evaluation", "A4 Oral Evaluation"),
    ("Lecture 5", "Lecture 15"),
    ("Exam III", "Exam 2"),
]


def test_a_number_written_any_way_is_the_same_number() -> None:
    check(NUMBERS, same=True)


def test_another_number_is_another_one() -> None:
    check(OTHER_NUMBERS, same=False)


PARTS = [
    ("Textbook Contribution B", "Textbook Contribution 'B'"),
    ("Part A: Methods", "Part A Methods"),
    ("Lab report part b", "Lab Report Part B"),
]

OTHER_PARTS = [
    ("Part A: Methods", "Part B: Methods"),
    ("Material Write-Up 'A' Draft", "Material Write-Up 'B' Draft"),
    ("Textbook Contribution A", "Textbook Contribution B"),
]


def test_a_lettered_part_is_the_same_part() -> None:
    check(PARTS, same=True)


def test_another_part_is_another_one() -> None:
    check(OTHER_PARTS, same=False)


WORDING = [
    ("Submit: Ethics Exit Ticket Reflection", "Ethics Exit Ticket Reflection"),
    ("Due: Core Values Impact", "Core Values Impact"),
    ("Reminder - Academic Integrity Quiz", "Academic Integrity Quiz"),
    ("Simulation and Interpretation (A4)", "A4: Interpretation and Simulation"),  # another order
    ("ethics EXIT ticket reflection!!", "Ethics Exit Ticket Reflection"),  # case and punctuation
    ("Café reflections", "Cafe Reflection"),  # accents and plurals
    ("Ethics exit reflections", "Ethics Exit Reflection"),
    ("Pay Salsa dues", "Pay salsa dues"),
    ("Order Salsa merch by Friday", "Order Salsa merch"),
]


def test_extra_words_order_case_punctuation_and_plurals_dont_matter() -> None:
    check(WORDING, same=True)


LOOK_ALIKE = [
    ("Essay draft", "Essay final"),  # one word apart: not mostly the same
    ("Chapter 4 reading", "Chapter 4 quiz"),
    ("CS 2112 Lecture", "CS 2112 Discussion"),
    ("Order Salsa merch", "Pay Salsa dues"),
    ("Salsa Club practice", "Salsa Halloween Social"),
    ("Interview prep", "Interview"),  # a single word inside more needs something else to go on
    ("Gym", "Gym bag"),
    ("Read papers for CUAI", "CUAI meeting"),
    ("HRL survey", "Hockey tickets"),
    ("Exam 3 review sheet", "Exam 3 prep"),
    ("Weekly Routine grid", "Weekly Writing Assignment"),
    ("CS 2112", "CS 2112 Lecture"),
    # Your to-dos on 27 Oct: two readings for one course share "CS read" and are still two.
    ("CS read Recursive sorting algorithm", "CS read Sorting"),
    ("CS read Design Interfaces", "CS Read modular design"),
    ("Chem read chapter 19", "Chem read chapter 20"),
    ("Read", "Write"),
]


def test_things_that_only_look_alike_are_kept_apart() -> None:
    check(LOOK_ALIKE, same=False)


PLACES = [
    ("CS 2112 Lecture (room 155)", "CS 2112 Lecture (room 155)"),
    ("Psych 1130 (room 312)", "PSYCH 1130"),
    ("Olin 603 study room", "Olin 603 study room booking"),
]

OTHER_PLACES = [
    ("CS 2112 Lecture (room 155)", "CS 2112 Lecture (room 200)"),  # another section
    ("Olin 603 study room", "Olin 605 study room"),
]


def test_a_room_written_on_one_is_the_same_thing() -> None:
    check(PLACES, same=True)


def test_another_room_is_another_thing() -> None:
    check(OTHER_PLACES, same=False)


@pytest.mark.parametrize(
    ("title", "numbers", "courses", "letters"),
    [
        ("Chem 2090 PS9", {"9"}, {"chem 2090"}, set()),
        ("A4dd", {"a4"}, set(), set()),
        ("Material Write-Up 'B' Draft", set(), set(), {"b"}),
        ("A dentist appointment", set(), set(), set()),  # "a" is an article here
        ("Part A", set(), set(), {"a"}),
        ("CS 2112 Lecture (room 155)", set(), {"cs 2112"}, set()),
    ],
)
def test_what_a_title_says(title: str, numbers: set, courses: set, letters: set) -> None:
    read = read_title(title, RULES)
    assert (set(read.numbers), set(read.courses), set(read.letters)) == (numbers, courses, letters)
