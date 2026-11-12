"""What if, each kind of change said in words (a skip, a pin, a shove, a day's limits, an add that can't be made),
a change that makes work less late, and routines left out of when work ends."""

from pathlib import Path

import pytest

from friday.commands import whatif
from friday.planner.service import replan
from tests.commands.helpers import App, new_app
from tests.commands.test_whatif import busy, coffee, essay_day, tried


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    whatif.BEFORE.clear()
    return new_app(tmp_path)


def test_each_kind_of_change_is_said_in_words(app: App) -> None:
    essay = essay_day(app)
    lab = next(i["id"] for i in app.table("items") if i["title"] == "Lab")
    out = tried(
        app,
        ("edit", {"id": essay, "title": "Essay draft"}),
        ("pin", {"id": essay, "start": "2026-10-19T14:00"}),
        ("unpin", {"id": essay}),
        ("skip", {"id": lab}),
        ("shove", {"range": "30m"}),
        ("day_override", {"date": "2026-10-20", "cap_hours": 4}),
        ("repeat", {"id": essay}),
    )
    assert [c["said"] for c in out["changes"]] == [
        "Change Essay draft",
        "Plan Essay draft at Mon 2pm",
        "Let Friday place Essay draft",
        "Skip Lab, Mon 9am",
        "Keep 30m free",
        "Change 2026-10-20's limits",
        "Repeat",
    ]


def test_a_pin_with_no_time_and_a_skip_of_something_unknown_say_what_they_can(app: App) -> None:
    out = tried(app, ("skip", {"id": 99999}), ("add", {"text": ""}))
    skipped, added = out["changes"]
    assert skipped["said"] == "Skip it" and skipped["error"]
    assert added["said"] == "Add an item" and added["error"]
    assert out["said"] == "Nothing to try yet"


def test_a_list_of_ids_from_earlier_changes_is_resolved(app: App) -> None:
    assert whatif.resolved({"ids": [whatif.placeholder(0, 0), 7]}, [[41]]) == {"ids": [41, 7]}


def test_taking_away_what_made_work_late_says_it_is_less_late(app: App) -> None:
    essay_day(app)
    app.do("add", title="Coffee", when="fixed", start="2026-10-19T14:00", end="2026-10-19T17:00")
    replan(app.conn, app.now_utc)
    coffee_id = next(i["id"] for i in app.table("items") if i["title"] == "Coffee")
    out = tried(app, ("drop", {"id": coffee_id}))
    assert [s["title"] for s in out["sooner"]] == ["Essay"] and out["said"].endswith("Essay less late")


def test_routines_are_left_out_of_when_the_days_work_ends(app: App) -> None:
    app.do("series_add", title="Lunch", preset="Routine", every="day", release_offset_min=450, due_offset_min=630,
           min_min=30, ideal_min=30, max_min=30)  # fmt: skip
    busy(app, ("2026-10-19T09:00", "2026-10-19T18:00"))
    replan(app.conn, app.now_utc)
    out = tried(app, coffee("19:00", "20:00"))
    assert out["verdict"] == "fits" and out["later_days"] == []
