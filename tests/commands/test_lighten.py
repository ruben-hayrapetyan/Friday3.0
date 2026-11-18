"""Lightening a week that holds more than your usual (15 Nov: a client's Load ahead said a week held 1 h more than
they could do, and its button opened what gives when work is late, which said everything fits)."""

from pathlib import Path

import pytest

from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    app = new_app(tmp_path, horizon_days=14)
    app.do("add", title="Essay", duration_min=20 * 60, due="2026-10-25T23:00", firmness="hard")
    # due at the year's end, it goes in this week as soon as there's time (17 Nov); with no due, where it went was
    # anyone's guess, this week or the next
    app.do("add", title="Side project", duration_min=5 * 60, due="2026-12-31T17:00", firmness="hard")
    app.do("add", title="Lab report", duration_min=2 * 60, due="2026-10-26T12:00", firmness="hard")
    app.do("replan")
    return app


def test_flexible_work_in_the_week_is_offered_to_start_after_it_and_applying_it_lightens_the_week(app: App) -> None:
    before = app.do("load", weeks=2)[0]["hours"]
    options = app.do("lighten", start="2026-10-19")["options"]
    # the essay is due that week and the lab report the morning after: neither can leave it on time
    assert [o["action"] for o in options] == ["Start Side project on Mon 26"]
    (side,) = options
    assert 0 < side["hours_moved"] <= 5
    assert side["side_effects"] == ["Most of it goes to the week of Mon 26", "Still done by its due, Thu 31"]
    assert side["steps"] == [{"command": "edit", "input": {"id": 2, "release": "2026-10-26T04:00"}}]
    for step in side["steps"]:
        app.do(step["command"], **step["input"])
    app.do("replan")
    after = app.do("load", weeks=2)
    assert after[0]["hours"] == pytest.approx(before - side["hours_moved"], abs=0.5)
    assert after[1]["hours"] >= side["hours_moved"] - 0.5
    assert app.do("status")["late_items"] == []


def test_a_day_is_lightened_to_the_days_after_it(app: App) -> None:
    # Monday holds 6 h of the essay, due Sunday, and the lab report's 2: as much as a day takes, all work in as soon
    # as there's time, what's due first first (17 Nov; it held 3 h of the essay while only work due a week off went in
    # early). Each can start Tuesday and still be done in time; the side project, due last, isn't on Monday
    options = {o["action"]: o for o in app.do("lighten", start="2026-10-19", days=1)["options"]}
    essay = options["Start Essay on Tue 20"]
    assert essay["hours_moved"] == 6
    assert set(options) <= {"Start Essay on Tue 20", "Start Lab report on Tue 20", "Start Side project on Tue 20"}
    goes, due = essay["side_effects"]
    assert goes.startswith("Most of it goes to ") and due == "Still done by its due, Sun 25"


def test_days_past_what_friday_plans_have_nothing_to_offer(app: App) -> None:
    assert app.do("lighten", start="2027-06-07")["options"] == []
