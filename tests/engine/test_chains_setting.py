"""How many search chains a plan is made with (C90): performance cores − 1 unless FRIDAY_CHAINS says, and the tests
say 3 (the fewest an Apple-silicon Mac gets), so a plan in a test is the same on any machine. GitHub's 2-CPU machines
had run 1 chain and missed Priya's lunch, which no Mac would."""

from pathlib import Path

import pytest

import friday.engine.sampler as sampler
from friday.planner.build import scheduler_config
from friday.planner.service import replan
from friday.planner.store import load_settings
from tests.commands.helpers import new_app


def test_the_tests_plan_with_three_chains_whatever_the_machine() -> None:
    assert sampler.default_chains() == 3


@pytest.mark.parametrize(("cores", "chains"), [(12, 11), (4, 3), (2, 1), (1, 1)])
def test_without_the_setting_it_is_the_performance_cores_less_one(
    monkeypatch: pytest.MonkeyPatch, cores: int, chains: int
) -> None:
    monkeypatch.delenv("FRIDAY_CHAINS")
    monkeypatch.setattr(sampler, "performance_cores", lambda: cores)
    assert sampler.default_chains() == chains


@pytest.mark.parametrize(("said", "chains"), [("5", 5), (" 2 ", 2), ("0", 1), ("", 11)])
def test_the_setting_fixes_it_and_never_below_one(monkeypatch: pytest.MonkeyPatch, said: str, chains: int) -> None:
    monkeypatch.setenv("FRIDAY_CHAINS", said)
    monkeypatch.setattr(sampler, "performance_cores", lambda: 12)
    assert sampler.default_chains() == chains


def test_a_chain_count_in_your_settings_still_wins(tmp_path: Path) -> None:
    app = new_app(tmp_path)  # its engine settings say 2 chains
    assert scheduler_config(load_settings(app.conn)).sampler.chains == 2


def test_a_plan_says_it_was_made_with_the_setting_s_chains(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    app.do("settings_set", key="engine", value={"chains": None})
    app.do("add", title="Essay", preset="Assignment", due="2026-10-22T23:59", duration_min=120)
    replan(app.conn, app.now_utc)
    report = app.conn.execute("SELECT report FROM plans WHERE status = 'current'").fetchone()[0]
    assert '"chains": 3' in report
