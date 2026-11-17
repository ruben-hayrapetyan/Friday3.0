"""A project made of steps and one worked on as a whole, told apart by Friday (17 Nov, proposal (h)): the last step
done finishes the project (one Undo puts both back), a step opened again opens it; a length you gave it beyond its
steps is a "More on" step, made, resized and let go as the steps change, and not made again once you delete it."""

from pathlib import Path

import pytest

from friday.commands.project_steps import REST
from friday.planner.store import kv_get
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=14)


def project(app: App, minutes: int | None = None) -> int:
    fields = {"duration_min": minutes} if minutes else {}
    return app.do("add", title="Thesis", preset="Project", due="2026-11-20T17:00", **fields)["item"]["id"]


def step(app: App, parent: int, title: str, minutes: int) -> int:
    return app.do("add", title=title, preset="Assignment", duration_min=minutes, parent_id=parent)["item"]["id"]


def status(app: App, item_id: int) -> str:
    return app.conn.execute("SELECT status FROM items WHERE id = ?", [item_id]).fetchone()[0]


def more_on(app: App, parent: int) -> int:
    return (kv_get(app.conn, REST, {}) or {}).get(str(parent), 0)


def rest(app: App, parent: int) -> dict | None:
    made = more_on(app, parent)
    if not made:
        return None
    row = app.conn.execute("SELECT title, duration_units, status FROM items WHERE id = ?", [made]).fetchone()
    return None if row[2] == "dropped" else {"title": row[0], "minutes": row[1] * 15, "status": row[2]}


def test_the_last_step_done_finishes_the_project_and_one_undo_puts_both_back(app: App) -> None:
    made = project(app)
    first, last = step(app, made, "Read", 60), step(app, made, "Write", 120)
    app.do("done", id=first)
    assert status(app, made) == "todo"  # a step still to do
    command = app.full("done", payload={"id": last}).command_id
    assert (status(app, last), status(app, made)) == ("done", "done")
    app.do("undo", command_id=command)
    assert (status(app, last), status(app, made)) == ("todo", "todo")


def test_a_step_opened_again_opens_its_finished_project(app: App) -> None:
    made = project(app)
    only = step(app, made, "Write", 120)
    app.do("done", id=only)
    assert status(app, made) == "done"
    app.do("reopen", id=only)
    assert status(app, made) == "todo"


def test_a_project_with_no_steps_is_a_to_do_done_by_itself(app: App) -> None:
    made = project(app, 300)
    app.do("done", id=made)
    assert status(app, made) == "done"
    assert rest(app, made) is None


def test_the_length_you_gave_beyond_its_steps_is_a_more_on_step_kept_as_steps_change(app: App) -> None:
    made = project(app, 600)  # ten hours, said by you
    step(app, made, "Read", 240)
    assert rest(app, made) == {"title": "More on Thesis", "minutes": 360, "status": "todo"}
    write = step(app, made, "Write", 120)
    assert rest(app, made)["minutes"] == 240  # type: ignore[index]
    app.do("edit", id=made, duration_min=720)
    assert rest(app, made)["minutes"] == 360  # type: ignore[index]
    step(app, made, "Polish", 360)
    assert rest(app, made) is None  # the steps cover it: no "More on" step
    app.do("drop", id=write)
    assert rest(app, made)["minutes"] == 120  # type: ignore[index]


def test_a_more_on_step_is_work_the_project_waits_for(app: App) -> None:
    made = project(app, 300)
    only = step(app, made, "Read", 120)
    app.do("done", id=only)
    assert status(app, made) == "todo"  # its "More on" step is still to do
    app.do("done", id=more_on(app, made))
    assert status(app, made) == "done"


def test_a_guessed_length_makes_no_more_on_step(app: App) -> None:
    made = project(app)  # a Project's own ten hours, a guess
    step(app, made, "Read", 120)
    assert rest(app, made) is None


def test_a_more_on_step_you_delete_isnt_made_again(app: App) -> None:
    made = project(app, 600)
    step(app, made, "Read", 120)
    app.do("drop", id=more_on(app, made))
    step(app, made, "Write", 60)
    assert more_on(app, made) == 0
    titles = [r[0] for r in app.conn.execute("SELECT title FROM items WHERE parent_id = ? AND status = 'todo'", [made])]
    assert "More on Thesis" not in titles


def test_a_more_on_step_with_time_in_it_ends_at_what_was_done_once_the_steps_cover_the_rest(app: App) -> None:
    made = project(app, 300)
    step(app, made, "Read", 120)
    app.at("2026-10-19T12:00").do("log", id=more_on(app, made), start="2026-10-19T10:00", end="2026-10-19T10:30")
    step(app, made, "Write", 180)
    assert rest(app, made) == {"title": "More on Thesis", "minutes": 30, "status": "todo"}
