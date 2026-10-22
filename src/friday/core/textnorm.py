"""Title normalization and similarity (DESIGN §6.6)."""

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

NUMBER_WORDS = {
    word: str(i)
    for i, word in enumerate(
        "_ one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen twenty".split()
    )
    if i > 0
}
ROMAN_NUMERALS = {
    word: str(i)
    for i, word in enumerate("_ i ii iii iv v vi vii viii ix x xi xii xiii xiv xv xvi xvii xviii xix xx".split())
    if i > 0
}
LETTER_DIGIT_BOUNDARY = re.compile(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])")
NOT_LETTER_OR_DIGIT = re.compile(r"[\W_]+")


@dataclass(frozen=True)
class TextRules:
    abbreviations: dict[str, str] = field(default_factory=dict)
    numbered_words: frozenset[str] = frozenset()
    stopwords: frozenset[str] = frozenset()


def plain_words(text: str) -> list[str]:
    """Steps 1–3: fold case and accents, split letters from digits, keep only letters and digits."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    without_accents = "".join(c for c in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(c))
    spaced = LETTER_DIGIT_BOUNDARY.sub(" ", without_accents)
    return NOT_LETTER_OR_DIGIT.sub(" ", spaced).split()


def remove_sequence(words: list[str], sequence: list[str]) -> list[str]:
    n = len(sequence)
    for i in range(len(words) - n + 1):
        if n and words[i : i + n] == sequence:
            return words[:i] + words[i + n :]
    return words


def expand_abbreviations(words: list[str], abbreviations: dict[str, str]) -> list[str]:
    return [part for word in words for part in abbreviations.get(word, word).split()]


def normalize_numbers(words: list[str], numbered_words: frozenset[str]) -> list[str]:
    out: list[str] = []
    for word in words:
        if word in NUMBER_WORDS:
            word = NUMBER_WORDS[word]
        elif word in ROMAN_NUMERALS and out and out[-1] in numbered_words:
            # Only right after a word like "part", so the "i" in "what i learned" stays a word.
            word = ROMAN_NUMERALS[word]
        elif word.isdigit():
            word = str(int(word))
        out.append(word)
    return out


def norm(title: str, rules: TextRules, area: str | None = None) -> list[str]:
    words = plain_words(title)
    if area:
        words = remove_sequence(words, plain_words(area))
    words = expand_abbreviations(words, rules.abbreviations)
    words = normalize_numbers(words, rules.numbered_words)
    return [w for w in words if w not in rules.stopwords]


def identity_text(words: list[str]) -> str:
    return " ".join(words)


def type_text(words: list[str]) -> str:
    return " ".join(w for w in words if not w.isdigit())


def similarity(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a, b) / 100


COURSE_CODE = re.compile(r"^\s*([A-Z]{2,5}) ?(\d{4})\b")


def course_tag(title: str, tags: list[str]) -> str | None:
    """The tag a course's title names ("CS 2110 A5" → "CS 2110"): an existing tag spelled any way (#cs2110), else
    the code itself; None when the title doesn't start with one."""
    found = COURSE_CODE.match(title)
    if found is None:
        return None
    code = f"{found[1]} {found[2]}"
    wanted = "".join(plain_words(code))
    return next((t for t in tags if "".join(plain_words(t)) == wanted), code)
