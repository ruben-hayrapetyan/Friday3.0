"""Things that run by themselves keep off your meals too, when you say so (23 Nov: the user typed "Things that can
happen during other events can't happen during meals", meaning laundry and the like; it was misread as "Meals are never
skipped for work"; their choice: off the meal as it's planned that day, not its whole window). The rule keeps a run's
time off events and the night; with meals, off each meal where the plan puts it: planned, then, where a run crosses a
planned meal, planned again with that meal's time kept clear of it. Monday 19 Oct 2026, 9am."""

from pathlib import Path

import pytest

from friday.core.rule_text import read, sentence
from friday.core.time import parse_local, to_utc
from friday.planner.service import replan
from tests.commands.helpers import TZ, App, new_app

SAID = "Things that can happen during other events can't happen during meals"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path, horizon_days=1)


def minute(local: str) -> int:
    return to_utc(parse_local(local), TZ)


def a_full_day(app: App) -> int:
    """Classes all day but 11am–3pm, when lunch (30 min, 11:30–2:30) and a 2-hour laundry both fit; laundry due tonight.
    Planned unaware, laundry ran 11am–1pm and lunch 11:30–12 inside it."""
    app.do("add", title="Class", when="fixed", start="2026-10-19T09:00", end="2026-10-19T11:00")
    app.do("add", title="Lab", when="fixed", start="2026-10-19T15:00", end="2026-10-19T23:30")
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=30, ideal_min=30, max_min=30)  # fmt: skip
    return app.do("add", text="laundry ~2h runs by itself due today 11:30pm")["item"]["id"]


def spans(app: App, item: int) -> list[tuple[int, int]]:
    return [(minute(b["start"]), minute(b["end"])) for b in app.do("plan")["blocks"] if b["item_id"] == item]


def test_the_sentence_reads_as_keeping_runs_off_meals() -> None:
    reading, strength = read(SAID)
    assert reading is not None and reading.kind == "runs_while_working" and "meals" in (reading.events or ())
    said = "Things that run by themselves run while you work, not during events, meals or your sleep"
    assert sentence(reading) == said


def test_laundry_runs_around_lunch_as_planned(app: App) -> None:
    laundry = a_full_day(app)
    app.do("rule_add", text=SAID, strength="Always")
    replan(app.conn, app.now_utc)
    [(start, _)] = spans(app, laundry)
    running = (start + 15, start + 120)  # its first quarter hour needs you; then it runs until it's done
    lunch = [i["id"] for i in app.table("items") if i["title"] == "Lunch" and i["occurrence_date"] == "2026-10-19"]
    eating = spans(app, lunch[0])
    assert eating, "lunch is planned"
    assert not any(lo < running[1] and running[0] < hi for lo, hi in eating), (running, eating)


def test_without_meals_in_the_rule_only_events_and_the_night_count() -> None:
    reading, _ = read("things that run by themselves only while I'm working")
    assert reading is not None and "meals" not in (reading.events or ())


def solved_with(app: App, text: str):  # noqa: ANN201
    from friday.planner.snapshot import take_snapshot  # noqa: PLC0415
    from friday.planner.solve import solve  # noqa: PLC0415

    app.do("rule_add", text=text, strength="Always")
    return solve(take_snapshot(app.conn, app.now_utc), warm=False)


def meal_slots(solved) -> list[int]:  # noqa: ANN001
    return [s for r in solved.inp.settings["rules"] if r.type == "runs_while_working"
            for s in (r.params or {}).get("meal_slots", [])]  # fmt: skip


def test_a_day_with_no_clash_is_planned_once(app: App) -> None:
    """Room for both apart (free 11:30am–3:30pm): nothing is kept clear, no plan made again."""
    app.do("add", title="Class", when="fixed", start="2026-10-19T09:00", end="2026-10-19T11:30")
    app.do("add", title="Lab", when="fixed", start="2026-10-19T15:30", end="2026-10-19T23:30")
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=30, ideal_min=30, max_min=30)  # fmt: skip
    app.do("add", text="laundry ~2h runs by itself due today 11:30pm")
    assert meal_slots(solved_with(app, SAID)) == []


def test_without_meals_the_rule_lets_a_run_cross_lunch(app: App) -> None:
    a_full_day(app)
    assert meal_slots(solved_with(app, "things that run by themselves only while I'm working")) == []


def test_the_rules_page_says_what_it_does(app: App) -> None:
    effect = app.do("rule_read", text=SAID)["effect"]
    assert "misses your events, your meals as they're planned and your sleep" in effect
    assert "No event has those words" not in effect  # "meals" isn't an event's name
