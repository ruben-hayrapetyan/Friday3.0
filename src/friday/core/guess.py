"""A task's kind and course read from its title when you didn't say (COMBINED.md 55), as personal's adapter read them:
"MATH 2940 HW 7" is an Assignment for MATH 2940, "Study guide for prelim 2" is Exam prep. Only presets you have are
guessed, and only when the title says so plainly; the add box shows the guess as a chip you can change. Pure.
"""

import re
from collections import Counter
from collections.abc import Container, Iterable

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


def course_code(title: str) -> str | None:
    """A title's course with its number ("phys 2213" for "PHYS 2213 prelim 2 prep"), or None without one."""
    m = re.search(r"\b([A-Za-z]{2,5})\s?(\d{4})\b", title)
    return f"{m.group(1).lower()} {m.group(2)}" if m else None


def same_course(a: str, b: str) -> bool:
    """Two titles about the same course: by number when both give one (PHYS 1112's quiz isn't PHYS 2213's), else by
    the department or first word ("Math quiz prep" goes with "MATH 2940 Quiz 3")."""
    code_a, code_b = course_code(a), course_code(b)
    if code_a and code_b:
        return code_a == code_b
    return course_word(a) == course_word(b)


def course_word(title: str) -> str:
    """The course a title is about, as one word for comparing ("math" for "MATH 2940 Prelim"); its first word when
    no course code is found."""
    m = COURSE.search(title) or re.search(r"\b([A-Za-z]{2,5})\s?(\d{4})\b", title)
    return (m.group(1) if m else (title.split() or [""])[0]).lower()


# Words a to-do can start with that say what you'll do, not what it's for ("Read Papers for CUAI", "Email Linwei").
DOING = frozenset(
    "read reading reread email e-mail make pay clean prep prepare write finish study review do call buy submit check "
    "fix update send meet start plan practice work watch go get book ask print sign apply text reply look find set "
    "the a an my and to for of new first last final".split()
    # and short capitals that are parts of a task, not what it's for ("CATC Assignment 2 PR", "Psych HW")
    + "hw ps pr wa ta oh tbd asap pdf ii iii iv vi am pm".split()
)
ACRONYM = re.compile(r"^[A-Z]{2,6}$")
ANY_COURSE = re.compile(r"\b([A-Za-z]{2,5})\s?(\d{4})\b")
WORD = re.compile(r"[A-Za-z][A-Za-z&-]*")


def subjects(titles: Iterable[str]) -> dict[str, str]:
    """The subjects your to-dos are for, read from their titles: the department of a course code ("Chem" of "Chem
    2090 Problem Set 9"), a short name in capitals ("CATC Assignment 2", "Read Papers for CUAI"), or a first word two
    or more titles share ("Psych website", "Psych WA7"). Keyed by the word in lower case, spelled as you mostly spell
    it ("Math" for "Math read 16.5" and "Prep: Math 1920 Quiz 3")."""
    spellings: dict[str, Counter[str]] = {}
    firsts: Counter[str] = Counter()
    seconds: dict[str, Counter[str]] = {}  # the word after a first word: "Jane" is always "Jane Street"
    sure: set[str] = set()  # a course's department, or a name in capitals: one title is enough
    for title in titles:
        code = ANY_COURSE.search(title)
        if code:
            sure.add(code.group(1).lower())
            spellings.setdefault(code.group(1).lower(), Counter())[code.group(1)] += 1
        words = WORD.findall(title)
        for i, w in enumerate(words):
            first = i == 0 and len(w) <= 6
            if w.lower() in DOING or not (first or ACRONYM.match(w)):
                continue
            spellings.setdefault(w.lower(), Counter())[w] += 1
            firsts[w.lower()] += first
            if first:
                seconds.setdefault(w.lower(), Counter())[words[1] if len(words) > 1 else ""] += 1
            if ACRONYM.match(w):
                sure.add(w.lower())

    def spelled(word: str) -> str:
        name = spellings[word].most_common(1)[0][0]
        after, n = (seconds.get(word) or Counter({"": 0})).most_common(1)[0]
        whole = word not in sure and after[:1].isupper() and after.lower() not in DOING and n == firsts[word]
        return f"{name} {after}" if whole else name

    return {word: spelled(word) for word in spellings if word in sure or firsts[word] >= 2}


def subject_of(title: str, known: dict[str, str]) -> str | None:
    """The subject a to-do is for, from `subjects`: its course code's department, else the first known word in it."""
    code = ANY_COURSE.search(title)
    if code and code.group(1).lower() in known:
        return known[code.group(1).lower()]
    for w in WORD.findall(title):
        if w.lower() in known and w.lower() not in DOING:
            return known[w.lower()]
    return None
