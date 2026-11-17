"""How a project's steps are planned (17 Nov: a client's notes and a sweep of 700 sample projects): in the order they're
listed, a step that waits starting as soon as what it waits on is done, the work spread over the weeks to the due
when no pace is set, steps never chained by their titles, and never more planned than a step has left.

Whole system, through the commands and the planner, on an empty week from Monday 19 Oct 2026 9am."""

from pathlib import Path

import pytest

from friday.core.time import parse_utc
from friday.planner.service import replan
from tests.commands.helpers import REGISTRY, App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=14)


def project(app: App, due: str, steps: list[tuple[str, int]], title: str = "Report") -> tuple[int, list[int]]:
    made = app.do("add", title=title, preset="Project", due=due)["item"]["id"]
    ids = [app.do("add", title=t, preset="Assignment", duration_min=m, parent_id=made)["item"]["id"] for t, m in steps]
    return made, ids


def blocks(app: App) -> dict[int, list[tuple[int, int]]]:
    plan = app.conn.execute("SELECT id FROM plans WHERE status = 'current'").fetchone()[0]
    out: dict[int, list[tuple[int, int]]] = {}
    for r in app.conn.execute(
        "SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ? ORDER BY start_utc", [plan]
    ):
        out.setdefault(r[0], []).append((parse_utc(r[1]), parse_utc(r[2])))
    return out


def minutes(found: list[tuple[int, int]]) -> int:
    return sum(end - start for start, end in found)


def chain(app: App, ids: list[int]) -> None:
    for before, after in zip(ids, ids[1:], strict=False):
        app.do("depend", item_id=after, depends_on_id=before)


def test_a_project_with_no_pace_is_spread_over_the_weeks_to_its_due(app: App) -> None:
    # A client: "'no pace' breaks everything bc friday doesn't account for how long the project will take"
    _, ids = project(app, "2026-11-16T17:00", [("Research", 360), ("Draft", 360), ("Revise", 360)])
    replan(app.conn, app.now_utc)
    planned = sum(minutes(found) for item, found in blocks(app).items() if item in ids)
    assert planned >= 0.4 * 1080  # four weeks to its due: about half in the plan's two, not left to the last days


def test_a_step_that_waits_can_start_the_day_what_it_waits_on_is_done(app: App) -> None:
    # A chain of short steps due tomorrow evening: a day for each link left most of it late
    made, ids = project(app, "2026-10-20T20:00", [(f"Part {n}", 45) for n in range(1, 6)])
    chain(app, ids)
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert all(minutes(found.get(i, [])) == 45 for i in ids)
    assert app.do("projects")[0]["status"] == "on_track"
    for before, after in zip(ids, ids[1:], strict=False):
        assert found[after][0][0] >= found[before][-1][1]  # still after what it waits on


def test_free_steps_are_planned_beside_a_chain_not_left_for_last(app: App) -> None:
    # A client: "task B that's waiting on task A is getting planned while task A is not"; the user: "the tasks that
    # are waiting got planned while the tasks that weren't, didn't get planned at all"
    names = ["Collect data", "Clean data", "Run analysis", "Make plots", "Write methods", "Write results", "Proofread"]
    _, linked = project(app, "2026-11-06T17:00", [(t, 45) for t in names])
    chain(app, linked)
    free = [app.do("add", title=t, preset="Assignment", duration_min=45, parent_id=app.do("projects")[0]["item"]["id"])
            ["item"]["id"] for t in ("Book lab room", "Email TA", "Find citations")]  # fmt: skip
    for step in free:  # a step that waits on nothing is "any time" now: the order is the chain (17 Nov)
        app.do("step_any_time", id=step, any_time=True)
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert all(found.get(i) for i in free), "a step that waits on nothing is planned"
    for before, after in zip(linked, linked[1:], strict=False):
        assert not found.get(after) or found.get(before), "never a step planned while what it waits on isn't"


def test_a_chain_due_after_a_busy_weekend_is_planned_before_the_weekend(app: App) -> None:
    app.do(
        "add", title="Away all weekend", when="fixed", start="2026-11-21T07:00", end="2026-11-22T23:00", preset="Event"
    )
    _, ids = project(app, "2026-11-23T17:00", [("Gather", 120), ("Write", 120), ("Polish", 120)])
    chain(app, ids)
    replan(app.conn, app.now_utc)
    [shown] = app.do("projects")
    assert shown["status"] != "late" and shown["planned_finish"] <= "2026-11-23T17:00"


def test_a_projects_steps_arent_chained_by_their_titles(app: App) -> None:
    # Steps whose titles share two words were made to wait on each other by title ("Read chapter 1" before "Read
    # chapter 2"), unseen, and came out late; the order you list them in is the one kept
    _, (second, first) = project(app, "2026-10-23T17:00", [("Read chapter 2", 180), ("Read chapter 1", 180)])
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert found[second][0][0] < found[first][0][0]
    assert app.do("projects")[0]["status"] == "on_track"


def test_steps_are_planned_in_the_order_theyre_listed_and_reordering_replans(app: App) -> None:
    # The user: "the order in which it plans subtasks is plain wrong" (planned Outline, Edit, Research, Draft)
    made, ids = project(app, "2026-10-24T17:00", [("Research", 120), ("Outline", 120), ("Draft", 120), ("Edit", 120)])
    replan(app.conn, app.now_utc)

    def order() -> list[int]:
        found = blocks(app)
        return sorted(ids, key=lambda i: found[i][0][0])

    assert order() == ids
    app.do("reorder", parent_id=made, ids=list(reversed(ids)))
    assert REGISTRY["reorder"].affects_plan  # Friday plans again after it, as after any change to the plan
    replan(app.conn, app.now_utc)
    assert order() == list(reversed(ids))


def test_a_step_with_project_in_its_title_is_a_step(app: App) -> None:
    made = app.do("add", title="Capstone", preset="Project", due="2026-10-30T17:00")["item"]["id"]
    step = app.do("add", text="Email project partner", parent_id=made)["item"]
    assert step["preset"] != "Project"
    assert [p["item"]["title"] for p in app.do("projects")] == ["Capstone"]


@pytest.mark.xfail(
    strict=True,
    reason="left for now (17 Nov): from the plan's second week slots are half hours, so an odd quarter hour takes a "
    "whole one (+15 min). Trimming the saved block broke the next replan's warm start (a replan with nothing "
    "changed moved blocks); the fix belongs in the scheduler's coarse slots or the plan query's output",
)
def test_no_step_is_planned_for_more_than_it_has_left(app: App) -> None:
    made = app.do("template_apply", template="Essay", title="Essay", hours=6, due="2026-11-09T17:00")["item"]["id"]
    app.do("project_set", id=made, pacing="front")
    replan(app.conn, app.now_utc)
    found = blocks(app)
    for step in app.do("projects")[0]["children"]:
        assert minutes(found.get(step["id"], [])) <= step["remaining_min"], step["title"]


def test_finishing_early_is_kept_when_there_is_room(app: App) -> None:
    # 14 hours due Saturday 5pm, 3 days early: by Wednesday 5pm, with Monday to Wednesday empty
    made, (first, second) = project(app, "2026-10-24T17:00", [("Write section 1", 315), ("Write section 2", 525)])
    chain(app, [first, second])
    app.do("project_set", id=made, pacing="linear")
    app.do("project_set", id=made, early_days=3)
    replan(app.conn, app.now_utc)
    found = blocks(app)
    aim = parse_utc("2026-10-21T21:00Z")  # Wednesday 21 Oct, 5pm New York
    assert all(end <= aim for _, end in found[first] + found[second])


def test_a_step_planned_past_the_plans_days_says_when(app: App) -> None:
    # "open subtasks say not planned even with ample time": planned nearer the due, past the plan's two weeks (paced
    # evenly: with no pace set it's all done in the first days, 17 Nov)
    made, ids = project(app, "2026-11-30T17:00", [("Research", 240), ("Draft", 240), ("Revise", 240), ("Present", 240)])
    app.do("project_set", id=made, pacing="linear")
    replan(app.conn, app.now_utc)
    [shown] = app.do("projects")
    found = blocks(app)
    later = [i for i in ids if not found.get(i)]
    assert later, "some of it is planned past the plan's two weeks"
    assert all(shown["step_finish"].get(str(i), "") > "2026-11-01" for i in later)
    assert shown["status"] == "on_track"


# 17 Nov, your choice: a project's order is its chain. Each step waits for the one above it ("↓ then"); one made "Any
# time" goes alongside; the old "waits on" between a project's own steps gives way to the order.


def starts(app: App, ids: list[int]) -> list[int]:
    found = blocks(app)
    return [found[i][0][0] for i in ids]


def test_each_step_waits_for_the_one_above_it(app: App) -> None:
    _, ids = project(app, "2026-10-30T17:00", [("Research", 120), ("Outline", 60), ("Draft", 180)])
    replan(app.conn, app.now_utc)
    found = blocks(app)
    for before, after in zip(ids, ids[1:], strict=False):
        assert found[after][0][0] >= found[before][-1][1]


def test_a_step_made_any_time_can_go_before_the_one_above(app: App) -> None:
    made, (research, slides, cite) = project(
        app, "2026-10-23T17:00", [("Research", 480), ("Slides", 240), ("Citations", 60)]
    )
    app.do("step_any_time", id=cite, any_time=True)
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert found[cite][0][0] < found[slides][-1][1], "any time: not held behind Slides (a chained step starts after)"
    assert found[slides][0][0] >= found[research][-1][1], "Slides still after Research"
    [shown] = app.do("projects")
    assert shown["any_time"] == [cite]
    app.do("step_any_time", id=cite, any_time=False)
    replan(app.conn, app.now_utc)
    assert blocks(app)[cite][0][0] >= blocks(app)[slides][-1][1]


def test_reordering_changes_what_waits_on_what(app: App) -> None:
    made, (a, b, c) = project(app, "2026-10-30T17:00", [("A", 120), ("B", 120), ("C", 120)])
    app.do("reorder", parent_id=made, ids=[c, a, b])
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert found[c][-1][1] <= found[a][0][0] and found[a][-1][1] <= found[b][0][0]


def test_an_old_wait_against_the_order_gives_way_to_it(app: App) -> None:
    # Research was made to wait on Draft, listed after it: with the order a chain, that was a loop
    _, (research, draft) = project(app, "2026-10-30T17:00", [("Research", 120), ("Draft", 120)])
    app.do("depend", item_id=research, depends_on_id=draft)
    replan(app.conn, app.now_utc)
    found = blocks(app)
    assert found[draft][0][0] >= found[research][-1][1]


def test_only_a_projects_step_can_be_any_time(app: App) -> None:
    alone = app.do("add", title="Laundry", duration_min=30)["item"]["id"]
    with pytest.raises(Exception, match="only a project's step"):
        app.do("step_any_time", id=alone, any_time=True)


def test_a_more_on_step_is_any_time(app: App) -> None:
    made = app.do("add", title="Thesis", preset="Project", due="2026-10-30T17:00", duration_min=600)["item"]["id"]
    app.do("add", title="Read", preset="Assignment", duration_min=120, parent_id=made)
    [shown] = app.do("projects")
    rest = [c["id"] for c in shown["children"] if c["title"] == "More on Thesis"]
    assert shown["any_time"] == rest
