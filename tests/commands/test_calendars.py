"""Your calendars' settings (calendar_set) and the calendar view (calendar): a calendar's events trusted to skip the
inbox, and no calendar to draw before your sleep is set."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.db import connect
from friday.core.items import FieldError
from friday.sim.fakes import FakeGoogle
from tests.commands.helpers import MONDAY_9, TZ, App, new_app


def test_a_calendar_can_be_trusted_or_not_without_switching_it_on(tmp_path: Path) -> None:
    app = new_app(tmp_path)
    sync(app.conn, app.now_utc, google=FakeGoogle({"Classes@group": []}))
    assert app.do("calendar_set", id="Classes@group", trusted=True)["message"] == "Saved Classes"
    (source,) = [s for s in app.table("sources") if s["kind"] == "gcal"]
    assert (source["trusted"], source["enabled"]) == (1, 0)
    app.do("calendar_set", id="Classes@group", trusted=False)
    assert app.table("sources")[-1]["trusted"] == 0


def test_the_calendar_waits_for_your_sleep_to_be_set(tmp_path: Path) -> None:
    app = App(connect(tmp_path / "friday.db"), 0)
    app.at(MONDAY_9).do("settings_set", key="time", value={"timezone": TZ})
    with pytest.raises(FieldError, match="sleep: not set yet"):
        app.do("calendar")
