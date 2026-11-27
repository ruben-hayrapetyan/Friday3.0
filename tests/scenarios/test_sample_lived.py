"""Alex's lived-in sample (sim/history.py), as the demo and the browser tests open it."""

import os
from datetime import datetime
from pathlib import Path

import pytest

from friday.commands.registry import run
from friday.core.time import to_utc
from friday.sim.history import ZONE, open_lived_in
from friday.sim.students import ALEX


@pytest.fixture(autouse=True)
def steady(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRIDAY_CHAINS", os.environ.get("FRIDAY_CHAINS", "3"))
    monkeypatch.setenv("FRIDAY_FIXED_EFFORT", "1")


def test_the_inbox_always_has_a_day_to_compare(tmp_path: Path) -> None:
    """27 Nov: lived up to Friday 27 Nov at 2pm, Alex's answers looked too noisy for Friday to ask more, so the sample
    had no day to compare and the browser tests on the Inbox's questions failed on that date whatever the code."""
    now = to_utc(datetime.fromisoformat("2026-11-27T14:00"), ZONE.key)
    conn = open_lived_in(tmp_path / "friday.db", ALEX, now)
    asked = run(conn, "questions", {}, now_utc=now).result
    assert len(asked["comparisons"]) >= 1
