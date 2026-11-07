"""`day_gaps` with `assume_unreviewed = not_done`, from the inside: a task's unanswered blocks are left out, its
answered ones still reported with what you said (the Review sheet shows them), and a task with some of each isn't
asked about. Monday 2026-10-19 in New York; blocks placed by locked pins."""

from pathlib import Path

import pytest

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


def missed_mode(app: App) -> None:
    app.do("settings_set", key="planner", value={"assume_unreviewed": "not_done"})


def test_a_task_answered_before_still_shows_its_answer(app: App) -> None:
    essay = placed(app, "essay due wed ~2h", ("09:00", "10:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    app.do("review_task", item_id=essay, status="partial", minutes=30)
    missed_mode(app)
    (gap,) = app.do("review")["gaps"]
    assert (gap["item_id"], gap["answer"], gap["done_min"]) == (essay, "partial", 30)


def test_a_task_with_one_block_answered_and_one_not_isnt_asked(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", ("09:00", "10:00"), ("11:15", "12:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T10:30")
    app.do("review_task", item_id=essay, status="done")  # the 9am block, the only one over
    app.at("2026-10-19T13:00")
    settled = app.do("review")["settled"]
    assert "T1@2026-10-19T09:00" in settled and len(settled) < 3  # the 9am answered, the later ones not
    assert [g["item_id"] for g in app.do("review")["gaps"] if g["answer"] is None] == [essay]  # counted done: asks
    missed_mode(app)
    assert [g for g in app.do("review")["gaps"] if g["answer"] is None] == []


def test_the_day_counts_as_reviewed_once_whats_left_is_answered(app: App) -> None:
    missed_mode(app)
    essay = placed(app, "essay due wed ~2h", ("09:00", "10:00"))
    placed(app, "email ~1h", ("11:15", "12:00"))
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T13:00")
    assert not app.do("review")["reviewed"]
    app.do("review_task", item_id=essay, status="done")  # said from the Review sheet: nothing else waits
    assert app.do("review")["reviewed"]
