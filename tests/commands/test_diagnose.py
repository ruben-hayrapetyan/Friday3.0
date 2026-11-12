"""What diagnose reads back of a plan: its late work and the work it cut into pieces today."""

from pathlib import Path

from tests.commands.helpers import new_app


def test_diagnose_says_a_plans_late_work_and_work_cut_into_pieces_today(tmp_path: Path) -> None:
    app = new_app(tmp_path, horizon_days=3)
    app.do("add", title="Lab", when="fixed", start="2026-10-19T11:00", end="2026-10-19T12:00")
    app.do("add", title="Essay", duration_min=900, due="2026-10-19T23:00")
    app.do("replan")
    (plan,) = [h for h in app.at("2026-10-19T09:30").do("diagnose", hours=1) if h["kind"] == "plan"][-1:]
    assert "late: " in plan["summary"] and "Essay in " in plan["summary"] and "pieces today" in plan["summary"]
