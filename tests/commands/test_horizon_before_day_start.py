"""KNOWN FAILING (24 Nov, found running tests/system at FRIDAY_TEST_HOUR=3; src/ not changed): just before the 4am day
start the plan reaches a whole day less far ahead. The grid is `horizon_days` planning days from the planning day now
(core/time.make_grid), and before 4am that day is yesterday's last hour or so: at 3:30am a 7-day horizon ends six days
and half an hour on, at 4:30am seven days on. Work in the day between goes unplanned at 3:30 and is planned at 4:30
with nothing changed, and the plan around it shifts too (the breaks test: a 15-minute hard-due "Pay rent" on a break
day left late at 3am, on time from 4am, since what didn't fit before the horizon's end was squeezed in instead)."""

from pathlib import Path

import pytest

from friday.core.time import parse_utc
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


def report_blocks(app: App) -> list[tuple[str, str]]:
    ids = {r["id"] for r in app.table("items") if r["title"] == "Report"}
    return [(b["start_utc"], b["end_utc"]) for b in app.table("blocks") if b["item_id"] in ids]


def planned_at(tmp_path: Path, now: str) -> App:
    """A 7-day horizon; an hour of work that can only be done on Monday the 26th, 8am to 8pm."""
    app = new_app(tmp_path, now=now, horizon_days=7)
    app.do("add", title="Report", duration_min=60, firmness="hard", release="2026-10-26T08:00", due="2026-10-26T20:00")
    replan(app.conn, app.now_utc)
    return app


def test_at_4_30am_work_six_days_on_is_planned(tmp_path: Path) -> None:
    app = planned_at(tmp_path, "2026-10-20T04:30")
    assert sum(parse_utc(e) - parse_utc(s) for s, e in report_blocks(app)) == 60


@pytest.mark.xfail(
    strict=True, reason="before the 4am day start the plan reaches a day less far: waiting on the user's choice"
)
def test_at_3_30am_the_same_work_is_planned_too(tmp_path: Path) -> None:
    # fails: at 3:30am the grid ends at 4am on the 26th (seven planning days from Monday the 19th's last half hour),
    # so the Report, six days and a few hours on, isn't planned until the clock passes 4am
    app = planned_at(tmp_path, "2026-10-20T03:30")
    assert sum(parse_utc(e) - parse_utc(s) for s, e in report_blocks(app)) == 60
