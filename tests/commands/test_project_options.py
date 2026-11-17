"""A project's own options (commands/project_options.py): its pace through the work, and finishing it some days early as
a rule about it alone. Glass box: the `project` scope reaching a project and every step under it, the top project of a
step, the pacing read for planning. Black box through the commands: set, shown, in Rules with its words, taken away,
refused when it can't be, put away by archiving and back with unarchiving. The whole system: a project planned to end
days before its due, and front-loaded work planned before end-loaded work."""

from pathlib import Path

import pytest

from friday.core.items import FieldError, Item
from friday.core.time import parse_utc
from friday.engine.problem import EngineItem
from friday.engine.rules import Scope
from friday.planner.build import top_project
from friday.planner.ongoing import project_pacing
from friday.planner.service import replan
from tests.commands.helpers import App, new_app

MONDAY = "2026-11-09T09:00"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, now=MONDAY, horizon_days=14)


def essay(app: App, due: str = "2026-11-20T17:00") -> tuple[int, list[int]]:
    project = app.do("add", title="Essay", preset="Project", due=due, duration_min=360)["item"]["id"]
    steps = [app.do("add", title=t, parent_id=project, duration_min=m)["item"]["id"]
             for t, m in (("Outline", 60), ("Draft", 180), ("Revise", 120))]  # fmt: skip
    return project, steps


def blocks_of(app: App, ids: list[int]) -> list[tuple[int, int]]:
    return sorted(
        (parse_utc(b["start_utc"]), parse_utc(b["end_utc"])) for b in app.table("blocks") if b["item_id"] in ids
    )


# Glass box


def test_the_project_scope_reaches_the_project_and_its_steps_only() -> None:
    scope = Scope(project=["7"])
    assert scope.matches(EngineItem(key="a", project=7), None)  # type: ignore[arg-type]
    assert scope.matches(EngineItem(key="b", project=7, title="Outline"), None)  # type: ignore[arg-type]
    assert not scope.matches(EngineItem(key="c", project=8), None)  # type: ignore[arg-type]
    assert not scope.matches(EngineItem(key="d"), None)  # type: ignore[arg-type]
    assert Scope().matches(EngineItem(key="e", project=8), None)  # type: ignore[arg-type]  # no scope: everything


def test_a_steps_top_project_is_the_one_at_the_top() -> None:
    top = Item(id=1, title="Essay")
    step = Item(id=2, title="Draft", parent_id=1)
    sub = Item(id=3, title="Paragraph 1", parent_id=2)
    by_id = {1: top, 2: step, 3: sub}
    assert [top_project(i, by_id) for i in (top, step, sub)] == [1, 1, 1]
    assert top_project(Item(id=4, title="Lone", parent_id=99), by_id) == 4  # its parent isn't in the plan: itself


def test_only_a_pace_set_on_a_project_is_read_for_planning(app: App) -> None:
    project, _ = essay(app)
    assert project_pacing(app.conn) == {}
    app.do("project_set", id=project, pacing="front")
    assert project_pacing(app.conn) == {project: "front"}
    app.do("project_set", id=project, pacing="kind")
    assert project_pacing(app.conn) == {}


# Black box


def test_finishing_early_is_a_rule_about_this_project_in_rules(app: App) -> None:
    project, _ = essay(app)
    app.do("project_set", id=project, early_days=3)
    [rule] = [r for r in app.do("rules") if r["name"] == f"you:project:{project}:early"]
    assert (rule["sentence"], rule["source"], rule["strength"], rule["enabled"]) == (
        "Finish Essay 3 days early", "you", "Prefer", True,
    )  # fmt: skip
    assert app.do("project_options") == [{"id": project, "pacing": None, "early_days": 3.0}]
    app.do("project_set", id=project, early_days=0)
    assert not [r for r in app.do("rules") if r["name"].startswith("you:project:")]
    assert app.do("project_options") == []


def test_finishing_early_by_more_than_is_left_is_refused(app: App) -> None:
    project, _ = essay(app, due="2026-11-12T17:00")  # three days off
    with pytest.raises(FieldError, match="due in 3 days"):
        app.do("project_set", id=project, early_days=4)


def test_a_rule_switched_off_in_rules_no_longer_shows_on_the_project(app: App) -> None:
    project, _ = essay(app)
    app.do("project_set", id=project, early_days=2)
    app.do("rule_set", name=f"you:project:{project}:early", enabled=False)
    assert app.do("project_options") == []


def test_archiving_puts_its_rule_away_and_unarchiving_brings_it_back(app: App) -> None:
    project, _ = essay(app)
    app.do("project_set", id=project, early_days=2, pacing="back")
    app.do("project_archive", id=project)
    assert not [r for r in app.do("rules") if r["name"].startswith("you:project:")]
    app.do("project_unarchive", id=project)
    assert [r["sentence"] for r in app.do("rules") if r["name"].startswith("you:project:")] == [
        "Finish Essay 2 days early"
    ]
    assert app.do("project_options") == [{"id": project, "pacing": "back", "early_days": 2.0}]


def test_something_that_isnt_a_project_is_refused(app: App) -> None:
    task = app.do("add", title="Buy stamps", duration_min=15)["item"]["id"]
    with pytest.raises(FieldError, match="isn't a project"):
        app.do("project_set", id=task, early_days=1)


# The whole system, the planner


def two_projects_due_saturday(app: App, early: int | None) -> dict[str, list[int]]:
    """An essay and a report, 15 hours each in three parts, both due Saturday at 5pm: they compete for the week."""
    out = {}
    for name in ("Essay", "Report"):
        project = app.do("add", title=name, preset="Project", due="2026-11-14T17:00", duration_min=900)["item"]["id"]
        out[name] = [app.do("add", title=f"{name} part {i}", parent_id=project, duration_min=300)["item"]["id"]
                     for i in range(3)]  # fmt: skip
        if name == "Essay" and early:
            app.do("project_set", id=project, early_days=early)
    replan(app.conn, app.now_utc)
    return out


def test_a_project_finishing_early_ends_its_work_days_before_its_due(tmp_path: Path) -> None:
    # Where work competes for the week, the rule decides which is done first: the essay ends 3 days before Saturday
    # 5pm; without it, the day before.
    (tmp_path / "plain").mkdir()
    (tmp_path / "early").mkdir()
    plain, early = new_app(tmp_path / "plain", now=MONDAY), new_app(tmp_path / "early", now=MONDAY)
    due = parse_utc("2026-11-14T22:00Z")  # 5pm in New York
    steps = two_projects_due_saturday(early, 3)
    assert max(end for _, end in blocks_of(early, steps["Essay"])) <= due - 3 * 1440
    steps = two_projects_due_saturday(plain, None)
    assert max(end for _, end in blocks_of(plain, steps["Essay"])) > due - 3 * 1440


def test_front_loaded_work_puts_more_in_the_coming_weeks_than_work_left_toward_the_end(tmp_path: Path) -> None:
    # A project due in six weeks: its pace decides how much of it the next two weeks hold (weekly quotas). Its kind's
    # (a Project's) leaves it all for later; front-loaded puts the most of it first; toward the end, less.
    planned = {}
    for pace in ("kind", "front", "back"):
        (tmp_path / pace).mkdir()
        app = new_app(tmp_path / pace, now=MONDAY, horizon_days=14)
        project, steps = essay(app, due="2026-12-21T17:00")
        app.do("edit", id=steps[1], duration_min=600)  # 13 hours in all
        app.do("project_set", id=project, pacing=pace)
        replan(app.conn, app.now_utc)
        planned[pace] = blocks_of(app, steps)
    hours = {pace: sum(end - start for start, end in found) / 60 for pace, found in planned.items()}
    assert hours["front"] > hours["back"] > hours["kind"]
