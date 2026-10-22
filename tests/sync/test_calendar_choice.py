"""Choosing Google calendars in Settings (M12b): the list is every calendar the last sync saw, alphabetized;
`gcal.read` only switches on the first ones; switching one off withdraws what you haven't answered, and back on
or to another kind suggests it afresh."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.core.items import FieldError
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def account() -> FakeGoogle:
    google = FakeGoogle(
        {
            "proj@group": [],
            "school@group": [event("ps", "PS5 due", "2026-10-21T17:00", "2026-10-21T17:00")],
            "todo@group": [],
            "ten@group": [event("x", "Thing", "2026-10-21T10:00", "2026-10-21T11:00")],
        },
        primary="proj@group",
    )
    google.names = {
        "proj@group": "1. Projects",
        "school@group": "4. School",
        "todo@group": "2. To-Do",
        "ten@group": "10. Later",
    }
    return google


def read(app: App, google: FakeGoogle, minutes_later: int = 0) -> None:
    app.conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'sync_now', '1')")
    sync(app.conn, app.now_utc + minutes_later, google=google)


def titles(app: App) -> list[str]:
    return [s["input"]["title"] for s in app.do("inbox")["suggestions"]]


def test_calendars_are_listed_alphabetized_and_gcal_read_switches_on_the_first_ones(app: App) -> None:
    app.do("settings_set", key="gcal", value={"read": ["primary", "4. School"]})
    read(app, account())
    listed = app.do("google_calendars")
    assert [c["name"] for c in listed] == ["1. Projects", "2. To-Do", "4. School", "10. Later"]
    assert [c["name"] for c in listed if c["on"]] == ["1. Projects", "4. School"]
    assert titles(app) == ["PS5"]


def test_switching_a_calendar_off_withdraws_its_suggestions_and_back_on_brings_them(app: App) -> None:
    google = account()
    read(app, google)
    app.do("calendar_set", id="ten@group", on=True)
    read(app, google, minutes_later=1)
    assert titles(app) == ["Thing"]
    app.do("calendar_set", id="ten@group", on=False)
    read(app, google, minutes_later=2)
    assert titles(app) == []
    app.do("calendar_set", id="ten@group", on=True)
    read(app, google, minutes_later=3)
    assert titles(app) == ["Thing"]


def test_a_calendars_kind_reads_its_events_again_that_way(app: App) -> None:
    google = account()
    read(app, google)
    app.do("calendar_set", id="ten@group", on=True)
    read(app, google, minutes_later=1)
    app.do("calendar_set", id="ten@group", kind="Class")
    read(app, google, minutes_later=2)
    assert [s["input"]["preset"] for s in app.do("inbox")["suggestions"]] == ["Class"]
    assert app.do("google_calendars")[3]["kind"] == "Class"
    with pytest.raises(FieldError):
        app.do("calendar_set", id="ten@group", kind="Nonsense")
