"""One graph of what waits for what (23 Nov: "thing B depends on thing A and thing A doesn't have time (or so Friday
says) however thing B still gets scheduled"; your fix: "generate a dependency graph and then schedule things based
off of a topological ordering"). Whole system, a scratch Friday, Monday 19 October 2026 9am, a lab until 6pm, as
test_steps_wait_behind_stuck.py: a 5-hour thesis due tonight at 9 that's pointless late has no room.

Each case is a way B came to be planned though A had no time, or a page said so when the plan didn't: a wait on a
whole project (dropped), a wait across projects (the page found no title and said "No room"), a loop of waits, the
page's own guess of "No room" for a step the plan said nothing of, and placing a dependent before what it waits for."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, now="2026-10-19T09:00")
    app.do("add", title="Lab", when="fixed", start="2026-10-19T09:00", end="2026-10-19T18:00")
    return app


def add(app: App, **fields) -> int:  # noqa: ANN003
    return app.do("add", **fields)["item"]["id"]


def project_with_no_room(app: App, name: str = "LING Final Essay") -> dict[str, int]:
    """A project whose thesis step has no room before its due tonight, and a draft after it."""
    pid = add(app, title=name, preset="Project", due="2026-11-14T17:00", duration_min=60)
    thesis = add(app, title=f"{name} thesis", parent_id=pid, due="2026-10-19T21:00", duration_min=300, firmness="hard")
    app.do("edit", id=thesis, expires=True)
    draft = add(app, title=f"{name} draft", parent_id=pid, due="2026-10-22T17:00", duration_min=240, firmness="hard")
    return {"project": pid, "thesis": thesis, "draft": draft}


def planned(app: App, item: int) -> bool:
    plan = app.table("plans")[-1]["id"]
    return any(b["item_id"] == item and b["plan_id"] == plan for b in app.table("blocks"))


def page(app: App, project: int) -> dict:
    [found] = [p for p in app.do("projects") if p["item"]["id"] == project]
    return found


def test_what_waits_for_a_whole_project_waits_for_its_steps(app: App) -> None:
    """Reproduced 23 Nov: a wait on a project was dropped (a project has no time of its own), so B was planned at
    once though the project's thesis has no room."""
    ids = project_with_no_room(app)
    slides = add(app, title="Slides", due="2026-10-23T17:00", duration_min=60, firmness="hard")
    app.do("depend", item_id=slides, depends_on_id=ids["project"])
    replan(app.conn, app.now_utc)
    assert not planned(app, ids["draft"])  # behind the thesis, which keeps what fits before its due
    assert not planned(app, slides)  # waiting for the whole project, it waits behind the thesis too


def test_a_wait_on_a_project_whose_steps_fit_is_planned_after_its_last_step(app: App) -> None:
    pid = add(app, title="Poster", preset="Project", due="2026-10-23T17:00", duration_min=60)
    print_it = add(app, title="Print the poster", parent_id=pid, due="2026-10-21T17:00", duration_min=60,
                   firmness="hard")  # fmt: skip
    talk = add(app, title="Practice the talk", due="2026-10-23T17:00", duration_min=60, firmness="hard")
    app.do("depend", item_id=talk, depends_on_id=pid)
    replan(app.conn, app.now_utc)
    plan = app.table("plans")[-1]["id"]
    ends = [b["end_utc"] for b in app.table("blocks") if b["plan_id"] == plan and b["item_id"] == print_it]
    starts = [b["start_utc"] for b in app.table("blocks") if b["plan_id"] == plan and b["item_id"] == talk]
    assert ends and starts and min(starts) >= max(ends)


def test_a_step_waiting_across_projects_is_named_not_called_no_room(app: App) -> None:
    """The page looked for what a step waits for among its own project's steps only; found nowhere, it said "No room
    before its due" of a step that was only waiting."""
    first = project_with_no_room(app, "LING")
    second = add(app, title="HIST", preset="Project", due="2026-11-14T17:00", duration_min=60)
    outline = add(app, title="HIST outline", parent_id=second, due="2026-10-22T17:00", duration_min=60,
                  firmness="hard")  # fmt: skip
    app.do("depend", item_id=outline, depends_on_id=first["thesis"])
    replan(app.conn, app.now_utc)
    assert not planned(app, outline)
    assert page(app, second)["step_note"][str(outline)] == "Waits for “LING thesis”, which has no room before its due"
    assert page(app, first["project"])["step_note"][str(first["thesis"])] == "No room before its due"


def test_the_page_says_no_room_only_when_the_plan_does(app: App) -> None:
    """A step with no time that the plan says nothing of (here: not planned yet, added after the plan) isn't called
    "No room before its due": the page reads the plan, it doesn't guess."""
    ids = project_with_no_room(app)
    replan(app.conn, app.now_utc)
    later = add(
        app,
        title="LING Final Essay rubric",
        parent_id=ids["project"],
        due="2026-10-24T17:00",
        duration_min=60,
        firmness="hard",
    )  # fmt: skip — no replan yet
    notes = page(app, ids["project"])["step_note"]
    assert notes[str(ids["thesis"])] == "No room before its due"
    assert notes[str(ids["draft"])] == "Waits for “LING Final Essay thesis”, which has no room before its due"
    assert str(later) not in notes


def test_a_loop_of_waits_is_held_back_and_said(app: App) -> None:
    """A task waits for a project whose step waits for that task: none can be first."""
    pid = add(app, title="Grant", preset="Project", due="2026-11-14T17:00", duration_min=60)
    budget = add(app, title="Grant budget", parent_id=pid, due="2026-10-23T17:00", duration_min=60, firmness="hard")
    letter = add(app, title="Cover letter", due="2026-10-23T17:00", duration_min=60, firmness="hard")
    app.do("depend", item_id=letter, depends_on_id=pid)
    app.do("depend", item_id=budget, depends_on_id=letter)
    replan(app.conn, app.now_utc)
    assert not planned(app, letter) and not planned(app, budget)
    notices = app.do("status")["notices"]
    assert any("“Cover letter” and “Grant budget” wait for each other" in n or
               "“Grant budget” and “Cover letter” wait for each other" in n for n in notices)  # fmt: skip
    assert page(app, pid)["step_note"][str(budget)].startswith("Waits for “Cover letter”, which waits for it in turn")
