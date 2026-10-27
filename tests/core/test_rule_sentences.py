"""510 rule sentences a student might type, each labelled with what the writer means (tests/core/data, 27 Oct). Each
reads as it means or goes to Claude: none is read as another rule, half of two rules, or a rule made of something to
add or of something Friday can't do. Which go to Claude is reported, not held: the grammar may learn more of them."""

from collections import Counter
from typing import Any

import pytest

from friday.core.rule_text import DAYS, Reading, read
from tests.core.data.rule_sentences import C

# Kinds whose subject the reading fixes ("optional", "around"…): the label leaves it out.
FIXED_SUBJECT = {"optional", "ahead", "around", "night_before", "meals_kept", "meals_learned", "fit_gaps",
                 "runs_while_working", "deadlines", "pace"}  # fmt: skip
# Read as a rule though labelled otherwise, and right to be: a bedtime is the end of the day's work (rule_text's
# SAID_AS), and a task named for a day is that task on that day.
ALLOWED = {"lights out by 12:30", "in bed by 11:30 on school nights", "call mom on sundays"}


def words(s: Any) -> set[str]:
    return {w.rstrip("s") for w in str(s).lower().split() if w not in ("the", "my", "a")}


def same_days(want: list[str] | None, got: tuple[str, ...] | None, rel_want: str | None, rel_got: str | None) -> bool:
    w, g = set(want or DAYS), set(got or DAYS)
    if {rel_want, rel_got} == {"on", "not_on"}:
        return w == set(DAYS) - g  # "on X" is "not on" the others
    return w == g


def differences(want: dict[str, Any], r: Reading) -> list[str]:
    if r.kind != want["kind"]:
        return [f"kind {r.kind}"]
    bad = []
    if "subject" in want and want["kind"] not in FIXED_SUBJECT and r.subject != want["subject"]:
        bad.append(f"subject {r.subject!r}")
    for key in ("rel", "at", "until"):
        if key in want and want[key] != getattr(r, key) and not (key == "rel" and r.kind == "days"):
            bad.append(f"{key} {getattr(r, key)!r}")
    if (r.kind == "days" or "days" in want or r.days) and not same_days(
        want.get("days"), r.days, want.get("rel"), r.rel
    ):
        bad.append(f"days {r.days}")
    if "amount" in want and (r.amount is None or abs(r.amount - want["amount"]) > 0.02):
        bad.append(f"amount {r.amount}")
    for key in ("before_min", "after_min"):
        if key in want and (getattr(r, key) or 0) != want[key]:
            bad.append(f"{key} {getattr(r, key)}")
    for key in ("events", "event"):
        named = want.get(key)
        got = (r.events or ()) if key == "events" else (r.event,)
        for event in named if isinstance(named, list) else [named] if named else []:
            if not any(g and (words(event) <= words(g) or words(g) <= words(event)) for g in got):
                bad.append(f"{key} {got}")
    if "paces" in want and sorted(map(tuple, want["paces"])) != sorted(map(tuple, r.paces or ())):
        bad.append(f"paces {r.paces}")
    return bad


@pytest.mark.parametrize(("topic", "text", "want"), C, ids=[t for _, t, _ in C])
def test_a_sentence_reads_as_it_means_or_goes_to_claude(topic: str, text: str, want: Any) -> None:
    reading, _ = read(text)
    if reading is None:
        return  # Claude's to read
    if isinstance(want, dict):
        assert not differences(want, reading), (want, reading)
    else:
        assert text in ALLOWED, f"read as a rule, but it's {want}: {reading}"


def test_most_rules_are_read_without_claude() -> None:
    read_right = Counter(isinstance(want, dict) and read(text)[0] is not None for _, text, want in C)
    rules = sum(isinstance(want, dict) for _, _, want in C)
    assert read_right[True] / rules >= 0.65  # 202 of 306 on 27 Oct
