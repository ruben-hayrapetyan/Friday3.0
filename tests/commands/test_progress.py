"""Progress, the timer, logging and the day's review (commands/progress.py), at the edges: a share out of range, a
block that isn't there, something that happened added in the review, and a day closed before it ended. Monday
2026-10-19 in New York; blocks placed by locked pins."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def placed(app: App, text: str, start: str, end: str) -> int:
    item = app.do("add", text=text)["item"]["id"]
    app.do("pin", id=item, start=f"2026-10-19T{start}", end=f"2026-10-19T{end}", kind="locked")
    return item


def test_progress_is_a_share_from_none_to_all(app: App) -> None:
    item = app.do("add", title="Essay", duration_min=120)["item"]["id"]
    with pytest.raises(FieldError, match="between 0 and 1"):
        app.do("progress", id=item, share=1.5)


def test_an_event_isnt_something_to_time(app: App) -> None:
    event = app.do("add", title="Lecture", start="2026-10-19T10:00", end="2026-10-19T11:00")["item"]["id"]
    with pytest.raises(FieldError, match=f"T{event} isn't something to work on now"):
        app.do("start", id=event)


def test_logging_needs_an_item_or_a_title(app: App) -> None:
    with pytest.raises(FieldError, match="give an item id, or a title"):
        app.do("log", start="2026-10-19T07:00", end="2026-10-19T08:00")


def test_a_review_names_a_block_by_its_item_and_start(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    with pytest.raises(FieldError, match="isn't a block like T42@2026-10-20T14:00"):
        app.do("review_submit", entries=[{"block_key": f"T{essay}@noon"}])
    with pytest.raises(FieldError, match=f"no block T{essay}@2026-10-19T11:00 on 2026-10-19"):
        app.do("review_submit", entries=[{"block_key": f"T{essay}@2026-10-19T11:00"}])
    with pytest.raises(FieldError, match="between 0 and 1"):
        app.do("review_submit", entries=[{"block_key": f"T{essay}@2026-10-19T09:00", "status": "partial", "share": 2}])


def test_a_review_of_a_closed_day_replaces_what_was_assumed_and_adds_what_happened(app: App) -> None:
    essay = placed(app, "essay due wed ~4h", "09:00", "10:00")
    reading = app.do("add", title="Reading", duration_min=60)["item"]["id"]
    replan(app.conn, app.now_utc)
    app.at("2026-10-20T12:00").do("close_day")
    assert [(p["item_id"], p["source"]) for p in app.table("progress")] == [(essay, "assumed")]
    app.do(
        "review_submit",
        date="2026-10-19",
        entries=[
            {"block_key": f"T{essay}@2026-10-19T09:00", "status": "partial", "share": 0.5},
            {"item_id": reading, "start": "2026-10-19T14:00", "end": "2026-10-19T14:45"},
        ],
    )
    found = sorted((p["item_id"], p["source"], p["minutes"]) for p in app.table("progress"))
    assert found == sorted([(essay, "review", 30), (reading, "review", 45)])


def test_only_a_day_that_has_ended_can_be_closed(app: App) -> None:
    with pytest.raises(FieldError, match="only a day that has ended"):
        app.do("close_day", date="2026-10-19")
