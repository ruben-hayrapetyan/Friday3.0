"""A repeat deleted in Friday goes from its calendar from then on (8 Nov: twenty-two yearly birthdays, to be deleted
here, would have left every later year in Google: the Mac app deleted only the one time it was given). Black box
through `series_delete` and what the Mac app and Google are sent, then Google's side inside. Monday 2026-10-19."""

from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle, event
from friday.sync import gcal
from tests.commands.helpers import App, new_app
from tests.sync.test_mac_calendars import GMAIL, LECTURE, WRITABLE, creates, every_time, post, written


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def birthday_on_the_mac(app: App) -> int:
    """Remy's birthday made here, yearly, and made by the Mac app on your Gmail calendar."""
    post(app, [GMAIL], [])
    app.do("settings_set", key="gcal", value={"new_events_to": "gmail-cal"})
    made = app.do("add", title="Remy's Birthday", when="fixed", start="2026-10-22T00:00", end="2026-10-23T00:00",
                  every="rrule:FREQ=YEARLY", after=[], before=[], exceptions=[])  # fmt: skip
    (job,) = creates(app)
    written(app, job, eid="ray1", cid="gmail-cal", title="Remy's Birthday", start="2026-10-22T00:00",
            end="2026-10-23T00:00")  # fmt: skip
    return made["series_id"]


class TestBlackBox:
    def test_a_yearly_birthday_deleted_here_goes_from_the_mac_every_year(self, app: App) -> None:
        app.do("series_delete", id=birthday_on_the_mac(app))
        (job,) = app.do("mac_writes")
        assert job["op"] == "delete_from" and job["event"].startswith("ray1") and job["calendar"] == "gmail-cal"
        app.do("mac_written", id=job["id"], ok=True)
        assert app.do("mac_writes") == [] and every_time(app, "Remy's Birthday") == []

    def test_one_time_skipped_or_dropped_is_still_only_that_time(self, app: App) -> None:
        birthday_on_the_mac(app)
        (ray,) = every_time(app, "Remy's Birthday")
        app.do("skip", id=ray["id"])
        assert [j["op"] for j in app.do("mac_writes")] == ["delete"]

    def test_an_event_that_doesnt_repeat_is_deleted_as_before(self, app: App) -> None:
        post(app, [WRITABLE], [LECTURE])
        dentist = next(i for i in every_time(app, "Dentist"))
        app.do("drop", id=dentist["id"])
        assert [j["op"] for j in app.do("mac_writes")] == ["delete"]

    def test_on_google_each_time_made_here_goes(self, app: App) -> None:
        google = FakeGoogle({"Classes@group": []})
        app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"],
                                                  "new_events_to": "Classes@group"})  # fmt: skip
        sync(app.conn, app.now_utc, google=google)
        series = app.do("add", title="Gym", when="fixed", start="2026-10-20T07:30", end="2026-10-20T09:00",
                        every="week")["series_id"]  # fmt: skip
        write_events(app.conn, app.now_utc, google=google)
        assert google.calendars_by_id["Classes@group"]
        app.do("series_delete", id=series)
        assert {w["op"] for w in app.table("event_writes") if w["done_utc"] is None} == {"delete_from"}
        write_events(app.conn, app.now_utc, google=google)
        assert google.calendars_by_id["Classes@group"] == []


def weekly_gym() -> FakeGoogle:
    times = [
        event(f"g_{n}", "Gym", f"2026-10-{day}T07:00", f"2026-10-{day}T08:00", recurringEventId="g")
        for n, day in enumerate((20, 27), start=1)
    ] + [event("g_3", "Gym", "2026-11-03T07:00", "2026-11-03T08:00", recurringEventId="g")]
    return FakeGoogle({"c": times}, rules={"g": "FREQ=WEEKLY;BYDAY=TU"})


class TestGoogleInside:
    def test_from_its_first_time_the_whole_repeat_goes(self) -> None:
        google = weekly_gym()
        gcal.delete_from(google, "c", "g_1")
        assert google.calendars_by_id["c"] == [] and google.writes == ["delete"]

    def test_from_a_later_time_the_repeat_ends_just_before_it(self) -> None:
        google = weekly_gym()
        gcal.delete_from(google, "c", "g_2")
        assert [e["id"] for e in google.calendars_by_id["c"]] == ["g_1"]
        assert google.rules["g"] == "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261027T105959Z"

    def test_an_event_that_doesnt_repeat_or_is_gone_already(self) -> None:
        google = FakeGoogle({"c": [event("one", "Dentist", "2026-10-20T10:00", "2026-10-20T11:00")]})
        gcal.delete_from(google, "c", "one")
        gcal.delete_from(google, "c", "one")
        assert google.calendars_by_id["c"] == []

    def test_its_end_comes_before_the_time_for_days_and_for_times(self) -> None:
        assert gcal.ended_before("RRULE:FREQ=YEARLY", {"date": "2027-02-01"}) == "RRULE:FREQ=YEARLY;UNTIL=20270131"
        assert (
            gcal.ended_before("RRULE:FREQ=WEEKLY;COUNT=9;BYDAY=TU", {"dateTime": "2026-11-03T07:00:00-05:00"})
            == "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20261103T115959Z"
        )
        assert gcal.ended_before("RRULE:FREQ=DAILY;UNTIL=20271231", {"dateTime": "2026-11-03T12:00:00Z"}) == (
            "RRULE:FREQ=DAILY;UNTIL=20261103T115959Z"
        )
