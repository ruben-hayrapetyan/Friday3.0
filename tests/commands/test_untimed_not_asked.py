"""With untimed blocks planned again, the Inbox asks nothing about them (7 Nov: "these notifications can get a little
annoying especially of when there was no timer, i didnt do anything"): Settings → Schedule's "Plan it again" says no
timer means not done, so there's nothing to ask; a missed block's "I did it" says otherwise. "Count it as done" still
asks, since there Friday is guessing. Monday 2026-10-19 in New York; blocks placed by locked pins."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def untimed_missed(app: App) -> None:
    app.do("settings_set", key="planner", value={"assume_unreviewed": "not_done"})


def placed(app: App, text: str, start: str, end: str) -> int:
    item = app.do("add", text=text)["item"]["id"]
    app.do("pin", id=item, start=f"2026-10-19T{start}", end=f"2026-10-19T{end}", kind="locked")
    return item


def gaps(app: App, day: str | None = None) -> list[dict]:
    return app.do("review", **({"date": day} if day else {}))["gaps"]


def asked(app: App, day: str | None = None) -> list[int]:
    return [g["item_id"] for g in gaps(app, day) if g["answer"] is None and not g["finished"]]


def test_a_block_that_passed_with_no_timer_isnt_asked_about(app: App) -> None:
    untimed_missed(app)
    placed(app, "essay due wed ~2h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert asked(app) == []


def test_nor_yesterdays(app: App) -> None:
    untimed_missed(app)
    placed(app, "essay due wed ~2h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-20T09:00")
    assert asked(app, "2026-10-19") == []


def test_its_work_is_planned_again(app: App) -> None:
    untimed_missed(app)
    essay = placed(app, "essay due wed ~2h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    item = app.do("item", id=essay)["item"]
    assert (item["done_min"], item["remaining_min"]) == (0, 120)


def test_i_did_it_on_the_calendar_still_counts_it(app: App) -> None:
    untimed_missed(app)
    essay = placed(app, "essay due wed ~2h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    (block,) = [b for b in app.do("review")["blocks"] if b["item_id"] == essay and b["start"] == "2026-10-19T09:00"]
    app.do("settle", block_key=block["key"], status="done", until=block["end"])
    assert app.do("item", id=essay)["item"]["done_min"] == 60
    assert asked(app) == []


def test_count_it_as_done_still_asks(app: App) -> None:
    essay = placed(app, "essay due wed ~2h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert asked(app) == [essay]


def test_switching_to_plan_it_again_drops_what_was_waiting(app: App) -> None:
    essay = placed(app, "essay due wed ~2h", "09:00", "10:00")
    replan(app.conn, app.now_utc)
    app.at("2026-10-19T12:00")
    assert asked(app) == [essay]
    untimed_missed(app)
    assert asked(app) == []
