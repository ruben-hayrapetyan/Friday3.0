"""Work your plans showed late that you finished on time, through the whole command layer (2 Nov: "it consistently
proposes schedules that have things late but i don't do anything late"): real replans save what they show late,
your logged work and `done` are read for how you did it, the Inbox asks, and your answer changes the plan.

Monday 19 Oct 2026, New York; weeknights 11:30pm with an hour of margin (Friday plans nothing from 12:30am), up at
7:30. Each day is busy 9am–11:30pm, so 3 h due at 9am the next morning can't fit in the plan: an hour of margin
is all there is."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.planner.cushion import SHARES
from friday.planner.planned_late import planned_late
from friday.planner.snapshot import take_snapshot
from friday.planner.store import kv_get, load_settings
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=3)


def asked(app: App) -> dict[str, dict]:
    return {d["key"]: d for d in app.do("status")["decisions"] if d["kind"] == "learned"}


def answer(app: App, key: str, option: str) -> str:
    return app.do("conflict_resolve", key=key.removeprefix("learned:"), option=option)["message"]


def due_tomorrow(app: App, day: int, preset: str = "Assignment", hours: int = 3) -> int:
    """`hours` of `preset` work due at 9am the morning after 2026-10-`day`, its length yours."""
    return app.do("add", title=f"{preset} {day}", preset=preset, duration_min=hours * 60, firmness="hard",
                  due=f"2026-10-{day + 1:02d}T09:00")["item"]["id"]  # fmt: skip


def shown_late(app: App, day: int, preset: str = "Assignment") -> int:
    """At 9am on 2026-10-`day`, a busy day and work due at 9am the next morning that the plan shows late."""
    app.at(f"2026-10-{day:02d}T09:00")
    app.do("add", title="busy", when="fixed", start=f"2026-10-{day:02d}T09:00", end=f"2026-10-{day:02d}T23:30")
    item = due_tomorrow(app, day, preset)
    app.do("replan")
    assert item in planned_late(app.conn, 1), "the plan should show it late"
    return item


def worked_late(app: App, item: int, day: int, until: str = "03:00") -> None:
    """Worked from 12:30am the night after `day` until `until`, done then: before its 9am due."""
    app.at(f"2026-10-{day + 1:02d}T{until}")
    app.do("log", id=item, start=f"2026-10-{day + 1:02d}T00:30", end=f"2026-10-{day + 1:02d}T{until}")
    app.do("done", id=item)


def three_late_nights(app: App) -> None:
    for day in (19, 20, 21):  # Monday to Wednesday nights
        worked_late(app, shown_late(app, day), day)
    app.at("2026-10-22T09:00")


class TestLaterNights:
    def test_the_inbox_asks_after_three_late_nights_not_before(self, app: App) -> None:
        for day in (19, 20):
            worked_late(app, shown_late(app, day), day)
        assert "learned:beat:nights" not in asked(app)
        worked_late(app, shown_late(app, 21), 21)
        found = asked(app)["learned:beat:nights"]
        assert found["title"] == "You finish work Friday showed late by working later at night"
        assert (
            "about 2h 30m past where Friday stops planning at night (Mondays, Tuesdays and Wednesdays)"
            in found["detail"]
        )
        assert [(o["id"], o["recommended"]) for o in found["options"]] == [("later", True), ("keep", False)]
        assert found["options"][0]["label"] == "Plan up to 2h 30m later on those nights"

    def test_yes_grows_those_evenings_margins_and_late_work_then_fits(self, app: App) -> None:
        three_late_nights(app)
        message = answer(app, "learned:beat:nights", "later")
        assert message == "Later nights on Mondays, Tuesdays and Wednesdays when work would be late"
        sleep = load_settings(app.conn, 1)["sleep"]
        assert [sleep[d].margin_min for d in ("mon", "tue", "wed", "thu", "sun")] == [210, 210, 210, 60, 60]
        assert "learned:beat:nights" not in asked(app)
        app.at("2026-10-26T09:00")  # the next Monday: the same day, the same work
        app.do("add", title="busy", when="fixed", start="2026-10-26T09:00", end="2026-10-26T23:30")
        item = due_tomorrow(app, 26)
        app.do("replan")
        status = app.do("status")
        assert "Assignment 26" not in status["late"] and item not in {i["item_id"] for i in status["late_items"]}
        assert item not in planned_late(app.conn, 1)

    def test_no_keeps_your_nights_and_isnt_asked_again(self, app: App) -> None:
        three_late_nights(app)
        assert answer(app, "learned:beat:nights", "keep") == "Kept your nights"
        assert load_settings(app.conn, 1)["sleep"]["mon"].margin_min == 60
        assert "learned:beat:nights" not in asked(app)

    def test_asked_again_when_you_reach_further(self, app: App) -> None:
        three_late_nights(app)
        answer(app, "learned:beat:nights", "keep")
        for day in (22, 23):  # Thursday and Friday nights, to 4:30am: the median reach grows
            worked_late(app, shown_late(app, day), day, until="04:30")
        worked_late(app, shown_late(app, 26), 26, until="04:30")  # Monday: Sunday night ends at 9am
        assert "learned:beat:nights" in asked(app)

    def test_work_finished_after_its_due_teaches_nothing(self, app: App) -> None:
        for day in (19, 20, 21):
            item = shown_late(app, day)
            app.at(f"2026-10-{day + 1:02d}T10:00")
            app.do("log", id=item, start=f"2026-10-{day + 1:02d}T00:30", end=f"2026-10-{day + 1:02d}T03:00")
            app.do("done", id=item)  # an hour after its due
        assert "learned:beat:nights" not in asked(app)
        out = app.do("beat_plan")
        assert (out["on_time"], out["late"]) == (0, 3)

    def test_an_answer_to_a_settled_question_is_refused(self, app: App) -> None:
        three_late_nights(app)
        answer(app, "learned:beat:nights", "keep")
        with pytest.raises(FieldError):
            answer(app, "learned:beat:nights", "later")


class TestFaster:
    def finish_fast(self, app: App, day: int) -> int:
        item = shown_late(app, day, preset="Reading")
        app.at(f"2026-10-{day + 1:02d}T00:30")
        app.do("log", id=item, start=f"2026-10-{day:02d}T23:30", end=f"2026-10-{day + 1:02d}T00:30")
        app.do("done", id=item)  # 1 h of the 3 planned, inside the margin
        return item

    def test_a_kind_finished_in_a_third_of_its_length_is_offered_at_half(self, app: App) -> None:
        for day in (19, 20, 21):
            self.finish_fast(app, day)
        found = asked(app)["learned:beat:speed:Reading"]
        assert found["title"] == "Reading takes you about 50% of the time Friday plans for it"
        assert [o["id"] for o in found["options"]] == ["shorten", "keep"]
        assert app.do("beat_plan")["counts"] == {"faster": 3}

    def test_yes_plans_that_kind_shorter_and_leaves_other_kinds_alone(self, app: App) -> None:
        for day in (19, 20, 21):
            self.finish_fast(app, day)
        assert answer(app, "learned:beat:speed:Reading", "shorten") == "Planning Reading at 50% of its length"
        assert kv_get(app.conn, SHARES) == {"Reading": 0.5}
        app.at("2026-10-26T09:00")
        reading, essay = due_tomorrow(app, 26, "Reading", hours=2), due_tomorrow(app, 26, "Assignment", hours=2)
        planned = {i.id: i.duration_units for i in take_snapshot(app.conn, app.now_utc).items}
        assert (planned[reading], planned[essay]) == (4, 8)  # 2 h → 1 h; the essay keeps its 2 h
        assert app.do("item", id=reading)["item"]["duration_min"] == 120  # what you said is kept as said
        assert "learned:beat:speed:Reading" not in asked(app)

    def test_no_keeps_planning_that_kind_at_full_length(self, app: App) -> None:
        for day in (19, 20, 21):
            self.finish_fast(app, day)
        assert answer(app, "learned:beat:speed:Reading", "keep") == "Planning Reading at full length"
        assert not kv_get(app.conn, SHARES)
        assert "learned:beat:speed:Reading" not in asked(app)


class TestTheQuery:
    def test_it_says_what_friday_learned_and_what_it_asks(self, app: App) -> None:
        three_late_nights(app)
        out = app.do("beat_plan")
        assert (out["on_time"], out["late"]) == (3, 0)
        assert out["counts"] == {"nights": 3}
        assert out["said"] == [
            "You finished 3 of the 3 things your plans showed late on time",
            "3 by working later at night",
        ]
        assert out["asking"] == ["You finish work Friday showed late by working later at night"]
        assert all(f["ways"] == ["nights"] and f["late_hours"] > 0 for f in out["finishes"])

    def test_a_new_user_has_nothing_to_learn(self, app: App) -> None:
        out = app.do("beat_plan")
        assert (out["on_time"], out["late"], out["finishes"], out["said"], out["asking"]) == (0, 0, [], [], [])

    def test_work_done_on_time_without_a_record_is_untold_and_asks_nothing(self, app: App) -> None:
        for day in (19, 20, 21):
            item = shown_late(app, day)
            app.at(f"2026-10-{day + 1:02d}T08:00").do("done", id=item)
        out = app.do("beat_plan")
        assert out["counts"] == {"untold": 3} and out["asking"] == []
