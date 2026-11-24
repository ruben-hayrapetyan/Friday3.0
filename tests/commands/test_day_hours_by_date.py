"""A day's hours are one number everywhere (23 Nov, the agreement check, web/scripts/agreement-check.mjs: the week's
day header said "0.5 h over" of a day the Plan page's note, the day panel and the month counted at exactly its usual
10 h). The headers counted work over midnight on each side of it (15 Nov), the server all on the day it starts; now the
server counts it on each side too, and every page reads the server's. Monday 19 Oct 2026, 9am."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_work_over_midnight_counts_on_each_side_of_it(app: App) -> None:
    essay = app.do("add", title="Essay", duration_min=150)["item"]["id"]
    app.do("pin", id=essay, start="2026-10-19T23:00", kind="locked")
    app.do("replan")
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-21T00:00")
    [block] = [b for b in plan["blocks"] if b["item_id"] == essay]
    assert (block["start"], block["end"]) == ("2026-10-19T23:00", "2026-10-20T01:30")
    assert plan["day_hours"]["2026-10-19"] == pytest.approx(1.0)
    assert plan["day_hours"]["2026-10-20"] == pytest.approx(1.5)
