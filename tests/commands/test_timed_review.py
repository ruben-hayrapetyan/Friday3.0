"""Time you timed is accounted for (5 Nov: the Inbox said "CS A4 Complete … did you do it?" while its timer was
running, about blocks each replan had put at now). A block of the task you're timing isn't asked about, running timer
or stopped; one planned while you timed something else didn't happen: not asked, not counted done, planned again and
shown missed. Monday 2026-10-19 in New York; blocks placed by locked pins."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def placed(app: App, text: str, start: str, end: str) -> int:
    item = app.do("add", text=text)["item"]["id"]
    app.do("pin", id=item, start=f"2026-10-19T{start}", end=f"2026-10-19T{end}", kind="locked")
    return item


def asked(app: App) -> list[int]:
    return [g["item_id"] for g in app.do("review")["gaps"] if g["answer"] is None]


def planned_ahead(app: App, item: int) -> int:
    plan = app.do("plan", start=app.local_now(), end="2026-10-22T00:00")
    return sum(minutes(b) for b in plan["blocks"] if b["item_id"] == item and b["start"] >= app.local_now())


def state_at(app: App, item: int, start: str) -> str:
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-20T00:00")
    return next(b["state"] for b in plan["blocks"] if b["item_id"] == item and b["start"] == f"2026-10-19T{start}")


def minutes(b: dict) -> int:
    return (int(b["end"][11:13]) * 60 + int(b["end"][14:16])) - (int(b["start"][11:13]) * 60 + int(b["start"][14:16]))


def test_the_task_youre_timing_now_isnt_asked_about(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    app.at("2026-10-19T11:00")
    replan(app.conn, app.now_utc)  # a replan with the timer running plans the essay at now, as each one did on 5 Nov
    app.at("2026-10-19T12:00")
    assert asked(app) == []
    assert state_at(app, essay, "09:00") == "timed"


def test_the_task_youre_timing_isnt_counted_twice(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    app.at("2026-10-19T10:00")
    replan(app.conn, app.now_utc)
    # The hour timed counts once, as the timer's: three hours are left, not two (the block too).
    assert planned_ahead(app, essay) == 180


def test_what_was_planned_while_you_timed_something_else_isnt_asked_or_counted(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "10:00")
    email = placed(app, "email due wed ~1h", "10:00", "11:00")
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    app.at("2026-10-19T11:30")
    assert asked(app) == []
    assert state_at(app, email, "10:00") == "missed"
    replan(app.conn, app.now_utc)
    assert planned_ahead(app, email) == 60  # the whole hour again, nothing assumed done


def test_the_same_after_the_timer_stops(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "10:00")
    email = placed(app, "email due wed ~1h", "10:00", "11:00")
    replan(app.conn, app.now_utc)
    app.do("start", id=essay)
    app.at("2026-10-19T11:00").do("stop")
    app.at("2026-10-19T12:00")
    assert asked(app) == []
    assert state_at(app, email, "10:00") == "missed"


def test_a_little_of_something_else_timed_still_asks(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "09:30")
    email = placed(app, "email due wed ~1h", "10:00", "11:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:00").do("start", id=essay)
    app.at("2026-10-19T10:20").do("stop")  # 20 minutes of the email's hour: the other 40 Friday can't account for
    app.at("2026-10-19T12:00")
    assert email in asked(app)
    assert state_at(app, email, "10:00") == "done"  # unanswered blocks count as done, as before


def test_timing_something_that_runs_by_itself_leaves_the_rest_asked(app: App) -> None:
    email = placed(app, "email due wed ~1h", "10:00", "11:00")
    laundry = app.do("add", title="Laundry", duration_min=90, due="2026-10-20T20:00", background=True)["item"]["id"]
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:00").do("start", id=laundry)
    app.at("2026-10-19T12:00")
    assert email in asked(app)


def test_submitting_the_review_doesnt_count_time_spent_on_something_else(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "09:30")
    email = placed(app, "email due wed ~1h", "10:00", "11:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:00").do("start", id=essay)
    app.at("2026-10-19T12:00")
    assert asked(app) == [essay]  # its half hour before the timer; the email's hour went to the essay
    assert app.do("review_submit", date="2026-10-19", entries=[])["message"] == "Reviewed Mon Oct 19"
    assert app.do("item", id=email)["item"]["done_min"] == 0  # submitting doesn't count the hour you didn't spend on it
