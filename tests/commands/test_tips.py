"""Pro tips (#23, 24 Nov): a feature you may be missing, short, sliding in at the bottom right for five seconds; at
most one a day, the same one at most three times a week apart, none once its habit is gone. Each habit the user chose
shows its tip, and a near miss doesn't. Monday 19 Oct 2026, 9am."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def tip(app: App) -> str | None:
    return app.do("tips")["id"]


def event(app: App, title: str, day: int, hour: int = 14) -> None:
    app.do("add", title=title, when="fixed", start=f"2026-10-{day:02d}T{hour:02d}:00",
           end=f"2026-10-{day:02d}T{hour + 1:02d}:00")  # fmt: skip


def test_nothing_to_say_says_nothing(app: App) -> None:
    app.do("add", title="Essay", due="2026-10-23T17:00", duration_min=120)
    assert app.do("tips") == {"id": None, "text": None, "page": None}


def test_work_made_as_events(app: App) -> None:
    event(app, "Study for prelim", 20)
    event(app, "CS 2110 midterm", 21)  # an exam is an event: not counted
    assert tip(app) is None
    event(app, "Essay draft", 22)
    said = app.do("tips")
    assert said == {"id": "work_events", "text": "Add work as a to-do, and Friday finds the time for it.",
                    "page": "/todo"}  # fmt: skip


def test_meals_made_as_events(app: App) -> None:
    event(app, "Lunch", 20, 12)
    event(app, "Lunch with Sam", 21, 12)  # a lunch out is an event
    event(app, "dinner", 21, 18)
    assert tip(app) is None
    event(app, "Breakfast", 22, 8)
    assert tip(app) == "meal_events"


def test_to_dos_with_no_due_date_or_length(app: App) -> None:
    for n in range(4):
        app.do("add", title=f"Thing {n}")
    app.do("add", title="Dated", due="2026-10-23T17:00")
    assert tip(app) is None  # four
    app.do("add", title="Thing 4")
    assert tip(app) == "due_and_length"


def test_work_in_parts_not_a_project(app: App) -> None:
    app.do("add", title="History essay outline", due="2026-10-23T17:00", duration_min=60)
    assert tip(app) is None
    app.do("add", title="History essay draft", due="2026-10-25T17:00", duration_min=180)
    assert tip(app) == "projects"


def test_a_to_do_waiting_for_another_outside_a_project(app: App) -> None:
    a = app.do("add", title="Collect data", due="2026-10-23T17:00", duration_min=60)["item"]["id"]
    b = app.do("add", title="Write up results", due="2026-10-25T17:00", duration_min=60)["item"]["id"]
    assert tip(app) is None
    app.do("depend", item_id=b, depends_on_id=a)
    assert tip(app) == "projects"


def test_a_huge_single_to_do(app: App) -> None:
    app.do("add", title="Thesis chapter", due="2026-11-10T17:00", duration_min=420)
    assert tip(app) is None
    app.do("add", title="Capstone report", due="2026-11-10T17:00", duration_min=600)
    assert tip(app) == "huge"


def test_an_overdue_pile(app: App) -> None:
    for n in range(5):
        app.do("add", title=f"Old reading {n}", due=f"2026-10-{5 + n:02d}T17:00", duration_min=30)
    assert tip(app) == "overdue"


def test_most_blocks_locked(app: App) -> None:
    for n in range(5):
        item = app.do("add", title=f"Problem set {n}", duration_min=60)["item"]["id"]
        app.do("pin", id=item, start=f"2026-10-2{n}T10:00", kind="locked")
    assert tip(app) == "locked"


def finish(app: App, n: int, at: str, title: str = "Reading") -> None:
    for i in range(n):
        item = app.do("add", title=f"{title} {at} {i}", duration_min=30)["item"]["id"]
        app.at(at).do("done", id=item)


def test_never_timing_work(app: App) -> None:
    app.do("rule_add", text="no work after 10pm", strength="Always")  # a week in: no rules tip first
    for day in range(10, 19):
        finish(app, 1, f"2026-10-{day:02d}T{10 + day % 5}:00")
    app.at("2026-10-19T09:00")
    assert tip(app) is None  # nine
    finish(app, 1, "2026-10-18T20:00", "Lab")
    app.at("2026-10-19T09:00")
    assert tip(app) == "timing"


def test_done_all_at_once(app: App) -> None:
    app.do("rule_add", text="no work after 10pm", strength="Always")
    timed = app.at("2026-10-13T10:00").do("add", title="Timed reading", duration_min=30)["item"]["id"]
    app.do("start", id=timed)
    app.at("2026-10-13T10:30").do("stop", id=timed, done=True)  # some work timed: not the timing tip
    finish(app, 5, "2026-10-14T23:00")
    app.at("2026-10-19T09:00")
    assert tip(app) is None  # one night
    finish(app, 5, "2026-10-16T23:30")
    app.at("2026-10-19T09:00")
    assert tip(app) == "done_as_you_go"


def test_no_rules_of_your_own_a_week_in(app: App) -> None:
    app.do("add", title="Essay", due="2026-10-30T17:00", duration_min=60)
    assert tip(app) is None  # day one
    app.at("2026-10-27T09:00")
    assert tip(app) == "rules"
    app.do("rule_add", text="no work after 10pm", strength="Always")
    assert tip(app) is None


def test_one_tip_a_day_each_at_most_three_times_a_week_apart(app: App) -> None:
    for day in (20, 21, 22):
        event(app, "Lunch", day, 12)
    assert tip(app) == "meal_events"
    app.do("tip_shown", id="meal_events")
    assert tip(app) is None  # one a day
    for at, shown in (("2026-10-25T09:00", None), ("2026-10-26T09:00", "meal_events")):
        assert app.at(at).do("tips")["id"] == shown  # a week apart
    app.do("tip_shown", id="meal_events")
    app.at("2026-11-02T09:00").do("tip_shown", id="meal_events")
    assert app.at("2026-11-20T09:00").do("tips")["id"] != "meal_events"  # three times, then never


def test_a_habit_gone_stops_its_tip(app: App) -> None:
    lunches = []
    for day in (20, 21, 22):
        event(app, "Lunch", day, 12)
        lunches.append(app.table("items")[-1]["id"])
    assert tip(app) == "meal_events"
    app.do("drop", id=lunches[0])
    assert tip(app) is None


def test_a_tip_closed_with_x_doesnt_come_back(app: App) -> None:
    for day in (20, 21, 22):
        event(app, "Lunch", day, 12)
    app.do("tip_shown", id="meal_events")
    app.do("tip_shown", id="meal_events", closed=True)  # × while it showed
    assert app.at("2026-10-26T09:00").do("tips")["id"] != "meal_events"  # a week on: not again
    assert app.at("2026-11-20T09:00").do("tips")["id"] != "meal_events"
