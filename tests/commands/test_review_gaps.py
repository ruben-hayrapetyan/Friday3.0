"""The daily Review asks only about the gaps, by task (27 Oct: "everything that is covered in the human inputs from
review is already just a learned behaviour"; answered "Only the gaps, by task"): a task's time that ended with no
timer running, no answer and the task still open. Monday 2026-10-19 in New York; blocks placed by locked pins."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def placed(app: App, text: str, *spans: tuple[str, str]) -> int:
    item = app.do("add", text=text)["item"]["id"]
    for start, end in spans:
        app.do("pin", id=item, start=f"2026-10-19T{start}", end=f"2026-10-19T{end}", kind="locked")
    return item


def gaps(app: App) -> list[dict]:
    return app.do("review")["gaps"]


def asked(app: App) -> list[int]:
    return [g["item_id"] for g in gaps(app) if g["answer"] is None]


def gap(app: App, item: int) -> dict:
    return next(g for g in gaps(app) if g["item_id"] == item)


def done_min(app: App, item: int) -> int:
    return app.do("item", id=item)["item"]["done_min"]


def busy(app: App, start: str, end: str) -> None:
    app.do("add", title="busy", when="fixed", start=f"2026-10-19T{start}", end=f"2026-10-19T{end}")


def test_a_tasks_untimed_blocks_are_one_row_with_their_minutes(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", ("09:00", "10:00"), ("11:00", "11:30"))
    busy(app, "10:00", "11:00")
    busy(app, "11:30", "12:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    row = gap(app, essay)
    assert (row["planned_min"], row["answer"], len(row["spans"])) == (90, None, 2)
    assert row["spans"][0] == ["2026-10-19T09:00", "2026-10-19T10:00"]
    assert row["last"] is False  # the rest is planned later


def test_rows_come_in_the_order_the_day_planned_them(app: App) -> None:
    late = placed(app, "email ~1h", ("10:30", "11:30"))
    early = placed(app, "essay due wed ~1h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert asked(app) == [early, late]


def test_time_you_timed_isnt_asked_about(app: App) -> None:
    essay = placed(app, "essay due wed ~1h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    app.at("2026-10-19T10:00")
    app.do("stop")
    app.at("2026-10-19T12:00")
    assert asked(app) == []


def test_a_task_you_checked_off_isnt_asked_about(app: App) -> None:
    essay = placed(app, "essay due wed ~1h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("done", id=essay)
    assert gaps(app) == []


def test_time_marked_on_the_calendar_is_answered_not_asked(app: App) -> None:
    essay = placed(app, "essay due wed ~1h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("settle", block_key=f"T{essay}@2026-10-19T09:00", status="not_done")
    assert asked(app) == [] and gap(app, essay)["answer"] == "not_done"


def test_a_block_under_way_isnt_asked_about_yet(app: App) -> None:
    placed(app, "essay due wed ~2h", ("09:00", "11:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:00")
    assert gaps(app) == []


def test_meals_are_the_meal_taps_to_record(app: App) -> None:
    lunch = app.do("add", title="Lunch", preset="Routine", duration_min=30)["item"]["id"]
    app.do("pin", id=lunch, start="2026-10-19T09:30", end="2026-10-19T10:00", kind="locked")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert gaps(app) == []


def test_all_of_it_records_the_planned_time(app: App) -> None:
    essay = placed(app, "essay due wed ~90m", ("09:00", "10:00"), ("11:00", "11:30"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert app.do("review_task", item_id=essay, status="done")["message"] == "essay: all done"
    assert done_min(app, essay) == 90
    assert (gap(app, essay)["answer"], gap(app, essay)["done_min"]) == ("done", 90)


def test_some_of_it_records_what_you_say_across_its_blocks(app: App) -> None:
    essay = placed(app, "essay due wed ~90m", ("09:00", "10:00"), ("11:00", "11:30"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert app.do("review_task", item_id=essay, status="partial", minutes=45)["message"] == "essay: 45 min done"
    assert done_min(app, essay) == 45
    assert gap(app, essay)["answer"] == "partial"


def test_some_needs_how_much(app: App) -> None:
    essay = placed(app, "essay due wed ~2h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    with pytest.raises(FieldError, match="how much"):
        app.do("review_task", item_id=essay, status="partial")


def test_none_of_it_is_planned_again(app: App) -> None:
    essay = placed(app, "essay due wed ~2h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("review_task", item_id=essay, status="not_done")
    assert done_min(app, essay) == 0
    assert app.do("item", id=essay)["item"]["remaining_min"] == 120


def test_finished_it_checks_the_task_off(app: App) -> None:
    essay = placed(app, "essay due wed ~3h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("review_task", item_id=essay, status="finished")
    assert app.do("item", id=essay)["item"]["status"] == "done"
    row = gap(app, essay)
    assert (row["answer"], row["finished"]) == ("done", True)


def test_an_answer_can_be_changed(app: App) -> None:
    essay = placed(app, "essay due wed ~2h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("review_task", item_id=essay, status="done")
    app.do("review_task", item_id=essay, status="not_done")
    assert done_min(app, essay) == 0 and gap(app, essay)["answer"] == "not_done"


def test_the_day_is_reviewed_once_every_row_is_answered(app: App) -> None:
    essay = placed(app, "essay due wed ~1h", ("09:00", "10:00"))
    email = placed(app, "email ~1h", ("10:30", "11:30"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("review_task", item_id=essay, status="done")
    assert not app.do("review")["reviewed"]
    app.do("review_task", item_id=email, status="not_done")
    assert app.do("review")["reviewed"]


def test_the_last_planned_time_is_marked_so_finishing_is_offered_first(app: App) -> None:
    essay = placed(app, "essay due mon 18:00 ~1h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert gap(app, essay)["last"] is True


def test_a_task_with_no_time_that_day_cant_be_answered(app: App) -> None:
    essay = app.do("add", text="essay due wed ~1h")["item"]["id"]
    with pytest.raises(FieldError, match="no time"):
        app.do("review_task", item_id=essay, status="done")


def test_yesterdays_gaps_can_be_answered_today(app: App) -> None:
    essay = placed(app, "essay due wed ~1h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-20T09:00")
    assert [g["item_id"] for g in app.do("review", date="2026-10-19")["gaps"]] == [essay]
    app.do("review_task", date="2026-10-19", item_id=essay, status="done")
    assert done_min(app, essay) == 60
