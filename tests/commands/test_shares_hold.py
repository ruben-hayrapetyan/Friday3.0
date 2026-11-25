"""A week's share of work due past the plan's weeks holds from one plan to the next while the amount stays within a
quarter hour of it (24 Nov, the user's Laundry: re-rounded each tick, shares moved a quarter hour each way between
ticks with nothing changed, and Laundry turned late and back). The plan saves its shares; the next plan holds them."""

import json
from pathlib import Path

import pytest

import friday.engine.allocator as allocator
from friday.planner.service import replan
from friday.planner.store import current_plan
from tests.commands.helpers import new_app


def shares(app) -> dict[str, dict[str, int]]:  # noqa: ANN001
    return json.loads(current_plan(app.conn)["report"])["quotas"]


def test_the_last_plans_shares_reach_the_next_plans_rounding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = new_app(tmp_path)  # Monday 19 Oct, a 7-day plan
    thesis = app.do("add", title="Thesis chapter", duration_min=30 * 60, due="2026-10-28T17:00")["item"]["id"]
    replan(app.conn, app.now_utc)
    first = shares(app)[str(thesis)]
    assert first, "a thesis due just past the plan's week gets a share of this one"
    seen: list[tuple[float, int | None]] = []
    real = allocator.held
    monkeypatch.setattr(allocator, "held", lambda amount, last: seen.append((amount, last)) or real(amount, last))
    replan(app.conn, app.now_utc)
    assert [last for _, last in seen] == list(first.values())  # each week's share, from the plan before
    assert shares(app)[str(thesis)] == first
