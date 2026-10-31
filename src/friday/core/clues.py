"""Which category an event is, from clues rather than word lists (31 Oct: "the way you classified was just based on
string? this seems like a very fragile way to do this"; of the ways offered, clues, with Claude asked only what they
leave unclear, for cost).

The clues are what an event shares with events whose category is known (yours, your always-words', Claude's): its
title's words and pairs of words, whether it names a course, the calendar it's on, the words of its place, an email's
sender. Each counts by how telling it is: rare and always in one category, much; common or mixed, little; a calendar
or a place less than a title's words. Two judges must agree before Friday is sure: the clues' weighted vote, and the
three most similar events. On your own events (31 Oct, each title hidden in turn) they were sure of two thirds and
wrong twice, both a professor's office hours your words already tell from a TA's; unsure, they guess, and a guess is
only offered. Pure.
"""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

COURSE = re.compile(r"\b[a-z]{2,5}\s?\d{4}\b")
WORD = re.compile(r"[a-z][a-z'&]+")
STOP = frozenset("the a an of for with and at in on to by from my your our".split())
TITLE = ("w:", "b:", "from:")  # what the event says of itself, and who sent it: these count fully
WEAK = 0.4  # a calendar, a place, a course: shared by events of many kinds

# Sure: the vote's winner has four fifths of it with enough evidence behind it, or the three most similar events agree
# and the nearest is close.
MARGIN, EVIDENCE = 0.8, 2.5
NEAR = 0.45  # tried on your events (31 Oct): 0.35 was sure of a class that was an advising drop-in
YOURS = 0.6  # this close to an event whose category you chose, it's that one's: what you choose spreads


def clues_of(
    title: str, calendar: str | None = None, location: str | None = None, sender: str | None = None
) -> frozenset[str]:
    """An event's clues: "w:salsa", "b:office hours", "course", "cal:…", "loc:willard", "from:janestreet.com"."""
    text = title.lower()
    words = [w for w in WORD.findall(COURSE.sub(" ", text)) if w not in STOP and len(w) > 1]
    out = {f"w:{w}" for w in words} | {f"b:{a} {b}" for a, b in zip(words, words[1:], strict=False)}
    if COURSE.search(text):
        out.add("course")
    if calendar:
        out.add(f"cal:{calendar.lower()}")
    if location:
        out |= {f"loc:{w}" for w in WORD.findall(location.lower()) if w not in STOP and len(w) > 2}
    if sender:
        out.add(f"from:{sender.lower()}")
    return frozenset(out)


@dataclass(frozen=True)
class Known:
    key: str  # the title as ratings key it (`rating_key`): one per title, however often it repeats
    title: str
    clues: frozenset[str]
    category: str
    by: str = "claude"  # who said: "you", "always" (your words), "claude"


@dataclass(frozen=True)
class Verdict:
    category: str | None
    sure: bool
    like: str | None = None  # the most similar event whose category is known, to say why
    like_by: str | None = None  # who said that one's category


class Clues:
    def __init__(self, known: Iterable[Known]) -> None:
        self.known: list[Known] = list(known)
        self.counts: dict[str, Counter[str]] = defaultdict(Counter)
        for k in self.known:
            for clue in k.clues:
                self.counts[clue][k.category] += 1
        self.df = Counter({clue: sum(found.values()) for clue, found in self.counts.items()})

    def judge(self, clues: frozenset[str], *, skip: str | None = None) -> Verdict:
        """The category these clues point to, and whether Friday is sure; `skip` leaves the event's own title out,
        so it isn't its own evidence."""
        own = next((k for k in self.known if k.key == skip), None)
        n_known = len(self.known) - (own is not None)
        if not clues or n_known <= 0:
            return Verdict(None, False)

        def counted(clue: str) -> Counter[str]:
            found = Counter(self.counts.get(clue, {}))
            if own is not None and clue in own.clues:
                found[own.category] -= 1
            return +found

        def weight(clue: str, n: int) -> float:
            return math.log((n_known + 1) / n) * (1.0 if clue.startswith(TITLE) else WEAK)

        votes: Counter[str] = Counter()
        evidence = 0.0
        for clue in clues:
            found = counted(clue)
            n = sum(found.values())
            if not n:
                continue
            w = weight(clue, n)
            for category, k in found.items():
                votes[category] += w * (k / n) ** 2
            if n >= 2 and found.most_common(1)[0][1] / n >= 0.9:
                evidence += w
        voted, sure_vote = None, False
        if votes:
            (voted, top), *rest = votes.most_common(2)
            second = rest[0][1] if rest else 0.0
            sure_vote = top / (top + second) >= MARGIN and evidence >= EVIDENCE

        near = self.nearest(clues, own, n_known)
        neighbours = Counter(k.category for _, k in near)
        nearest, sure_near = None, False
        if near:
            nearest, agreeing = neighbours.most_common(1)[0]
            sure_near = len(near) == 3 and agreeing == 3 and near[0][0] >= NEAR
        closest = near[0][1] if near and near[0][0] >= NEAR / 2 else None
        if closest is not None and closest.by == "you" and near[0][0] >= YOURS:
            return Verdict(closest.category, True, closest.title, "you")
        category = voted or nearest
        agree = voted is None or nearest is None or voted == nearest
        return Verdict(
            category,
            (sure_vote or sure_near) and agree,
            closest.title if closest else None,
            closest.by if closest else None,
        )

    def nearest(self, clues: frozenset[str], own: Known | None, n_known: int) -> list[tuple[float, Known]]:
        """The three events most like these clues, by the clues they share, each by how telling it is."""

        def weight(clue: str) -> float:
            n = self.df[clue] - (own is not None and clue in own.clues)
            return math.log((n_known + 1) / (n + 0.5)) * (1.0 if clue.startswith(TITLE) else WEAK)

        # a word no other event has says nothing of a category: it's left out of the likeness
        heard = frozenset(c for c in clues if self.df[c] - (own is not None and c in own.clues) > 0)
        scored = []
        for k in self.known:
            if k is own:
                continue
            shared = heard & k.clues
            if shared:
                scored.append((sum(map(weight, shared)) / sum(map(weight, heard | k.clues)), k))
        scored.sort(key=lambda s: (-s[0], s[1].title))
        return scored[:3]

    def examples(self, per: int = 3) -> dict[str, list[str]]:
        """A few of your events in each category, as Claude is shown what each has meant for you."""
        out: dict[str, list[str]] = defaultdict(list)
        for k in sorted(self.known, key=lambda k: k.title):
            if len(out[k.category]) < per:
                out[k.category].append(k.title)
        return dict(out)


def known_from(rows: Sequence[tuple[str, str, frozenset[str], str | None, str]]) -> list[Known]:
    """One Known per title key with a category, its clues those of every event with that title: rows of (key, title,
    clues, category or None, who said)."""
    clues: dict[str, set[str]] = defaultdict(set)
    first: dict[str, tuple[str, str | None, str]] = {}
    for key, title, found, category, by in rows:
        clues[key] |= found
        if key not in first or (first[key][1] is None and category):
            first[key] = (title, category, by)
    return [
        Known(key, title, frozenset(clues[key]), category, by)
        for key, (title, category, by) in first.items()
        if category
    ]
