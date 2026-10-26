"""What if: changes staged together on a copy of the plan, the calendar as it would be and what they'd cost, never
kept until you keep them; then kept as one change that one Undo takes back."""

from pathlib import Path

import pytest

from friday.commands import whatif
from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app

WEEK = {"start": "2026-10-19T00:00", "end": "2026-10-26T00:00"}


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    whatif.BEFORE.clear()
    return new_app(tmp_path)


def busy(app: App, *spans: tuple[str, str]) -> None:
    for start, end in spans:
        app.do("add", title="Lab", when="fixed", start=start, end=end)


def tried(app: App, *changes: tuple[str, dict]) -> dict:
    return app.do("whatif", changes=[{"command": c, "input": i} for c, i in changes], **WEEK)


def coffee(start: str = "14:00", end: str = "17:00") -> tuple[str, dict]:
    return "add", {"title": "Coffee", "when": "fixed", "start": f"2026-10-19T{start}", "end": f"2026-10-19T{end}"}


def essay_day(app: App) -> int:
    """The essay can only be written from 2 to 6pm today."""
    busy(app, ("2026-10-19T09:00", "2026-10-19T14:00"), ("2026-10-19T18:00", "2026-10-19T23:30"))
    essay = app.do("add", title="Essay", duration_min=180, due="2026-10-19T23:00")["item"]["id"]
    replan(app.conn, app.now_utc)
    return essay


def test_nothing_is_kept_and_the_calendar_shows_the_change(app: App) -> None:
    essay_day(app)
    kept = (len(app.table("items")), len(app.table("command_log")), len(app.table("plans")))
    out = tried(app, coffee())
    assert (len(app.table("items")), len(app.table("command_log")), len(app.table("plans"))) == kept
    (change,) = out["changes"]
    assert change["said"] == "Add Coffee, Mon 2pm" and change["error"] is None and len(change["created"]) == 1
    assert change["late"] == ["Essay 2 h"]  # the quick check, this change alone
    assert out["verdict"] == "late" and [x["title"] for x in out["later"]] == ["Essay"]
    shown = {f["title"]: (f["start"], f["end"]) for f in out["plan"]["fixed"]}
    assert shown["Coffee"] == ("2026-10-19T14:00", "2026-10-19T17:00")
    essay = [b for b in out["plan"]["blocks"] if b["title"] == "Essay"]
    assert essay and not [b for b in essay if b["start"] < "2026-10-19T17:00" and b["end"] > "2026-10-19T14:00"]
    real = app.do("plan", **WEEK)
    assert "Coffee" not in {f["title"] for f in real["fixed"]}  # the real calendar is untouched


def test_each_change_says_what_it_does_on_top_of_those_before(app: App) -> None:
    essay_day(app)
    out = tried(app, ("add", {"text": "laundry ~1h"}), coffee("15:00", "17:00"))
    first, second = out["changes"]
    assert first["late"] == [] and second["late"] == ["Essay 1 h"]


def test_a_later_change_can_move_what_an_earlier_one_made(app: App) -> None:
    essay_day(app)
    moved = ("edit", {"id": whatif.placeholder(0, 0), "start": "2026-10-20T14:00", "end": "2026-10-20T17:00"})
    out = tried(app, coffee(), moved)
    assert [c["said"] for c in out["changes"]] == ["Add Coffee, Mon 2pm", "Move Coffee to Tue 2pm"]
    assert out["verdict"] == "fits" and not out["later"]  # tomorrow takes nothing from the essay
    shown = {f["title"]: f["start"] for f in out["plan"]["fixed"]}
    assert shown["Coffee"] == "2026-10-20T14:00"


def test_a_refused_change_says_why_and_the_others_still_apply(app: App) -> None:
    essay_day(app)
    out = tried(app, ("edit", {"id": 99999, "start": "2026-10-20T14:00"}), coffee())
    refused, added = out["changes"]
    assert refused["error"] and added["error"] is None and added["created"]
    gone = ("edit", {"id": whatif.placeholder(5, 0), "start": "2026-10-20T14:00"})
    assert "taken out" in tried(app, gone)["changes"][0]["error"]


def test_skipping_an_optional_event_and_a_rule_are_tried_too(app: App) -> None:
    gym = app.do("add", title="Gym", when="fixed", start="2026-10-19T14:00", end="2026-10-19T16:00")["item"]["id"]
    app.do("add", title="Essay", duration_min=120, due="2026-10-19T20:00")
    replan(app.conn, app.now_utc)
    out = tried(app, ("drop", {"id": gym}), ("rule_add", {"text": "No work after 5pm"}))
    assert [c["said"] for c in out["changes"]] == ["Delete Gym", "Rule: No work after 5pm"]
    assert "Gym" not in {f["title"] for f in out["plan"]["fixed"]}
    assert len(app.table("items")) == 2 and not [r for r in app.table("settings") if "5pm" in str(r)]


@pytest.mark.parametrize("firmness", ["hard", "soft"])
def test_work_pushed_later_or_past_its_due_is_said(app: App, firmness: str) -> None:
    # Dinner out from 6 to 9 takes the evening the reading had. Due tonight for certain, it's read after dinner and
    # Monday's work ends later; due softly, the plan lets it slip to the morning, which is said as late.
    busy(app, ("2026-10-19T09:00", "2026-10-19T18:00"))
    app.do("add", title="Reading", duration_min=120, due="2026-10-19T23:59", firmness=firmness)
    replan(app.conn, app.now_utc)
    out = tried(app, ("add", {"title": "Dinner out", "when": "fixed", "start": "2026-10-19T18:00",
                              "end": "2026-10-19T21:00"}))  # fmt: skip
    if firmness == "hard":
        (day,) = out["later_days"]
        assert day["date"] == "2026-10-19" and day["after"] > day["before"] and out["verdict"] == "tight"
        assert out["said"] == "Fits, with work ending later on Monday"
    else:
        assert out["verdict"] == "late" and out["slipped"] == ["Reading"] and not out["later"]
        assert out["said"] == "Would push Reading past its due"


def test_the_plan_without_the_changes_is_yours_or_planned_once_per_generation(
    app: App, monkeypatch: pytest.MonkeyPatch
) -> None:
    essay_day(app)
    solves: list[int] = []
    real = whatif.plan_snapshot
    monkeypatch.setattr(whatif, "plan_snapshot", lambda s, warm: (solves.append(1), real(s, warm))[1])
    tried(app, coffee())
    assert len(solves) == 1 and not whatif.BEFORE  # your saved plan is the plan without it: only the trial is planned
    app.do("add", text="email prof ~15m")  # a change since the saved plan: the plan without the changes is planned
    tried(app, coffee())
    (first,) = whatif.BEFORE.values()
    tried(app, coffee(), ("add", {"text": "laundry ~1h"}))
    assert len(solves) == 4 and next(iter(whatif.BEFORE.values())) is first  # and kept for the next try


def test_keep_makes_them_all_as_one_and_one_undo_takes_them_back(app: App) -> None:
    essay_day(app)
    items = len(app.table("items"))
    moved = ("edit", {"id": whatif.placeholder(0, 0), "start": "2026-10-20T14:00", "end": "2026-10-20T17:00"})
    changes = [coffee(), moved, ("rule_add", {"text": "No work after 10pm"})]
    out = app.do("whatif_keep", changes=[{"command": c, "input": i} for c, i in changes])
    assert out["message"] == "Kept 3 changes from What if"
    (made,) = [r for r in app.table("items") if r["title"] == "Coffee"]
    assert made["start_utc"] == "2026-10-20T18:00Z"  # 2pm EDT, moved by the second change
    assert any(r["name"].startswith("you:") for r in app.do("rules"))
    log = app.table("command_log")
    assert [r["command"] for r in log[-1:]] == ["whatif_keep"]
    app.do("undo", command_id=log[-1]["id"])
    assert len(app.table("items")) == items and not any(r["name"].startswith("you:") for r in app.do("rules"))


def test_keep_refuses_all_when_one_cant_be_made(app: App) -> None:
    items = len(app.table("items"))
    with pytest.raises(FieldError, match="change 2"):
        app.do("whatif_keep", changes=[{"command": "add", "input": {"text": "laundry ~1h"}},
                                       {"command": "edit", "input": {"id": 99999, "title": "x"}}])  # fmt: skip
    assert len(app.table("items")) == items
