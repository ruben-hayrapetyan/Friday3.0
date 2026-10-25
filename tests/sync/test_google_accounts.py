"""Several Google accounts at once (a personal one and a school one): each account's token is kept under its address
and the one from before still counts, each calendar is read and written through its own account, a calendar both
accounts have comes in once, mail is read from every account that allows it (a message both got, once), and
removing an account stops its calendars and mail while what they brought in stays."""

import json
from pathlib import Path
from typing import Any

import pytest

from friday.commands.eventwrites import write_events
from friday.commands.fetching import sync
from friday.commands.mail import ELSEWHERE
from friday.planner.store import kv_get
from friday.server.jobs import send_event_writes
from friday.sim.fakes import FakeGmail, FakeGoogle, event, mail
from friday.sync import google_auth
from tests.commands.helpers import App, new_app
from tests.ingest.fakes import FakeClient

ME, SCHOOL = "me@gmail.com", "student@school.edu"
ALL = (*google_auth.LOGIN_SCOPES, google_auth.GMAIL_SCOPE)


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def personal() -> FakeGoogle:
    family = [event("f1", "Family dinner", "2026-10-21T18:00", "2026-10-21T19:30")]
    return FakeGoogle({ME: [], "family@group": family}, primary=ME, names={"family@group": "Family"})


def school() -> FakeGoogle:
    lectures = [event("l1", "CS 1110 Lecture", "2026-10-20T10:00", "2026-10-20T11:15")]
    return FakeGoogle({SCHOOL: [], "classes@group": lectures}, primary=SCHOOL, names={"classes@group": "Classes"})


def read(app: App, google: Any = None, minutes_later: int = 0, **apis: Any) -> None:
    app.conn.execute("INSERT OR REPLACE INTO kv (user_id, key, value) VALUES (1, 'sync_now', '1')")
    sync(
        app.conn,
        app.now_utc + minutes_later,
        google=google,
        client=FakeClient({"is_syllabus": False, "items": []}),
        **apis,
    )


def keep_token(folder: Path, account: str, scopes: tuple[str, ...] = ALL) -> None:
    google_auth.rewrite(folder, lambda found, saved: saved | {account: {"token": account, "scopes": list(scopes)}})


def fixed(app: App) -> list[str]:
    return sorted(i["title"] for i in app.table("items") if i["status"] == "todo")


def errors(app: App) -> dict[str, str | None]:
    return {s["name"]: s["last_error"] for s in app.table("sources")}


def test_each_accounts_token_is_kept_apart_and_the_one_from_before_still_counts(tmp_path: Path) -> None:
    secrets = google_auth.secrets_file(tmp_path)
    secrets.write_text(json.dumps({"google": {"token": "old", "scopes": ["a"]}, "anthropic": "kept"}))
    assert google_auth.tokens(tmp_path) == {google_auth.LEGACY: {"token": "old", "scopes": ["a"]}}
    assert google_auth.connected(tmp_path, ("a",)) and not google_auth.connected(tmp_path, ("b",))
    keep_token(tmp_path, SCHOOL, ("b",))
    assert google_auth.accounts(tmp_path) == [google_auth.LEGACY, SCHOOL]
    assert google_auth.accounts(tmp_path, ("b",)) == [SCHOOL]
    google_auth.adopt(tmp_path, ME)  # the sync found its address: it moves under it, still first
    assert list(google_auth.tokens(tmp_path)) == [ME, SCHOOL]
    assert google_auth.tokens(tmp_path)[ME]["token"] == "old"
    google_auth.remove(tmp_path, ME)
    assert list(google_auth.tokens(tmp_path)) == [SCHOOL]
    assert json.loads(secrets.read_text())["anthropic"] == "kept"  # whatever else the file keeps stays


def test_the_token_from_before_is_read_and_named_by_its_primary_calendar(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    google_auth.secrets_file(tmp_path).write_text(json.dumps({"google": {"token": "old", "scopes": ["x"]}}))
    google = school()
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: google)
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    read(app, folder=tmp_path)
    assert fixed(app) == ["CS 1110 Lecture"]
    assert list(google_auth.tokens(tmp_path)) == [SCHOOL]  # kept under its address from now on
    assert {c["account"] for c in kv_get(app.conn, "google_calendars")} == {SCHOOL}
    read(app, folder=tmp_path, minutes_later=60)  # and read as that account
    assert errors(app)["Classes"] is None


def test_a_calendar_listed_before_accounts_were_kept_is_still_read(app: App) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    app.conn.execute(  # as an older Friday listed them: no account
        "INSERT INTO kv (user_id, key, value) VALUES (1, 'google_calendars', ?)",
        [json.dumps([{"id": "classes@group", "name": "Classes", "primary": False, "writable": True}])],
    )
    read(app, school())
    assert fixed(app) == ["CS 1110 Lecture"] and errors(app)["Classes"] is None


def test_each_calendar_is_read_through_its_own_account(app: App) -> None:
    app.do("settings_set", key="gcal", value={"read": ["Family", "Classes"], "trusted": ["Family", "Classes"]})
    read(app, {ME: personal(), SCHOOL: school()})  # a stand-in asked for another's calendar fails: none does
    assert fixed(app) == ["CS 1110 Lecture", "Family dinner"]
    assert errors(app) == {"Family": None, "Classes": None}
    listed = {c["name"]: c["account"] for c in app.do("google_calendars")}
    assert listed == {"me": ME, "Family": ME, "student": SCHOOL, "Classes": SCHOOL}


def test_an_account_that_cant_be_read_says_why_on_its_calendars_and_the_other_goes_on(app: App) -> None:
    class Expired(FakeGoogle):
        def calendarList(self) -> FakeGoogle:  # noqa: N802 (Google's name)
            raise RuntimeError("RefreshError: invalid_grant")

    app.do("settings_set", key="gcal", value={"read": ["Family", "Classes"], "trusted": ["Family", "Classes"]})
    read(app, {ME: personal(), SCHOOL: school()})
    read(app, {ME: personal(), SCHOOL: Expired()}, minutes_later=60)
    assert "invalid_grant" in (errors(app)["Classes"] or "") and errors(app)["Family"] is None
    assert "Classes" in {c["name"] for c in app.do("google_calendars")}  # not taken for gone


def test_a_calendar_both_accounts_have_comes_in_once_through_the_one_that_may_change_it(app: App) -> None:
    club = [event("c1", "Robotics club", "2026-10-22T19:00", "2026-10-22T20:00")]
    mine = FakeGoogle({ME: [], "club@group": club}, names={"club@group": "Club"}, roles={"club@group": "reader"})
    theirs = FakeGoogle({SCHOOL: [], "club@group": list(club)}, names={"club@group": "Club"})
    app.do("settings_set", key="gcal", value={"read": ["Club"], "trusted": ["Club"]})
    read(app, {ME: mine, SCHOOL: theirs})
    (shared,) = [c for c in app.do("google_calendars") if c["name"] == "Club"]
    assert shared["account"] == SCHOOL and shared["writable"]
    assert fixed(app) == ["Robotics club"]


def test_calendars_of_the_same_name_in_two_accounts_are_told_apart(app: App) -> None:
    mine = FakeGoogle({ME: [], "p1@group": []}, names={"p1@group": "Personal"})
    theirs = FakeGoogle({SCHOOL: [], "p2@group": []}, names={"p2@group": "Personal"})
    read(app, {ME: mine, SCHOOL: theirs})
    app.do("calendar_set", id="p1@group", on=True)
    app.do("calendar_set", id="p2@group", on=True)
    assert sorted(s["name"] for s in app.table("sources")) == ["Personal", f"Personal ({SCHOOL})"]


def test_a_change_is_saved_through_the_account_its_calendar_is_in(app: App) -> None:
    mine, theirs = personal(), school()
    app.do("settings_set", key="gcal", value={"read": ["Classes"], "trusted": ["Classes"]})
    read(app, {ME: mine, SCHOOL: theirs})
    lecture = next(i for i in app.table("items") if i["title"] == "CS 1110 Lecture")
    app.do("edit", id=lecture["id"], title="CS 1110 Lecture (Olin 155)")
    app.do("settings_set", key="gcal", value={"new_events_to": "family@group"})
    app.do("add", text="Call grandma thu 18:00-18:30", when="fixed")
    assert write_events(app.conn, app.now_utc, google={ME: mine, SCHOOL: theirs}) == 2
    assert theirs.writes == ["patch"] and mine.writes == ["insert"]


def test_changes_for_an_account_that_must_sign_in_again_wait_and_the_status_says_which(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine, theirs = personal(), school()
    keep_token(tmp_path, ME, google_auth.CALENDAR_SCOPES)  # signed in before "Edit here"
    keep_token(tmp_path, SCHOOL)
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: {ME: mine, SCHOOL: theirs}[account])
    app.do("settings_set", key="gcal", value={"read": ["Family", "Classes"], "trusted": ["Family", "Classes"]})
    read(app, folder=tmp_path)
    for item in app.table("items"):
        app.do("edit", id=item["id"], title=item["title"] + "!")
    send_event_writes(app.conn, app.now_utc, {}, None, None, tmp_path / "backups", 1)  # type: ignore[arg-type]
    assert theirs.writes == ["patch"] and mine.writes == []
    assert [w["tries"] for w in app.table("event_writes") if w["done_utc"] is None] == [0]  # held, not failing
    assert ME in kv_get(app.conn, "server_problems")["event_writes"]


def gmail_of(*messages: dict[str, Any]) -> FakeGmail:
    return FakeGmail(list(messages))


def test_mail_is_read_from_each_account_and_a_message_both_got_is_read_once(app: App) -> None:
    app.do("settings_set", key="gmail", value={"enabled": True, "sender_domains": ["cornell.edu"]})
    notice = ("Prof <prof@cs.cornell.edu>", "Prelim moved", "<p>The prelim is now Thursday.</p>")
    mine = gmail_of(mail("a1", *notice), mail("a2", "Mom <mom@gmail.com>", "Dinner", "<p>Dinner by Sunday?</p>"))
    theirs = gmail_of(mail("b1", *notice))  # the same message, forwarded from school
    read(app, mail={ME: mine, SCHOOL: theirs})
    sources = {s["id"]: s for s in app.table("sources")}
    got = {
        (sources[r["source_id"]]["name"], r["external_id"]): (r["status"], r["error"]) for r in app.table("raw_inputs")
    }
    assert got[("Gmail", "a1")] == ("extracted", None)
    assert got[(f"Gmail ({SCHOOL})", "b1")] == ("ignored", ELSEWHERE)
    assert got[("Gmail", "a2")][0] == "extracted"


def test_one_accounts_mail_failing_leaves_the_others(app: App) -> None:
    class Down(FakeGmail):
        def list(self, userId: str, q: str, maxResults: int) -> Any:  # noqa: N803
            raise RuntimeError("RefreshError: invalid_grant")

    app.do("settings_set", key="gmail", value={"enabled": True, "sender_domains": ["cornell.edu"]})
    read(app, mail={ME: gmail_of(mail("a1", "Prof <p@cornell.edu>", "PS5", "<p>Due Friday</p>")), SCHOOL: Down([])})
    assert errors(app)["Gmail"] is None and "invalid_grant" in (errors(app)[f"Gmail ({SCHOOL})"] or "")


def test_only_accounts_that_allowed_gmail_are_read(app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app.do("settings_set", key="gmail", value={"enabled": True})
    keep_token(tmp_path, ME)
    keep_token(tmp_path, SCHOOL, google_auth.LOGIN_SCOPES)  # Gmail not allowed for this one
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: {ME: personal(), SCHOOL: school()}[account])
    monkeypatch.setattr(google_auth, "gmail", lambda folder, account: gmail_of())
    read(app, folder=tmp_path)
    assert [s["config"] for s in app.table("sources") if s["kind"] == "gmail"] == [json.dumps({"account": ME})]


def test_removing_an_account_stops_its_calendars_and_mail_and_what_they_brought_stays(
    app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    google = {ME: personal(), SCHOOL: school()}
    google[SCHOOL].calendars_by_id["seminars@group"] = [event("s1", "Seminar", "2026-10-23T16:00", "2026-10-23T17:00")]
    google[SCHOOL].names["seminars@group"] = "Seminars"
    for account in google:
        keep_token(tmp_path, account)
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: google[account])
    monkeypatch.setattr(google_auth, "gmail", lambda folder, account: gmail_of())
    app.do("settings_set", key="gmail", value={"enabled": True})
    app.do("settings_set", key="gcal", value={"read": ["Family", "Classes", "Seminars"], "trusted": ["Classes"]})
    read(app, folder=tmp_path)
    assert fixed(app) == ["CS 1110 Lecture"] and len(app.do("inbox")["suggestions"]) == 2  # family dinner, seminar

    status = app.do("google_remove", account=SCHOOL)
    assert [a["email"] for a in status["accounts"]] == [ME]
    assert {c["account"] for c in app.do("google_calendars")} == {ME}
    on = {s["name"]: bool(s["enabled"]) for s in app.table("sources")}
    assert on == {"Family": True, "Classes": False, "Seminars": False, "Gmail": True, f"Gmail ({SCHOOL})": False}
    assert fixed(app) == ["CS 1110 Lecture"]  # what it brought in stays
    assert [s["input"]["title"] for s in app.do("inbox")["suggestions"]] == ["Family dinner"]  # its unanswered go
    read(app, folder=tmp_path, minutes_later=60)
    assert all(error is None for error in errors(app).values())  # nothing tries to read it

    keep_token(tmp_path, SCHOOL)  # connected again: its calendars and mail come back on
    read(app, folder=tmp_path, minutes_later=120)
    assert {s["name"] for s in app.table("sources") if s["enabled"]} == set(on)
    assert sorted(s["input"]["title"] for s in app.do("inbox")["suggestions"]) == ["Family dinner", "Seminar"]
    assert fixed(app) == ["CS 1110 Lecture"]  # read again without a second copy
