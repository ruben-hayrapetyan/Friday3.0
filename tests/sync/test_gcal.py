"""Google Calendar (DESIGN §22.2–22.3): calendars you pick are read into fixed items (a trusted one straight in),
declined and cancelled events are left out or dropped, and the plan is published one way to a "Friday" calendar."""

from pathlib import Path

import pytest

from friday.commands.fetching import sync
from friday.commands.google import publish_plan
from friday.planner.service import replan
from friday.server.main import main
from friday.sim.fakes import FakeGoogle, event
from friday.sync import google_auth
from tests.commands.helpers import App, new_app

ME = {"self": True, "responseStatus": "declined"}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def classes() -> list[dict]:
    return [
        event("a1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15"),
        event("a2", "CS 1110 Lecture", "2026-10-22T10:00", "2026-10-22T11:15"),
        event("x", "Club social", "2026-10-21T18:00", "2026-10-21T19:00", attendees=[ME]),
        {"id": "h", "summary": "Fall break", "start": {"date": "2026-10-26"}, "end": {"date": "2026-10-28"}},
    ]


def read(app: App, google: FakeGoogle, trusted: bool, minutes_later: int = 0) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"] if trusted else []})
    sync(app.conn, app.now_utc + minutes_later, google=google)


def fixed(app: App) -> list[tuple[str, str]]:
    """Open fixed items (the `items` query lists only to-dos)."""
    return [(i["title"], i["start_utc"]) for i in app.table("items") if i["status"] == "todo"]


def test_a_trusted_calendars_events_go_in_and_declined_or_all_day_ones_dont(app: App) -> None:
    read(app, FakeGoogle({"Classes@group": classes()}), trusted=True)
    assert fixed(app) == [("CS 1110 Lecture", "2026-10-20T14:00Z"), ("CS 1110 Lecture", "2026-10-22T14:00Z")]
    assert app.do("inbox")["suggestions"] == []


def test_a_cancelled_event_drops_the_item_it_made(app: App) -> None:
    google = FakeGoogle({"Classes@group": classes()})
    read(app, google, trusted=True)
    del google.calendars_by_id["Classes@group"][1]
    read(app, google, trusted=True, minutes_later=60)
    assert fixed(app) == [("CS 1110 Lecture", "2026-10-20T14:00Z")]
    assert {r["actor"] for r in app.table("command_log") if r["command"] == "suggestion_accept"} == {"sync:Classes"}


def test_an_untrusted_calendar_waits_in_the_inbox_and_a_withdrawn_event_leaves_it(app: App) -> None:
    google = FakeGoogle({"Classes@group": classes()})
    read(app, google, trusted=False)
    assert len(app.do("inbox")["suggestions"]) == 2 and fixed(app) == []
    google.calendars_by_id["Classes@group"].pop(0)
    read(app, google, trusted=False, minutes_later=60)
    assert [s["input"]["start"] for s in app.do("inbox")["suggestions"]] == ["2026-10-22T10:00"]


def test_the_plan_is_published_once_per_change_and_google_edits_are_overwritten(app: App) -> None:
    app.do("add", text="essay due wed 17:00 ~3h")
    replan(app.conn, app.now_utc)
    app.do("settings_set", key="gcal", value={"publish": True, "publish_debounce_s": 0})
    google = FakeGoogle()
    assert publish_plan(app.conn, app.now_utc, google=google)
    (calendar,) = google.calendars_by_id
    published = google.calendars_by_id[calendar]
    assert published and all(e["summary"] == "essay" for e in published)
    assert not publish_plan(app.conn, app.now_utc + 1, google=google)  # the same plan
    published.append(event("mine", "Lunch", "2026-10-19T12:00", "2026-10-19T13:00"))
    published[0]["summary"] = "renamed in Google"
    google.writes.clear()
    replan(app.conn, app.now_utc + 2)
    assert publish_plan(app.conn, app.now_utc + 2, google=google)
    assert sorted(e["summary"] for e in published) == ["essay"] * len(published)
    assert google.writes.count("delete") >= 1 and "insert" not in google.writes  # unchanged blocks kept their events


def test_google_calendars_lists_each_accounts_names_for_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="google-login"):
        main(["--data-dir", str(tmp_path), "google-calendars"])
    google = {
        "me@gmail.com": FakeGoogle({"me@gmail.com": [], "Classes@group": []}, primary="me@gmail.com"),
        "student@school.edu": FakeGoogle({"student@school.edu": [], "dsa@group": []}, names={"dsa@group": "DSA"}),
    }
    google["me@gmail.com"].names["me@gmail.com"] = "Sam"
    for account in google:
        google_auth.rewrite(tmp_path, lambda found, saved, account=account: saved | {account: {"token": "t"}})
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: google[account])
    main(["--data-dir", str(tmp_path), "google-calendars"])
    shown = capsys.readouterr().out
    assert "'primary'  (also: Sam)" in shown and "'Classes'" in shown and "id Classes@group" in shown
    assert (
        shown.index("me@gmail.com:")
        < shown.index("'Classes'")
        < shown.index("student@school.edu:")
        < shown.index("'DSA'")
    )
