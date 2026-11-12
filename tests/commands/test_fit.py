"""Do I have time for this?: a change tried on a copy of the plan and never kept; what fits, what's tight, what would
be late (quick and exact), and other times for an event that makes work late."""

from pathlib import Path

import pytest

from friday.planner.service import replan
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:  # Monday 2026-10-19, 9am
    return new_app(tmp_path)


def busy(app: App, *spans: tuple[str, str]) -> None:
    for start, end in spans:
        app.do("add", title="Lab", when="fixed", start=start, end=end)


def test_a_task_that_fits_says_how_much_room_it_has_and_nothing_is_kept(app: App) -> None:
    items, log = len(app.table("items")), len(app.table("command_log"))
    out = app.do("fit", command="add", input={"text": "essay ~2h due wed 5pm"})
    assert out["verdict"] == "fits" and out["said"].startswith("Fits: ") and out["spare_h"] > 10
    assert (len(app.table("items")), len(app.table("command_log"))) == (items, log)


def test_a_task_with_too_little_room_is_late_and_one_just_fitting_is_tight(app: App) -> None:
    busy(app, ("2026-10-19T09:00", "2026-10-19T20:00"))
    late = app.do("fit", command="add", input={"title": "Problem set", "duration_min": 240, "due": "2026-10-19T22:00"})
    assert late["verdict"] == "late" and late["later"][0]["title"] == "Problem set"
    assert late["said"] == "Would leave Problem set 2 h short of its due"  # 8 to 10pm is all there is
    tight = app.do("fit", command="add", input={"title": "Worksheet", "duration_min": 90, "due": "2026-10-19T22:00"})
    assert tight["verdict"] == "tight" and tight["spare_h"] < 2


def test_an_event_that_makes_work_late_says_what_and_offers_other_times(app: App) -> None:
    # The essay can only be written from 2 to 6pm today; coffee from 2 to 5 leaves it an hour, so it would be two
    # hours late. Tomorrow at the same time takes nothing from it.
    busy(app, ("2026-10-19T09:00", "2026-10-19T14:00"), ("2026-10-19T18:00", "2026-10-19T23:30"))
    app.do("add", title="Essay", duration_min=180, due="2026-10-19T23:00")
    out = app.do("fit", command="add", input={"title": "Coffee", "when": "fixed", "start": "2026-10-19T14:00",
                                              "end": "2026-10-19T17:00"})  # fmt: skip
    assert out["verdict"] == "late" and [x["title"] for x in out["later"]] == ["Essay"]
    assert out["later"][0]["short_h"] == 2.0 and out["said"] == "Would leave Essay 2 h short of its due"
    assert out["instead"][0] == {"start": "2026-10-20T14:00", "end": "2026-10-20T17:00"}


def test_the_exact_check_plans_the_change_and_compares_it_with_the_plan_you_have(app: App) -> None:
    busy(app, ("2026-10-19T09:00", "2026-10-19T14:00"), ("2026-10-19T18:00", "2026-10-19T23:30"))
    app.do("add", title="Essay", duration_min=180, due="2026-10-19T23:00")
    replan(app.conn, app.now_utc)
    late = app.do("fit", command="add", input={"title": "Coffee", "when": "fixed", "start": "2026-10-19T14:00",
                                               "end": "2026-10-19T17:00"}, exact=True)  # fmt: skip
    assert late["exact"] and late["verdict"] == "late" and late["later"][0]["title"] == "Essay"
    fine = app.do("fit", command="add", input={"text": "laundry ~1h"}, exact=True)
    assert fine["verdict"] in ("fits", "tight") and not fine["later"]


def test_work_that_fits_your_free_time_but_not_your_daily_limits_is_tight(app: App) -> None:
    app.do("settings_set", key="daily_cap", value=dict.fromkeys(("mon", "tue", "wed", "thu", "fri", "sat", "sun"), 3))
    out = app.do("fit", command="add", input={"title": "Report", "duration_min": 480, "due": "2026-10-20T17:00"})
    assert (out["verdict"], out["said"]) == ("tight", "Fits in your free time, but not within your daily limits: "
                                                      "check exactly")  # fmt: skip
    assert app.do("fit", command="add", input={"text": "laundry ~1h"})["verdict"] == "fits"  # no due, no limit


def test_the_exact_check_says_when_it_fits_only_with_later_nights(app: App) -> None:
    busy(app, ("2026-10-19T09:00", "2026-10-19T21:00"))
    replan(app.conn, app.now_utc)
    out = app.do("fit", command="add", input={"title": "PS", "duration_min": 150, "due": "2026-10-20T08:00"},
                 exact=True)  # fmt: skip
    assert out["verdict"] == "tight" and out["later_nights"] and not out["later"]
    assert out["said"] == "Fits, but only with later nights than you have now"


def test_an_event_over_twelve_hours_is_offered_no_other_times(app: App) -> None:
    app.do("add", title="Essay", duration_min=180, due="2026-10-19T23:00")
    out = app.do("fit", command="add", input={"title": "Trip", "when": "fixed", "start": "2026-10-19T09:00",
                                              "end": "2026-10-20T09:00"})  # fmt: skip
    assert out["verdict"] == "late" and out["instead"] == []
