"""Spreading and keeping together, said as rules (14 Nov: tasks aren't marked spread or clustered; a rule names the
work): what reads, what it reads as, and what it leaves for the AI or other rules."""

import pytest

from friday.core.rule_text import read, sentence, spec

SPREAD = [
    ("spread my essays over several days", "essays"),
    ("spread essay writing over 3+ days", "essays"),
    ("space out problem sets", "problem sets"),
    ("spread out my readings", "readings"),
    ("spread essays across the week", "essays"),
    ("I'd like to spread my lab reports over a few days", "lab reports"),
]
CLUSTER = [
    ("keep problem sets on few days", "problem sets"),
    ("keep my problem sets on as few days as possible", "problem sets"),
    ("don't spread essays out", "essays"),
    ("cluster readings", "readings"),
    ("do lab reports in one or two days", "lab reports"),
]
NEITHER = [
    "split essays",  # into sittings, not over days
    "never split up lab reports",  # one sitting
    "spread work over the week",  # all work evenly: the built-in rule
    "spread hard work evenly",
    "group all errands on one day",  # a batch of tasks, not each one's days
    "spread my gym sessions 2 days apart",  # a repeat's spacing
]


@pytest.mark.parametrize(("text", "subject"), SPREAD)
def test_spreading_reads(text: str, subject: str) -> None:
    found, _ = read(text)
    assert found is not None and (found.kind, found.subject) == ("spread", subject)
    assert sentence(found) == f"Spread {subject} over several days"


@pytest.mark.parametrize(("text", "subject"), CLUSTER)
def test_keeping_together_reads(text: str, subject: str) -> None:
    found, _ = read(text)
    assert found is not None and (found.kind, found.subject) == ("cluster", subject)
    assert sentence(found) == f"Keep {subject} on as few days as possible"


@pytest.mark.parametrize("text", NEITHER)
def test_what_isnt_spreading_a_named_kind_of_work(text: str) -> None:
    found, _ = read(text)
    assert found is None or found.kind not in ("spread", "cluster")


def test_the_rule_reaches_the_work_named_with_the_engines_measures() -> None:
    essays, _ = read("spread my essays over several days")
    rule = spec(essays, "Strongly", "you:x", areas=["CS 2110"], presets=["Reading", "Assignment"])  # type: ignore[arg-type]
    assert (rule["type"], rule["weight"], rule["scope"]) == ("spread", 9.0, {"title": ["essays", "essay"]})
    readings, _ = read("keep readings on few days")
    rule = spec(readings, "Prefer", "you:y", areas=[], presets=["Reading"])  # type: ignore[arg-type]
    assert (rule["type"], rule["scope"], rule["params"]) == ("cluster", {"preset": "Reading"}, {"per_day": 2.0})
    course, _ = read("spread cs 2110 over several days")
    assert spec(course, "Prefer", "you:z", areas=["CS 2110"], presets=[])["scope"] == {"subject": ["CS 2110"]}  # type: ignore[arg-type]
