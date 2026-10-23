"""A task's kind and course read from its title when you didn't say (COMBINED.md 55), as personal's adapter read them:
"MATH 2940 HW 7" is an Assignment for MATH 2940, "Study guide for prelim 2" is Exam prep. Only presets you have are
guessed, and only when the title says so plainly; the add box shows the guess as a chip you can change. Pure.
"""

import re
from collections.abc import Container

COURSE = re.compile(r"\b([A-Z]{2,5})\s?(\d{4})\b")
# Study guides, review sheets and practice exams are exam prep (personal's decision 45), ahead of everything else.
STUDY = re.compile(
    r"\b(study guide|review sheet|review packet|practice (exam|prelim|midterm|test|quiz|final)|cram|"
    r"prep (for|quiz|exam|prelim|midterm)|study for)\b",
    re.IGNORECASE,
)
PROBLEM_SET = re.compile(
    r"\b(prob\w*\s*sets?|p-?sets?|hw\s*\d*|homework|ps\s*\d+|worksheets?|exercises?)\b", re.IGNORECASE
)
WORDS = (  # the first that matches wins
    ("Exam prep", re.compile(r"\b(prelim|midterm|exam|final exam|quiz)\b", re.IGNORECASE)),
    ("Project", re.compile(r"\bproject\b", re.IGNORECASE)),
    ("Assignment", re.compile(r"\b(essay|paper|draft|write[- ]?up|lab)\b", re.IGNORECASE)),
    ("Reading", re.compile(r"\b(read|reading|chapter|ch\.)", re.IGNORECASE)),
)


def guess_preset(title: str, presets: Container[str]) -> str | None:
    """The preset a title says it is, if you have it."""
    if STUDY.search(title):
        found = "Exam prep"
    elif PROBLEM_SET.search(title):
        found = "Assignment"
    else:
        found = next((preset for preset, words in WORDS if words.search(title)), None)
    return found if found is not None and found in presets else None


def course_of(title: str) -> str | None:
    """A course code in the title, like "CS 2110"."""
    m = COURSE.search(title)
    return f"{m.group(1)} {m.group(2)}" if m else None


EXAM = re.compile(r"\b(exam|prelim|midterm|final|quiz)\b", re.IGNORECASE)


def course_word(title: str) -> str:
    """The course a title is about, as one word for comparing ("math" for "MATH 2940 Prelim"); its first word when
    no course code is found."""
    m = COURSE.search(title) or re.search(r"\b([A-Za-z]{2,5})\s?(\d{4})\b", title)
    return (m.group(1) if m else (title.split() or [""])[0]).lower()
