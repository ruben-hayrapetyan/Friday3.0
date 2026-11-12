"""Glass box on Google's sign-in and tokens (sync/google_auth.py) without reaching Google: an expired token is
refreshed and kept again (the one from before Friday kept several, still under its old place), a token that's still
good is used as it is, an account not connected has none, Gmail is offered only to a login that allowed it,
Cancel stops only a sign-in waiting on this Mac, the account's address is its primary calendar's, and the read-only
API passes plain values through."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.oauth2.credentials import Credentials

from friday.sync import google_auth
from friday.sync.google_auth import LEGACY, Reading

ME, SCHOOL = "me@gmail.com", "student@school.edu"
CLIENT = {"installed": {"client_id": "id.apps.googleusercontent.com", "client_secret": "not-a-secret",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"}}  # fmt: skip


def utc_now() -> datetime:
    """Now in UTC with no zone, as google-auth keeps a token's expiry."""
    return datetime.now(UTC).replace(tzinfo=None)


def token(name: str, expired: bool, refresh: bool = True, scopes: tuple[str, ...] = google_auth.LOGIN_SCOPES) -> dict:
    """A saved token as Credentials.to_json writes it, expired an hour ago or good for another."""
    expiry = utc_now() + timedelta(hours=-1 if expired else 1)
    return {"token": name, "client_id": "id", "client_secret": "s", "scopes": list(scopes),
            "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"), "refresh_token": "r" if refresh else None}  # fmt: skip


@pytest.fixture
def refreshes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Google's token endpoint, stood in for: each refresh gives a new token good for an hour."""
    asked: list[str] = []

    def refresh(self: Credentials, request: Any) -> None:
        asked.append(self.token)
        self.token, self.expiry = f"fresh {self.token}", utc_now() + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    return asked


def keep(folder: Path, **found: Any) -> None:
    google_auth.secrets_file(folder).write_text(json.dumps(found))


class TestTokens:
    def test_an_expired_token_is_refreshed_and_kept_under_its_account(self, tmp_path: Path, refreshes: list) -> None:
        keep(tmp_path, google_accounts={ME: token("mine", expired=True), SCHOOL: token("school", expired=True)})
        creds = google_auth.credentials(tmp_path, SCHOOL)
        assert creds is not None and creds.valid and creds.token == "fresh school"
        assert refreshes == ["school"]  # only the account asked for
        saved = google_auth.tokens(tmp_path)
        assert saved[SCHOOL]["token"] == "fresh school" and saved[ME]["token"] == "mine"

    def test_the_token_from_before_is_refreshed_and_stays_where_it_was(self, tmp_path: Path, refreshes: list) -> None:
        keep(tmp_path, google=token("old", expired=True), anthropic="kept")
        creds = google_auth.credentials(tmp_path)  # none named: the first, the one from before
        assert creds is not None and creds.token == "fresh old"
        found = json.loads(google_auth.secrets_file(tmp_path).read_text())
        assert found["google"]["token"] == "fresh old" and found["google_accounts"] == {}
        assert found["anthropic"] == "kept"

    def test_a_token_still_good_is_used_as_it_is(self, tmp_path: Path, refreshes: list) -> None:
        keep(tmp_path, google_accounts={ME: token("mine", expired=False)})
        creds = google_auth.credentials(tmp_path, ME)
        assert creds is not None and creds.token == "mine" and refreshes == []

    def test_an_expired_token_that_cant_be_refreshed_is_given_back_as_it_is(
        self, tmp_path: Path, refreshes: list
    ) -> None:
        keep(tmp_path, google_accounts={ME: token("mine", expired=True, refresh=False)})
        creds = google_auth.credentials(tmp_path, ME)
        assert creds is not None and not creds.valid and refreshes == []

    def test_no_token_when_nothing_or_not_that_account_is_connected(self, tmp_path: Path) -> None:
        assert google_auth.credentials(tmp_path) is None
        keep(tmp_path, google_accounts={ME: token("mine", expired=False)})
        assert google_auth.credentials(tmp_path, SCHOOL) is None
        assert google_auth.calendar(tmp_path, SCHOOL) is None and google_auth.gmail(tmp_path, SCHOOL) is None

    def test_saving_the_account_from_before_keeps_it_under_its_old_place(self, tmp_path: Path) -> None:
        google_auth.save(tmp_path, LEGACY, Credentials(token="old"))
        found = json.loads(google_auth.secrets_file(tmp_path).read_text())
        assert found["google"]["token"] == "old" and found["google_accounts"] == {}
        assert list(google_auth.tokens(tmp_path)) == [LEGACY]

    def test_removing_the_account_from_before_forgets_it_and_leaves_the_others(self, tmp_path: Path) -> None:
        keep(tmp_path, google=token("old", expired=False), google_accounts={SCHOOL: token("s", expired=False)})
        google_auth.remove(tmp_path, LEGACY)
        assert list(google_auth.tokens(tmp_path)) == [SCHOOL]
        assert "google" not in json.loads(google_auth.secrets_file(tmp_path).read_text())

    def test_naming_the_token_from_before_changes_nothing_when_there_is_none(self, tmp_path: Path) -> None:
        google_auth.adopt(tmp_path, ME)
        assert not google_auth.secrets_file(tmp_path).exists()  # not even written
        keep(tmp_path, google=token("old", expired=False))
        google_auth.adopt(tmp_path, LEGACY)  # its address still not known: it stays
        assert list(google_auth.tokens(tmp_path)) == [LEGACY]

    def test_the_token_from_before_is_dropped_once_that_account_signed_in_again(self, tmp_path: Path) -> None:
        keep(tmp_path, google=token("old", expired=False), google_accounts={ME: token("newer", expired=False)})
        google_auth.adopt(tmp_path, ME)
        assert {a: t["token"] for a, t in google_auth.tokens(tmp_path).items()} == {ME: "newer"}
        assert "google" not in json.loads(google_auth.secrets_file(tmp_path).read_text())


class TestGmail:
    def test_gmail_is_offered_only_to_a_login_that_allowed_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        given: list[Credentials] = []
        monkeypatch.setattr(google_auth, "credentials", lambda folder, account=None: given[-1])
        given.append(Credentials(token="t", scopes=list(google_auth.LOGIN_SCOPES)))
        assert google_auth.gmail(tmp_path) is None  # signed in for the calendars only
        given.append(Credentials(token="t", scopes=[*google_auth.LOGIN_SCOPES, google_auth.GMAIL_SCOPE]))
        api = google_auth.gmail(tmp_path)  # Google's own client, built offline from the description it ships with
        assert api is not None and api.users().messages().list(userId="me").method == "GET"


class TestSignIn:
    def test_the_page_opened_is_told_to_whoever_asked_and_no_one_else(self) -> None:
        opened: list[str] = []
        flow = google_auth.Flow.from_client_config(CLIENT, list(google_auth.LOGIN_SCOPES))
        flow.redirect_uri = "http://localhost:8080/"
        url, _ = flow.authorization_url(prompt="consent")
        assert url.startswith("https://accounts.google.com/o/oauth2/auth?") and opened == []
        flow.opened = opened.append
        again, _ = flow.authorization_url(prompt="consent")
        assert opened == [again]

    def test_cancel_reaches_only_a_sign_in_waiting_on_this_mac(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[str] = []
        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: asked.append(url))
        google_auth.stop("https://accounts.google.com/o/oauth2/auth?redirect_uri=https%3A%2F%2Felsewhere.com%2F")
        google_auth.stop("https://accounts.google.com/o/oauth2/auth?state=abc")  # no address to answer at all
        assert asked == []

    def test_cancel_after_the_sign_in_finished_is_fine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[str] = []

        def gone(url: str, timeout: int) -> None:
            asked.append(url)
            raise ConnectionRefusedError("nothing listens there any more")

        monkeypatch.setattr("urllib.request.urlopen", gone)
        google_auth.stop("https://accounts.google.com/o/oauth2/auth?redirect_uri=http%3A%2F%2F127.0.0.1%3A5%2F&state=s")
        assert asked == ["http://127.0.0.1:5/?error=access_denied&state=s"]

    def test_the_accounts_address_is_its_primary_calendars_id(self) -> None:
        asked: list[str] = []

        def get(calendarId: str) -> SimpleNamespace:  # noqa: N803 (Google's name)
            asked.append(calendarId)
            return SimpleNamespace(execute=lambda: {"id": SCHOOL, "summary": "Student"})

        service = SimpleNamespace(calendarList=lambda: SimpleNamespace(get=get))
        assert google_auth.address(service) == SCHOOL and asked == ["primary"]


class TestReadOnly:
    def test_a_plain_value_of_the_api_is_given_as_it_is(self) -> None:
        api = Reading(SimpleNamespace(version="v3", events=lambda: SimpleNamespace(kind="calendar#events")))
        assert api.version == "v3"
        assert isinstance(api.events(), Reading) and api.events().kind == "calendar#events"


class TestWhich:
    def test_a_calendar_is_read_through_its_own_account_else_the_unnamed_one_else_the_first(self) -> None:
        assert google_auth.which({ME: 1, SCHOOL: 2}, SCHOOL) == SCHOOL
        assert google_auth.which({LEGACY: 1, SCHOOL: 2}, ME) == LEGACY  # may be it: its address isn't known yet
        assert google_auth.which({ME: 1, SCHOOL: 2}, None) == ME  # listed before accounts were kept
        assert google_auth.which({ME: 1, SCHOOL: 2}, "") == ME

    def test_a_calendar_of_an_account_no_longer_connected_has_none(self) -> None:
        assert google_auth.which({ME: 1}, SCHOOL) is None
        assert google_auth.which({}, None) is None


class TestAsking:
    def test_a_sign_in_asks_for_the_mail_and_tasks_only_once_they_are_wanted(self) -> None:
        assert google_auth.scopes(mail=False) == google_auth.LOGIN_SCOPES
        assert google_auth.scopes(mail=True) == (*google_auth.LOGIN_SCOPES, google_auth.GMAIL_SCOPE)
        assert google_auth.scopes(mail=False, tasks=True)[-1] == google_auth.TASKS_SCOPE
        assert google_auth.EVENTS_SCOPE in google_auth.scopes(mail=False)  # changing your events, every sign-in

    def test_your_own_client_is_kept_readable_only_by_you(self, tmp_path: Path) -> None:
        path = tmp_path / "config" / "google_client.json"
        google_auth.keep_client(path, json.dumps(CLIENT))
        assert json.loads(path.read_text()) == CLIENT and path.stat().st_mode & 0o777 == 0o600
