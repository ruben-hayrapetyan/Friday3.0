"""Your events, changed in Friday, saved back to Google Calendar (COMBINED.md 69): a change is queued by the command
and sent by the job, the next sync finds nothing new, and a new event lands in the calendar you named."""

import json
from pathlib import Path

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.sim.fakes import FakeGoogle, event
from tests.commands.helpers import App, new_app


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def lecture() -> FakeGoogle:
    return FakeGoogle({"Classes@group": [event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]})


def read(app: App, google: FakeGoogle, minutes_later: int = 0) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    sync(app.conn, app.now_utc + minutes_later, google=google)


def the_lecture(app: App) -> dict:
    return next(i for i in app.table("items") if i["title"].startswith("CS 1110"))


def test_a_change_made_in_friday_is_saved_to_the_calendar_and_not_suggested_back(app: App) -> None:
    google = lecture()
    read(app, google)
    item = the_lecture(app)
    app.do("edit", id=item["id"], title="CS 1110 Lecture (Olin 155)", start="2026-10-20T10:10", end="2026-10-20T11:25")
    assert write_events(app.conn, app.now_utc, google=google) == 1
    saved = google.calendars_by_id["Classes@group"][0]
    assert saved["summary"] == "CS 1110 Lecture (Olin 155)"
    assert saved["start"]["dateTime"].startswith("2026-10-20T10:10")
    read(app, google, minutes_later=60)
    assert app.do("inbox")["suggestions"] == []
    assert [s["status"] for s in app.table("suggestions")] == ["accepted"]  # nothing new read back
    assert the_lecture(app)["title"] == "CS 1110 Lecture (Olin 155)"


def test_deleting_an_event_in_friday_deletes_it_in_the_calendar(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do("drop", id=the_lecture(app)["id"])
    write_events(app.conn, app.now_utc, google=google)
    assert google.calendars_by_id["Classes@group"] == []


def test_a_calendar_you_keep_read_only_is_never_written(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do("calendar_set", id="Classes@group", editable=False)
    app.do("edit", id=the_lecture(app)["id"], title="Renamed here only")
    assert app.table("event_writes") == []
    assert write_events(app.conn, app.now_utc, google=google) == 0


def test_a_new_event_goes_to_the_calendar_you_named_and_follows_it_from_then_on(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do(
        "settings_set",
        key="gcal",
        value={"read": ["Classes"], "trusted": ["Classes"], "new_events_to": "Classes@group"},
    )
    made = app.do("add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00")["item"]
    write_events(app.conn, app.now_utc, google=google)
    titles = [e["summary"] for e in google.calendars_by_id["Classes@group"]]
    assert titles == ["CS 1110 Lecture", "Chess club"]
    read(app, google, minutes_later=60)
    chess = [i for i in app.table("items") if i["title"] == "Chess club" and i["status"] == "todo"]
    assert [i["id"] for i in chess] == [made["id"]]  # read back as the same event, not a second one
    google.calendars_by_id["Classes@group"][1]["summary"] = "Chess club (finals)"
    read(app, google, minutes_later=120)
    assert next(i for i in app.table("items") if i["id"] == made["id"])["title"] == "Chess club (finals)"


def test_undoing_a_change_before_it_is_sent_takes_it_back(app: App) -> None:
    google = lecture()
    read(app, google)
    edit = app.full("edit", payload={"id": the_lecture(app)["id"], "title": "Oops"})
    app.do("undo", command_id=edit.command_id)
    assert write_events(app.conn, app.now_utc, google=google) == 0
    assert google.calendars_by_id["Classes@group"][0]["summary"] == "CS 1110 Lecture"


def test_an_all_day_event_is_written_as_whole_days(app: App) -> None:
    from friday.commands.eventwrites import event_body
    from friday.core.items import Item

    item = Item(title="Fall break", when="fixed", start_utc="2026-10-26T04:00Z", end_utc="2026-10-28T04:00Z", id=1)
    body = event_body(item, "America/New_York")
    assert body["start"] == {"date": "2026-10-26"} and body["end"] == {"date": "2026-10-28"}
    timed = Item(title="Talk", when="fixed", start_utc="2026-10-26T22:00Z", end_utc="2026-10-26T23:00Z", id=2)
    assert event_body(timed, "America/New_York")["start"] == {"dateTime": "2026-10-26T22:00:00Z"}


def test_changes_the_calendar_made_are_never_written_back(app: App) -> None:
    google = lecture()
    read(app, google)
    google.calendars_by_id["Classes@group"][0]["summary"] = "CS 1110 Lecture (moved)"
    read(app, google, minutes_later=60)
    assert app.table("event_writes") == []  # the sync's own edit
    assert google.writes == []


def test_a_new_event_stays_in_friday_without_a_calendar_named(app: App) -> None:
    google = lecture()
    read(app, google)
    app.do("add", title="Chess club", when="fixed", start="2026-10-21T19:00", end="2026-10-21T21:00")
    assert app.table("event_writes") == []


def test_a_failing_write_is_tried_again_then_reported(app: App) -> None:
    from friday.commands.eventwrites import MAX_TRIES, failed_writes

    google = lecture()
    read(app, google)
    app.do("edit", id=the_lecture(app)["id"], title="Renamed")

    class Down:
        def events(self) -> "Down":
            return self

        def patch(self, **_: object) -> "Down":
            raise ConnectionError("Google is down")

    for _ in range(MAX_TRIES):
        assert write_events(app.conn, app.now_utc, google=Down()) == 0
    assert app.table("event_writes")[0]["tries"] == MAX_TRIES
    assert failed_writes(app.conn) == ["Couldn't save Renamed to Google (ConnectionError: Google is down)"]
    assert write_events(app.conn, app.now_utc, google=google) == 0  # given up: not tried again


def test_skipping_one_time_of_a_repeating_event_deletes_that_time(app: App) -> None:
    google = FakeGoogle(
        {"Classes@group": [event("r_1", "Gym", "2026-10-20T07:00", "2026-10-20T08:00", recurringEventId="r"),
                           event("r_2", "Gym", "2026-10-22T07:00", "2026-10-22T08:00", recurringEventId="r")]},
        rules={"r": "FREQ=WEEKLY;BYDAY=TU,TH"},
    )  # fmt: skip
    read(app, google)
    first = next(i for i in app.table("items") if i["title"] == "Gym" and i["start_utc"].startswith("2026-10-20"))
    if first["series_id"] is None:
        pytest.skip("this calendar's repeats come in as separate events")
    app.do("skip", id=first["id"])
    write_events(app.conn, app.now_utc, google=google)
    assert [e["id"] for e in google.calendars_by_id["Classes@group"]] == ["r_2"]


def test_a_new_event_can_name_its_calendar_or_stay_only_in_friday(app: App) -> None:
    # 26 Oct: events made in Friday stayed in Friday. The drawer names the calendar per event; "" keeps it here, even
    # once a default calendar is chosen and it's changed later.
    google = lecture()
    read(app, google)
    party = app.do("add", title="Party", when="fixed", start="2026-10-22T21:00", end="2026-10-22T23:00",
                   calendar="Classes@group")["item"]["id"]  # fmt: skip
    mine = app.do("add", title="Dentist", when="fixed", start="2026-10-23T09:00", end="2026-10-23T10:00",
                  calendar="")["item"]["id"]  # fmt: skip
    assert [(w["item_id"], w["calendar_id"]) for w in app.table("event_writes")] == [(party, "Classes@group")]
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"],
                                              "new_events_to": "Classes@group"})  # fmt: skip
    app.do("edit", id=mine, title="Dentist (Dr. Lee)")
    assert [w["item_id"] for w in app.table("event_writes")] == [party]
    write_events(app.conn, app.now_utc, google=google)
    assert [e["summary"] for e in google.calendars_by_id["Classes@group"]] == ["CS 1110 Lecture", "Party"]


def test_an_event_wears_its_calendar_s_own_colour_and_a_new_one_the_calendar_it_goes_to(app: App) -> None:
    # The Mac and Google say each calendar's colour; with none chosen in Settings, no event wore one.
    google = lecture()
    read(app, google)
    calendars = app.table("kv")
    listed = next(r for r in calendars if r["key"] == "google_calendars")
    rows = [c | {"color": "#0088ff"} for c in json.loads(listed["value"])]
    app.conn.execute("UPDATE kv SET value = ? WHERE key = 'google_calendars'", [json.dumps(rows)])
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-26T00:00")
    (lecture_out,) = [f for f in plan["fixed"] if f["title"].startswith("CS 1110")]
    assert (lecture_out["calendar"], lecture_out["calendar_color"]) == ("Classes", "blue")
    app.do(
        "add", title="Party", when="fixed", start="2026-10-22T21:00", end="2026-10-22T23:00", calendar="Classes@group"
    )
    plan = app.do("plan", start="2026-10-19T00:00", end="2026-10-26T00:00")
    (party,) = [f for f in plan["fixed"] if f["title"] == "Party"]
    assert party["calendar_color"] == "blue"  # on its way to Classes: its colour already
