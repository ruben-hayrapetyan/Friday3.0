"""Whether two titles name the same thing (27 Oct: "please scan for duplicates before proposing things to me. I have
gotten many requests to add duplicates"), for the inbox to set aside what you already have.

Read as words (abbreviations spelled out, "seven" and "VII" as 7, letters apart from digits), two titles are the same
thing when
- their courses don't differ: "CHEM 2090" and "CHEM 2091" are two courses; a title without one may be either;
- their numbers are the same: "PS 9" isn't "PS 10", and "Quiz" isn't "Quiz 3"; a code like "A4" counts as one;
- their lettered parts don't differ: "Part A" isn't "Part B"; "Write-Up 'B'" is "Write-Up B";
- and their words are one inside the other ("Core Values Impact" in "Core Values Impact (Required)"), or mostly the
  same ("AI Module Proof of Completion", "AI Literacy Proof of Completion"), once an initialism in one is spelled out
  by the other's words ("WWA" for "Weekly Writing Assignment", "dd" for "Design Doc").

Rooms ("(room 155)") and other numbers of three digits or more are where, not which: they must agree when both have
one, but a title with one may be the same as one without. Pure: words only, no database."""

import re
from dataclasses import dataclass

from friday.core.textnorm import TextRules, expand_abbreviations, normalize_numbers, plain_words

# Words that never tell two things apart, beyond your stopwords.
FILLER = frozenset("a an the of for on to and in at with my your by due".split())
COURSE_SUBJECT = re.compile(r"^[a-z]{2,6}$")
COURSE_NUMBER = re.compile(r"^\d{4}$")
WHERE_WORDS = frozenset({"room", "rm", "hall", "building", "floor", "fl", "flr", "level"})
ORDINAL = frozenset({"st", "nd", "rd", "th"})  # "3rd", split by plain_words into "3" and "rd"
# Words that say which course or what to do, not which thing: two readings for CS ("CS read Sorting", "CS read
# Recursive sorting algorithm") share them and are still two (27 Oct, your to-dos). They don't count towards a match.
PLAIN = frozenset(
    "read reading do finish work study studying review cs chem chemistry math psych psychology econ economics bio "
    "biology phys physics engrg engl english hist history orie ece mae cee info".split()
)


@dataclass(frozen=True)
class Reading:
    courses: frozenset[str]  # "chem 2090"
    numbers: frozenset[str]  # which one: "9", "a4" (one or two digits, or a letter and digits)
    places: frozenset[str]  # numbers of three digits or more that aren't a course: rooms
    letters: frozenset[str]  # lettered parts: "b" in "Part B"
    words: tuple[str, ...]  # the rest, in order, plurals made singular


QUOTED_LETTER = re.compile(r"""(?<![A-Za-z])['"‘’“”]([A-Za-z])['"‘’“”](?![A-Za-z])""")


def read_title(title: str, rules: TextRules) -> Reading:
    raw = normalize_numbers(expand_abbreviations(plain_words(title), rules.abbreviations), rules.numbered_words)
    quoted = {m.lower() for m in QUOTED_LETTER.findall(title)}
    stop = FILLER | rules.stopwords
    courses: set[str] = set()
    numbers: set[str] = set()
    places: set[str] = set()
    letters: set[str] = set()
    words: list[str] = []
    i = 0
    while i < len(raw):
        w, nxt = raw[i], raw[i + 1] if i + 1 < len(raw) else None
        prev = raw[i - 1] if i else None
        if nxt is not None and COURSE_SUBJECT.match(w) and COURSE_NUMBER.match(nxt) and w not in rules.numbered_words:
            courses.add(f"{w} {nxt}")
            i += 2
            continue
        if len(w) == 1 and w.isalpha() and nxt is not None and nxt.isdigit() and len(nxt) <= 2:
            numbers.add(f"{w}{nxt}")  # "A4", "Q3": a letter and its number, split by plain_words
            i += 2
            continue
        if w.isdigit() and nxt in ORDINAL and i + 2 < len(raw) and raw[i + 2] in WHERE_WORDS:
            # "(3rd floor, Appel)": where it is, not which one (29 Oct: the same table tennis practice from two
            # calendars, one saying its floor, was asked about every week)
            places.add(f"{w} {raw[i + 2]}")
            i += 3
            continue
        if w.isdigit():
            (numbers if len(w) <= 2 and prev not in WHERE_WORDS else places).add(w)  # "Room 12" is a place
        elif len(w) == 1 and w.isalpha():
            # A lone letter is a part ("Part B", "Write-Up 'B'"), but "a" and "i" only when quoted, after a word like
            # "part", or last: elsewhere they're an article or a pronoun ("a dentist appointment").
            article = w in ("a", "i") and w not in quoted and (prev is None or prev not in rules.numbered_words)
            if not (article and nxt is not None):
                letters.add(w)
        elif w not in stop and w not in WHERE_WORDS:
            words.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
        i += 1
    return Reading(frozenset(courses), frozenset(numbers), frozenset(places), frozenset(letters), tuple(words))


def spelled_out(words: tuple[str, ...], other: tuple[str, ...]) -> list[str]:
    """`words` with each initialism the other spells out replaced by its words: "wwa" by "weekly writing assignment"."""
    out: list[str] = []
    for w in words:
        found = None
        if 2 <= len(w) <= 6 and w.isalpha() and w not in other:
            for start in range(len(other) - len(w) + 1):
                run = other[start : start + len(w)]
                if "".join(x[0] for x in run) == w:
                    found = list(run)
                    break
        out.extend(found or [w])
    return out


def same_thing(a: str, b: str, rules: TextRules) -> bool:
    """Whether titles `a` and `b` name the same thing (see above)."""
    return same_reading(read_title(a, rules), read_title(b, rules))


def same_reading(x: Reading, y: Reading) -> bool:
    if x.courses and y.courses and not (x.courses & y.courses):
        return False
    if x.numbers != y.numbers:
        return False
    if x.places and y.places and not (x.places & y.places):
        return False
    if x.letters and y.letters and x.letters != y.letters:
        return False
    xs, ys = set(spelled_out(x.words, y.words)), set(spelled_out(y.words, x.words))
    if xs == ys and (xs or x.numbers or x.courses):
        return True  # the same words: "Read" and "read", "CS 2112 A4" and "A4 [CS 2112]"
    if not xs or not ys:
        return False
    # Words like "CS" and "read" still tell two things apart ("Chapter 4 reading", "Chapter 4 quiz"), but don't
    # count as what makes two the same.
    shorter, longer = sorted((xs, ys), key=len)
    if shorter <= longer:
        # One inside the other is the same with enough to go on: two telling words, a number, the course or the room.
        told = len(shorter - PLAIN) >= 2
        return told or bool(x.numbers) or bool(x.courses & y.courses) or bool(x.places & y.places)
    shared = xs & ys
    return len(shared - PLAIN) >= 2 and len(shared) / len(xs | ys) >= 0.6


def numbered(reading: Reading) -> bool:
    """Whether it says which one it is ("PS 9", "A4"): then the same one with another date is that one moved."""
    return bool(reading.numbers)
