"""The simulator (DESIGN §24.4): a term's events make sense, and a few days lived through the registry keep every
promise: no command fails and no hard deadline is missed."""

from datetime import date
from pathlib import Path

from friday.sim.generate import TermConfig, generate_term
from friday.sim.world import given_up, run_term


def test_a_term_has_classes_weekly_work_exams_a_project_and_a_life() -> None:
    term = generate_term(TermConfig(weeks=15), seed=0)
    commands = [e.command for e in term.events]
    titles = [e.payload.get("title", "") for e in term.events]
    assert commands.count("area_add") == 4 and commands.count("template_apply") == 1
    assert sum("lecture" in t for t in titles) == 4 and sum(" PS" in t for t in titles) == 4 * 14
    assert sum(t.endswith("prep") for t in titles) == 8
    assert {"lunch", "dinner", "gym", "guitar"} <= set(titles)
    assert term.events == sorted(term.events, key=lambda e: e.at)
    assert generate_term(TermConfig(weeks=15), seed=0) == term  # seeded


def test_a_shifted_chunk_counts_only_its_shift() -> None:
    before = [["2026-09-01T09:00Z", "2026-09-01T11:00Z"]]
    assert given_up(before, [["2026-09-01T09:30Z", "2026-09-01T11:30Z"]]) == 30
    assert given_up(before, before) == 0


def test_three_days_lived_through_the_registry(tmp_path: Path) -> None:
    metrics = run_term(tmp_path, TermConfig(start=date(2026, 8, 31), weeks=2), seed=1, days=3)
    assert metrics.errors == [] and metrics.hard_missed == 0
    assert metrics.days == 3 and len(metrics.plan_seconds) >= 3 and metrics.lived_minutes > 0
