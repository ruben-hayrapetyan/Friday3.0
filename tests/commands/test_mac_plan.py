"""Your plan as a calendar on this Mac (C113): off until you switch it on; on, the plan's blocks from now to the end of
the horizon, each with the key that keeps its event, and which plan they are, so the Mac app changes the calendar
only when the plan changed."""

from pathlib import Path

from friday.planner.service import replan
from tests.commands.helpers import new_app


def test_off_until_switched_on_then_the_plans_blocks(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    assert app.do("mac_plan") == {"wanted": False, "name": "Friday", "plan": None, "blocks": []}
    app.do("settings_set", key="mac_plan", value=True)
    assert app.do("mac_plan")["wanted"] is True and app.do("mac_plan")["blocks"] == []  # no plan yet
    app.do("add", text="essay due wed 17:00 ~3h")
    replan(app.conn, app.now_utc)
    out = app.do("mac_plan")
    assert out["plan"] is not None and out["blocks"], out
    first = out["blocks"][0]
    assert first["title"] == "essay" and first["start"].endswith("Z") and first["start"] < first["end"]
    assert len({b["key"] for b in out["blocks"]}) == len(out["blocks"])  # one event per block
