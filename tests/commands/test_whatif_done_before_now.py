"""What if keeps what counts as done (19 Nov). Planned blocks that have passed count as done (prepare.py
`progress_minutes`), and What if planned the changes from the plan without them, which begins at now: with the passed
blocks gone, a lab writeup worked 8:30–10:30 was planned again, and a call added for 9pm "made Wednesday's work end
later", 12pm to 5pm. Wednesday 18 Nov 2026 in New York, the plan made at 7am, What if at 10:30."""

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from friday.commands import whatif
from friday.planner.snapshot import BlockRow
from tests.commands.helpers import App, new_app

DAY = {"start": "2026-11-18T04:00", "end": "2026-11-19T04:00"}
CALL = {"command": "add", "input": {"title": "call", "when": "fixed", "start": "2026-11-18T21:00",
                                    "end": "2026-11-18T21:30"}}  # fmt: skip


def spans(blocks: list[dict], title: str) -> list[tuple[str, str]]:
    return [(b["start"][11:16], b["end"][11:16]) for b in blocks if b["title"] == title]


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-11-18T07:00")
    app.do("add", title="lab writeup", duration_min=180, due="2026-11-18T18:00")
    app.do("add", title="practice piano", every="mon,tue,wed,thu,fri,sat,sun", duration_min=30)
    app.do("add", title="problem set", duration_min=240, due="2026-11-20T23:59")
    app.do("add", title="class", when="fixed", start="2026-11-18T13:00", end="2026-11-18T15:00")
    app.do("replan")
    assert spans(app.do("plan", **DAY)["blocks"], "lab writeup") == [("08:30", "11:30")]
    return app.at("2026-11-18T10:30")  # the first two hours of it have passed: done


def test_a_call_tonight_doesnt_plan_again_the_work_done_this_morning(app: App) -> None:
    out = app.do("whatif", changes=[CALL], **DAY)
    assert spans(out["plan"]["blocks"], "lab writeup") == [("08:30", "10:30"), ("10:30", "11:30")]  # not 3pm–5pm too
    assert out["later_days"] == []  # was Wednesday's work ending at 5pm, not 12pm
    assert (out["verdict"], out["said"], out["moved"]) == ("fits", "Fits: nothing gets later", 0)


def test_what_if_plans_from_the_passed_blocks_and_the_plan_without_the_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planned: list = []
    monkeypatch.setattr(whatif, "plan_snapshot", lambda snapshot, warm, stop=None: planned.append(snapshot) or "plan")
    now = 600
    after = NS(
        now_utc=now,
        plan_blocks=(
            BlockRow(1, 510, 630, False),  # under way: begun before now
            BlockRow(2, 420, 450, False),  # done this morning
            BlockRow(3, 700, 760, False),  # ahead in the saved plan: the plan without the changes says
        ),
    )
    # The plan without the changes: your saved one from now on (the block under way, which the passed blocks have
    # already) and where it moved the rest.
    was = NS(blocks=[NS(item_id=1, start_utc=510, end_utc=630, tentative=False),
                     NS(item_id=3, start_utc=720, end_utc=780, tentative=True)])  # fmt: skip
    monkeypatch.setattr(whatif, "replace", lambda snapshot, plan_blocks: NS(now_utc=now, plan_blocks=plan_blocks))
    assert whatif.planned_from(was, after) == "plan"
    assert planned[0].plan_blocks == (
        BlockRow(1, 510, 630, False),
        BlockRow(2, 420, 450, False),
        BlockRow(3, 720, 780, True),
    )
