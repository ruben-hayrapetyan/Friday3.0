"""Projects, templates and the load ahead (DESIGN §6.4, §13.3)."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_a_template_makes_a_project_whose_steps_follow_each_other_each_aiming_at_its_share_of_the_time(
    app: App,
) -> None:
    project = app.do("template_apply", template="Essay", title="History essay", hours=10, due="2026-11-20T17:00")[
        "item"
    ]
    assert project["duration_min"] == 600
    kids = [i for i in app.do("items") if i["parent_id"] == project["id"]]
    assert [(k["title"], k["duration_min"], k["due"], k["firmness"]) for k in kids] == [
        ("Outline", 90, "2026-10-24T23:59", "soft"),  # 15% of the 32 days from now
        ("Draft", 300, "2026-11-09T23:59", "soft"),  # 65%
        ("Revise", 210, "2026-11-20T17:00", "hard"),
    ]
    depends = app.table("dependencies")
    assert [(d["item_id"], d["depends_on_id"]) for d in depends] == [
        (kids[1]["id"], kids[0]["id"]),
        (kids[2]["id"], kids[1]["id"]),
    ]


def test_a_project_rolls_up_its_children_and_is_on_track_once_planned(app: App) -> None:
    app.do("template_apply", template="Presentation", title="Talk", hours=5, due="2026-10-30T17:00")
    before = app.do("projects")[0]
    assert (before["remaining_min"], before["status"], len(before["children"])) == (300, "unplanned", 3)
    app.do("replan")
    after = app.do("projects")[0]
    assert after["status"] == "on_track" and after["planned_finish"] <= "2026-10-30T17:00"


def test_a_project_past_the_horizon_finishes_by_the_allocator(app: App) -> None:
    app.do("template_apply", template="Essay", title="Thesis", hours=40, due="2026-12-18T17:00")
    app.do("replan")
    project = app.do("projects")[0]
    assert project["status"] == "on_track" and project["planned_finish"] > "2026-10-26"


def test_a_template_can_be_saved_from_a_project(app: App) -> None:
    project = app.do("template_apply", template="Essay", title="Essay", hours=4, due="2026-11-02T17:00")["item"]
    app.do("template_save", name="Mine", project_id=project["id"])
    steps = app.do("settings")["templates"]["Mine"]
    assert [s["title"] for s in steps] == ["Outline", "Draft", "Revise"]
    assert sum(s["share"] for s in steps) == pytest.approx(1, abs=0.01)


def test_a_parent_must_exist_not_be_fixed_and_not_make_a_loop(app: App) -> None:
    outer = app.do("add", title="Outer", preset="Project", due="2026-11-20T17:00")["item"]
    inner = app.do("add", title="Inner", due="2026-11-20T17:00", parent_id=outer["id"], duration_min=60)["item"]
    with pytest.raises(FieldError, match="inside itself"):
        app.do("edit", id=outer["id"], parent_id=inner["id"])
    with pytest.raises(FieldError, match="isn't there any more"):
        app.do("add", title="Lost", parent_id=999)
    lecture = app.do("add", text="lecture at tue 10:00 for 1h")["item"]
    with pytest.raises(FieldError, match="set time"):
        app.do("add", title="Notes", parent_id=lecture["id"])


def test_load_counts_the_plan_then_the_forecast_week_by_week(app: App) -> None:
    app.do("add", text="essay due wed 17:00 ~2h")
    app.do("template_apply", template="Essay", title="Thesis", hours=40, due="2026-12-18T17:00")
    app.do("replan")
    weeks = app.do("load", weeks=12)
    assert weeks[0]["start"] == "2026-10-19" and not weeks[0]["forecast"] and weeks[-1]["forecast"]
    assert sum(w["hours"] for w in weeks) == pytest.approx(42, abs=1)
    assert all(w["capacity"] > 0 for w in weeks)
    assert [d["title"] for d in weeks[0]["due"]] == ["essay"]


def test_work_due_past_the_horizon_isnt_reported_late(app: App) -> None:
    app.do("template_apply", template="Essay", title="Thesis", hours=40, due="2026-12-18T17:00")
    app.do("replan")
    assert app.do("changes")["late_hours"] == {}
