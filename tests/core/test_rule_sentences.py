"""Rule sentences a student might type, each labelled with what the writer means (tests/core/data): 510 from 27 Oct,
1,057 more for wider coverage (28 Oct: "the barebones rules parsing [should be] much more comprehensive instead of
having to ask claude for everything"), 413 written as a held-out set, 327 more as a final one, and 750 written blind
by three writers on 8 Nov (rule_nov8: read untouched, 362 of its 570 rules were right and 48 misread, among them free
time read as the only hours for work and "start working by 8:30" as stopping at 8:30pm; all 48 fixed), then 400
more held out (rule_nov8_heldout: measured once, 79% right where the reader of that morning read 67%). Each reads as it
means or goes to Claude: none is read as another rule, half of two rules, or a rule made of something to add or of
something Friday can't do. How many are read without Claude is held per set.

The grammar was tuned on the first three. The final set, measured once before anything was changed for it, read 64 of
its 263 rules right and misread 32 (the grammar of 27 Oct morning: 16 right, 49 misread); only its misreads were then
fixed. That is the honest measure of wording the grammar hasn't seen: about a quarter read, the rest to Claude."""

import contextlib
import importlib
import re
from typing import Any

import pytest

from friday.core.rule_text import DAYS, Reading, read

SETS = ("rule_sentences", "rule_wordings", "rule_heldout", "rule_final", "rule_nov8", "rule_nov8_heldout")
CORPORA = {}
for name in SETS:
    with contextlib.suppress(ModuleNotFoundError):  # the held-out set may not be written yet
        CORPORA[name] = importlib.import_module(f"tests.core.data.{name}").C
ALL = [(name, topic, text, want) for name, c in CORPORA.items() for topic, text, want in c]

# Kinds whose subject the reading fixes ("optional", "around"…): the label leaves it out.
FIXED_SUBJECT = {"optional", "ahead", "around", "night_before", "meals_kept", "meals_learned", "fit_gaps",
                 "runs_while_working", "deadlines", "pace"}  # fmt: skip
# Read as a rule though labelled otherwise, and right to be: a bedtime is the end of the day's work (rule_text's
# SAID_AS), and a task named for a day is that task on that day.
ALLOWED = {"lights out by 12:30", "in bed by 11:30 on school nights", "call mom on sundays"}
BEDTIME = r"^(?:i'?m (?:usually )?)?(?:in bed|lights out|bed|asleep)\b"
# The share of each set's rules read without Claude, at least: what the grammar reads now, so it doesn't slip back.
READ = {
    "rule_sentences": 0.99,
    "rule_wordings": 0.99,
    "rule_heldout": 0.93,
    "rule_final": 0.62,
    "rule_nov8": 0.87,
    "rule_nov8_heldout": 0.83,
}


def words(s: Any) -> set[str]:
    said = str(s).lower().replace("-", " ").split()
    return {re.sub(r"ies$", "y", w).rstrip("s") for w in said if w not in ("the", "my", "a")}


def same_days(want: list[str] | None, got: tuple[str, ...] | None, rel_want: str | None, rel_got: str | None) -> bool:
    w, g = set(want or DAYS), set(got or DAYS)
    if {rel_want, rel_got} == {"on", "not_on"}:
        return w == set(DAYS) - g  # "on X" is "not on" the others
    return w == g


def differences(want: dict[str, Any], r: Reading) -> list[str]:
    if r.kind != want["kind"]:
        return [f"kind {r.kind}"]
    bad = []
    # "pset" and "psets" are one subject: a rule's scope matches either (rule_text.scope_of).
    one = lambda x: x.replace("-", " ").rstrip("s")  # noqa: E731  ("take-home exams", "take home exam")
    if "subject" in want and want["kind"] not in FIXED_SUBJECT and one(r.subject) != one(want["subject"]):
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


@pytest.mark.parametrize(("corpus", "topic", "text", "want"), ALL, ids=[f"{n}:{t}" for n, _, t, _ in ALL])
def test_a_sentence_reads_as_it_means_or_goes_to_claude(corpus: str, topic: str, text: str, want: Any) -> None:
    reading, _ = read(text)
    if reading is None:
        return  # Claude's to read
    if isinstance(want, dict):
        assert not differences(want, reading), (want, reading)
    elif want == "set:sleep" and re.search(BEDTIME, text.lower()) and reading.kind == "window":
        pass  # a bedtime read as the end of the day's work
    else:
        assert text in ALLOWED, f"read as a rule, but it's {want}: {reading}"


@pytest.mark.parametrize("corpus", list(CORPORA))
def test_nearly_every_rule_is_read_without_claude(corpus: str) -> None:
    rules = [(text, want) for _, text, want in CORPORA[corpus] if isinstance(want, dict)]
    read_right = sum(1 for text, want in rules if (r := read(text)[0]) is not None and not differences(want, r))
    assert read_right / len(rules) >= READ[corpus], f"{read_right} of {len(rules)}"
