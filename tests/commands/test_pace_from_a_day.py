"""A pace can start on a later day: next week's pace starts next week (found 23 Nov while debugging 0.6.6, in 0.6.5
too: the weekly review's "Pace for next week" set Easy from today, so the rest of the week being reviewed ran at Easy,
and what was timed on those days counted as another pace's). Monday 19 Oct 2026, 9am."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def periods(app: App) -> list[tuple[str, str, str | None]]:
    return [(r["pace_name"], r["start_date"], r["end_date"]) for r in app.table("pace_periods")]


def test_next_weeks_pace_starts_next_week_and_this_week_keeps_its_own(app: App) -> None:
    app.do("pace", name="Push", until="2026-10-25")  # this week, as it is
    out = app.do("pace", name="Easy", start="2026-10-26", for_days=7)  # the review's next week
    assert out["start_date"] == "2026-10-26" and out["end_date"] == "2026-11-01"
    assert periods(app) == [("Push", "2026-10-19", "2026-10-25"), ("Easy", "2026-10-26", "2026-11-01")]
    assert out["message"] == "Easy pace, Mon Oct 26 through Sun Nov 1. Then back to Normal."


def test_next_week_at_the_usual_pace_ends_this_weeks_on_sunday(app: App) -> None:
    app.do("pace", name="Push")  # until changed
    app.do("pace", name="Normal", start="2026-10-26", for_days=7)
    assert periods(app) == [("Push", "2026-10-19", "2026-10-25")]


def test_a_start_before_today_is_refused(app: App) -> None:
    with pytest.raises(FieldError, match="before today"):
        app.do("pace", name="Easy", start="2026-10-18", for_days=7)


def test_without_a_start_it_is_from_today_as_before(app: App) -> None:
    out = app.do("pace", name="Easy", for_days=7)
    assert out["start_date"] == "2026-10-19" and out["end_date"] == "2026-10-25"
