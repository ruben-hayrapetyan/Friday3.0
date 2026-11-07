"""Work sessions under five minutes are ignored (7 Nov: "can you ignore work sessions less then 5 minutes"): a timer
stopped sooner records nothing, says so, and leaves the plan as if it never ran; five minutes or more counts as
before. Black box, then the inside. Monday 2026-10-19 in New York."""

from pathlib import Path

import pytest

from friday.commands.timer import ran
from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def task(app: App, title: str, minutes: int = 120) -> int:
    return app.do("add", title=title, duration_min=minutes, due="2026-10-21T23:00")["item"]["id"]


def timed(app: App, item: int) -> int:
    return sum(r["minutes"] for r in app.table("progress") if r["item_id"] == item and r["source"] == "timer")


def timed_for(app: App, item: int, minutes: int, **stop: object) -> dict:
    app.do("start", id=item)
    app.now_utc += minutes
    return app.do("stop", **stop)


class TestBlackBox:
    def test_four_minutes_records_nothing_and_says_why(self, app: App) -> None:
        essay = task(app, "essay")
        out = timed_for(app, essay, 4)
        assert timed(app, essay) == 0
        assert out["minutes"] == 0 and "too short to count (under 5 min)" in out["message"]

    def test_five_minutes_counts(self, app: App) -> None:
        essay = task(app, "essay")
        out = timed_for(app, essay, 5)
        assert timed(app, essay) == 5 and out["message"].endswith("after 5 min")

    def test_its_work_is_still_all_to_do(self, app: App) -> None:
        essay = task(app, "essay")
        timed_for(app, essay, 3)
        item = app.do("item", id=essay)["item"]
        assert (item["done_min"], item["remaining_min"]) == (0, 120)

    def test_stopping_as_of_earlier_counts_what_was_left(self, app: App) -> None:
        essay = task(app, "essay")
        app.do("start", id=essay)  # at 9:00
        app.now_utc += 30
        app.do("stop", at="2026-10-19T09:03")  # forgot the timer: really stopped after three minutes
        assert timed(app, essay) == 0

    def test_done_after_two_minutes_checks_it_off_without_a_sitting(self, app: App) -> None:
        email = task(app, "email", 15)
        timed_for(app, email, 2, done=True)
        assert app.do("item", id=email)["item"]["status"] == "done" and timed(app, email) == 0

    def test_a_short_sitting_beside_another_counts_only_the_long_one(self, app: App) -> None:
        reading, laundry = task(app, "reading"), task(app, "laundry", 60)
        app.do("start", id=laundry)
        app.now_utc += 2
        app.do("start", id=reading, alongside=True)
        app.do("stop", id=laundry)  # two minutes of laundry
        app.now_utc += 20
        app.do("stop", id=reading)
        assert (timed(app, laundry), timed(app, reading)) == (0, 20)

    def test_switching_tasks_after_a_minute_drops_the_first(self, app: App) -> None:
        essay, email = task(app, "essay"), task(app, "email", 30)
        app.do("start", id=essay)
        app.now_utc += 1
        app.do("start", id=email)  # changed my mind
        app.now_utc += 10
        app.do("stop")
        assert (timed(app, essay), timed(app, email)) == (0, 10)

    def test_the_review_still_asks_about_a_block_a_short_sitting_was_in(self, app: App) -> None:
        essay = task(app, "essay due wed")
        app.do("pin", id=essay, start="2026-10-19T09:00", end="2026-10-19T10:00", kind="locked")
        replan(app.conn, app.now_utc)
        timed_for(app, essay, 3)
        app.at("2026-10-19T12:00")
        assert [g["item_id"] for g in app.do("review")["gaps"] if g["answer"] is None] == [essay]

    def test_the_shortest_is_a_setting(self, app: App) -> None:
        app.do("settings_set", key="planner", value={"shortest_sitting_min": 1})
        essay = task(app, "essay")
        timed_for(app, essay, 2)
        assert timed(app, essay) == 2


class TestInside:
    def test_how_long_it_really_ran_not_rounded(self) -> None:
        assert [ran(40), ran(60), ran(280)] == ["40 s", "1 min", "4 min 40 s"]

    def test_default_is_five(self, app: App) -> None:
        assert app.do("settings")["planner"]["shortest_sitting_min"] == 5
