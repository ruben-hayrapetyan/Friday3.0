"""A test Friday never changes a real calendar (29 Oct, Friday Test: a brand-new user's Friday beside yours, which may
be signed in to Google with your real account). With FRIDAY_CALENDARS_READ_ONLY=1 the Calendar API only reads: your
events still come in, a change made in Friday is refused as Google failing would be (kept, then said in the status
line), and the plan is never published into a calendar of yours."""

from pathlib import Path

import pytest
from google.oauth2.credentials import Credentials

from friday.commands.eventwrites import MAX_TRIES, failed_writes, write_events
from friday.commands.fetching import sync
from friday.commands.google import publish_plan
from friday.planner.service import replan
from friday.sim.fakes import FakeGoogle, event
from friday.sync import google_auth
from friday.sync.google_auth import Reading, ReadOnlyCalendars
from tests.commands.helpers import App, new_app

REFUSED = "ReadOnlyCalendars: a test Friday never changes a real calendar"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def lecture() -> FakeGoogle:
    return FakeGoogle({"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]})


def read(app: App, google: object) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc, google=google)


def test_your_events_still_come_in(app: App) -> None:
    read(app, Reading(lecture()))
    assert [i["title"] for i in app.table("items")] == ["CS 1110 Lecture"]


def test_a_change_made_in_friday_never_reaches_google_and_the_status_line_says_so(app: App) -> None:
    google = lecture()
    read(app, google)
    lecture_id = app.table("items")[0]["id"]
    app.do("edit", id=lecture_id, title="Renamed")
    app.do("add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00")
    for _ in range(MAX_TRIES):
        assert write_events(app.conn, app.now_utc, google=Reading(google)) == 0
    assert google.writes == []
    assert [e["summary"] for e in google.calendars_by_id["Classes@group"]] == ["CS 1110 Lecture"]
    assert failed_writes(app.conn) == [f"Couldn't save Renamed to Google ({REFUSED})"]
    app.do("drop", id=lecture_id)
    for _ in range(MAX_TRIES):
        write_events(app.conn, app.now_utc, google=Reading(google))
    assert google.calendars_by_id["Classes@group"] != [] and google.writes == []  # a delete is refused too


def test_the_plan_is_never_published_into_your_google(app: App) -> None:
    app.do("add", text="essay due wed 17:00 ~3h")
    replan(app.conn, app.now_utc)
    app.do("settings_set", key="gcal", value={"publish": True, "publish_debounce_s": 0})
    google = FakeGoogle()
    with pytest.raises(ReadOnlyCalendars):
        publish_plan(app.conn, app.now_utc, google=Reading(google))
    assert google.calendars_by_id == {} and google.writes == []


def real_api() -> object:
    """Google's own client, built offline from the description it ships with; nothing is sent."""
    from googleapiclient.discovery import build  # noqa: PLC0415

    return build("calendar", "v3", credentials=Credentials(token="t"), cache_discovery=False, static_discovery=True)


@pytest.mark.parametrize(
    ("part", "change"),
    [
        ("events", "insert"), ("events", "patch"), ("events", "update"), ("events", "delete"), ("events", "move"),
        ("events", "import_"), ("events", "quickAdd"), ("events", "watch"), ("calendars", "insert"),
        ("calendars", "patch"), ("calendars", "update"), ("calendars", "delete"), ("calendars", "clear"),
        ("calendarList", "insert"), ("calendarList", "patch"), ("calendarList", "update"), ("calendarList", "delete"),
    ],
)  # fmt: skip
def test_every_change_google_s_client_offers_is_refused(part: str, change: str) -> None:
    api = Reading(real_api())
    with pytest.raises(ReadOnlyCalendars):
        getattr(getattr(api, part)(), change)


def test_reading_goes_through_google_s_client_unchanged() -> None:
    api = Reading(real_api())
    request = api.events().list(calendarId="primary", singleEvents=True)
    assert request.api.uri.startswith("https://www.googleapis.com/calendar/v3/calendars/primary/events")
    assert request.api.method == "GET"
    assert api.calendarList().list().api.method == "GET" and api.calendars().get(calendarId="x").api.method == "GET"


def test_only_a_test_friday_reads_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google_auth, "credentials", lambda *_: Credentials(token="t"))
    monkeypatch.delenv(google_auth.READ_ONLY, raising=False)
    assert not isinstance(google_auth.calendar(tmp_path), Reading)  # yours writes as before
    monkeypatch.setenv(google_auth.READ_ONLY, "1")
    assert isinstance(google_auth.calendar(tmp_path), Reading)
    monkeypatch.setattr(google_auth, "credentials", lambda *_: None)
    assert google_auth.calendar(tmp_path) is None  # not connected: nothing to read either
