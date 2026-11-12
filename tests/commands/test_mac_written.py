"""The Mac app's report of a change it made (mac_written) at the edges: a change that isn't waiting says so, and one
reported twice is saved once."""

from pathlib import Path

import pytest

from friday.core.items import FieldError
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import LECTURE, WRITABLE, events, post


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_a_change_that_isnt_waiting_says_so(app: App) -> None:
    with pytest.raises(FieldError, match="no change 7 is waiting"):
        app.do("mac_written", id=7, ok=True)


def test_a_change_reported_twice_is_saved_once(app: App) -> None:
    post(app, [WRITABLE], [LECTURE])
    app.do("edit", id=events(app)["Dentist"]["id"], start="2026-10-20T12:00", end="2026-10-20T13:00")
    (job,) = app.do("mac_writes")
    assert app.do("mac_written", id=job["id"], ok=True)["message"] == "Saved to your calendar"
    assert app.do("mac_written", id=job["id"], ok=True)["message"] == "Already saved"
    assert app.do("mac_writes") == []
