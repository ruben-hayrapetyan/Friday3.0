"""Insights: estimates against actual time by kind, and when work gets done."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_insights_compare_estimates_by_kind_and_map_working_hours(app: App) -> None:
    for title, worked in (("PS1", ("09:00", "11:00")), ("PS2", ("09:00", "10:00"))):
        item = app.do("add", title=title, preset="Assignment", duration_min=60, due="2026-10-23T17:00")["item"]["id"]
        app.do("log", id=item, start=f"2026-10-19T{worked[0]}", end=f"2026-10-19T{worked[1]}")
        app.at("2026-10-19T12:00").do("done", id=item)
    out = app.do("insights", weeks=4)
    (kind,) = out["by_kind"]
    assert (kind["kind"], kind["n"], kind["low"], kind["high"]) == ("Assignment", 2, 1.0, 2.0)
    assert out["heat"][0][1] == 120 and out["heat"][0][2] == 60  # Monday 09:00 and 10:00
    assert out["best_hours"] == "You get the most done on Mondays, 9am to 11am."


def test_a_projects_steps_keep_the_order_you_give_them(app: App) -> None:
    project = app.do("template_apply", template="Essay", title="History essay", hours=6)["item"]["id"]
    steps = [c["id"] for c in app.do("projects")[0]["children"]]
    app.do("reorder", parent_id=project, ids=list(reversed(steps)))
    assert [c["id"] for c in app.do("projects")[0]["children"]] == list(reversed(steps))
