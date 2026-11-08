"""A new all-day event leaves its day free (7 Nov: "as the view is centered on tuesday i cannot see any events planned
for tuesday": Remy's Birthday, added as midnight to midnight without saying it doesn't block time, took all of
Tuesday). Black box through the commands as that birthday was added, then the rule inside. Monday 2026-10-19."""

from pathlib import Path

import pytest

from friday.commands.fields import all_day_is_free
from friday.planner.service import replan
from tests.commands.helpers import App, new_app

BIRTHDAY = {"title": "Remy's Birthday", "when": "fixed", "start": "2026-10-20T00:00", "end": "2026-10-21T00:00"}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=4)


def tuesday_work(app: App) -> int:
    """An essay that can only be done on Tuesday, and the minutes of it planned there."""
    essay = app.do("add", title="essay", duration_min=120, release="2026-10-20T00:00", due="2026-10-20T23:00")
    replan(app.conn, app.now_utc)
    blocks = app.do("plan", start="2026-10-20T00:00", end="2026-10-21T00:00")["blocks"]
    return sum(1 for b in blocks if b["item_id"] == essay["item"]["id"])


def fixed(app: App, title: str) -> dict:
    return next(i for i in app.table("items") if i["title"] == title and i["status"] == "todo")


class TestBlackBox:
    def test_a_yearly_birthday_added_as_it_was_leaves_tuesday_to_plan(self, app: App) -> None:
        app.do("add", **BIRTHDAY, every="rrule:FREQ=YEARLY", after=[], before=[], exceptions=[])
        assert tuesday_work(app) > 0

    def test_so_does_one_that_doesnt_repeat(self, app: App) -> None:
        app.do("add", **BIRTHDAY)
        assert fixed(app, "Remy's Birthday")["blocks_time"] == 0 and tuesday_work(app) > 0

    def test_a_repeat_made_on_its_own_too(self, app: App) -> None:
        app.do("series_add", **BIRTHDAY, every="rrule:FREQ=YEARLY")
        assert fixed(app, "Remy's Birthday")["blocks_time"] == 0

    def test_saying_it_blocks_time_still_takes_the_day(self, app: App) -> None:
        app.do("add", **(BIRTHDAY | {"title": "Away"}), blocks_time=True)
        assert fixed(app, "Away")["blocks_time"] == 1 and tuesday_work(app) == 0

    def test_an_event_with_times_still_blocks_them(self, app: App) -> None:
        app.do("add", title="lab", when="fixed", start="2026-10-20T09:00", end="2026-10-20T12:00")
        assert fixed(app, "lab")["blocks_time"] == 1

    def test_editing_a_busy_all_day_event_keeps_it_busy(self, app: App) -> None:
        made = app.do("add", **(BIRTHDAY | {"title": "Away"}), blocks_time=True)["item"]["id"]
        app.do("edit", id=made, start="2026-10-21T00:00", end="2026-10-22T00:00")
        assert fixed(app, "Away")["blocks_time"] == 1


class TestInside:
    def test_only_midnight_to_a_later_midnight_unsaid(self) -> None:
        day = {"start": "2026-10-20T00:00", "end": "2026-10-21T00:00"}
        assert all_day_is_free(day)["blocks_time"] is False
        assert all_day_is_free(day | {"blocks_time": None})["blocks_time"] is False
        assert all_day_is_free(day | {"blocks_time": True})["blocks_time"] is True
        assert "blocks_time" not in all_day_is_free({"start": "2026-10-20T00:00", "end": "2026-10-20T23:00"})
        assert "blocks_time" not in all_day_is_free({"start": "2026-10-20T00:00", "end": "2026-10-20T00:00"})
        assert "blocks_time" not in all_day_is_free({"title": "essay", "due": "2026-10-21T00:00"})
