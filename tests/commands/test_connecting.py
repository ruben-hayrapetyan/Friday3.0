"""Connecting Google from the app: the key file is checked and kept where `fridayd google-login` looks, Connect signs
in once in the background with the scopes the CLI asks for, lists the calendars and makes a sync due, and a failure
is said plainly. Connecting again adds another account, and signing in with one already there renews it; Remove
forgets one. Google's sign-in is faked throughout; nothing opens a browser or reaches Google."""

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from google_auth_oauthlib.flow import WSGITimeoutError

from friday.commands import connecting
from friday.core.items import FieldError
from friday.planner.store import kv_get, kv_set
from friday.server.main import main
from friday.sim.fakes import FakeGoogle
from friday.sync import google_auth
from tests.commands.helpers import App, new_app

CLIENT = {
    "installed": {
        "client_id": "123.apps.googleusercontent.com",
        "client_secret": "shh",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}
PAGE = "https://accounts.google.com/o/oauth2/auth?client_id=123"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def keep_token(folder: Path, account: str, scopes: tuple[str, ...]) -> None:
    """A token as a sign-in saves it, under the account's address."""
    token = {"token": f"t-{account}", "scopes": list(scopes)}
    google_auth.rewrite(folder, lambda found, saved: saved | {account: token})


class FakeSignIn:
    """Google's sign-in, answered when the test says: the token it saves, under `who`, has the scopes asked for."""

    def __init__(self, error: Exception | None = None, who: str = "me@gmail.com"):
        self.error, self.who, self.calls, self.asked, self.answer = error, who, [], [], threading.Event()

    def __call__(
        self,
        client: Path,
        folder: Path,
        scopes: tuple[str, ...],
        wait_s: int,
        opened: Callable[[str], None],
        account: str | None = None,
    ) -> str:
        self.calls.append(scopes)
        self.asked.append(account)
        opened(PAGE)
        assert self.answer.wait(5)
        if self.error is not None:
            raise self.error
        keep_token(folder, self.who, scopes)
        return self.who


def signed_in(app: App, monkeypatch: pytest.MonkeyPatch, fake: FakeSignIn, **payload: Any) -> dict[str, Any]:
    """Connect, let Google answer, and wait for the sign-in to finish."""
    monkeypatch.setattr(google_auth, "login", fake)
    app.do("google_connect", **payload)
    fake.answer.set()
    thread = connecting.SIGN_INS[connecting.data_file(app.conn).parent].thread
    assert thread is not None
    thread.join(5)
    return app.do("google_connect_status")


class Accounts:
    """Each account's stand-in Google, as `google_auth.calendar` gives them."""

    def __init__(self, by_account: dict[str, FakeGoogle]):
        self.by_account = by_account

    def __call__(self, folder: Path, account: str | None = None) -> FakeGoogle:
        return self.by_account[account or next(iter(self.by_account))]


def with_client(config: Path) -> None:
    (config / "google_client.json").write_text(json.dumps(CLIENT))


def test_without_the_key_file_it_says_so_and_starts_nothing(app: App) -> None:
    status = app.do("google_connect_status")
    assert status["state"] == "idle" and not (status["client_file"] or status["calendar"] or status["gmail"])
    with pytest.raises(FieldError, match="key file"):
        app.do("google_connect")


def test_the_key_file_is_checked_then_kept_beside_friday_toml_for_you_only(app: App, no_personal_config: Path) -> None:
    for wrong, said in (
        ("not json", "isn't Google's key file"),
        (json.dumps({"web": CLIENT["installed"]}), "Desktop app"),
        (json.dumps({"installed": {"client_id": "123"}}), "isn't Google's key file"),
    ):
        with pytest.raises(FieldError, match=said):
            app.do("google_client_save", content=wrong)
    assert not (no_personal_config / "google_client.json").exists()
    assert app.do("google_client_save", content=json.dumps(CLIENT))["client_file"]
    kept = no_personal_config / "google_client.json"
    assert json.loads(kept.read_text()) == CLIENT and kept.stat().st_mode & 0o777 == 0o600
    assert app.table("command_log")[-1]["command"] != "google_client_save"  # the secret isn't kept in the log


def test_the_key_file_goes_where_google_client_file_points(app: App, tmp_path: Path) -> None:
    app.do("settings_set", key="google", value={"client_file": str(tmp_path / "keys" / "mine.json")})
    app.do("google_client_save", content=json.dumps(CLIENT))
    assert json.loads((tmp_path / "keys" / "mine.json").read_text()) == CLIENT


def test_connect_signs_in_once_in_the_background_then_lists_the_calendars(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    with_client(no_personal_config)
    fake = FakeSignIn()
    monkeypatch.setattr(google_auth, "login", fake)
    monkeypatch.setattr(google_auth, "calendar", Accounts({"me@gmail.com": FakeGoogle({"me@gmail.com": []})}))
    first = app.do("google_connect")
    assert first["state"] == "waiting" and not first["calendar"]
    for _ in range(50):  # the page's address comes once the flow has made it
        if app.do("google_connect_status")["url"]:
            break
        threading.Event().wait(0.02)
    again = app.do("google_connect")  # a second press while it waits starts nothing new
    assert again["state"] == "waiting" and again["url"] == PAGE and len(fake.calls) == 1
    fake.answer.set()
    thread = connecting.SIGN_INS[connecting.data_file(app.conn).parent].thread
    assert thread is not None
    thread.join(5)
    status = app.do("google_connect_status")
    assert status["state"] == "connected" and status["calendar"] and status["events"] and status["url"] is None
    assert status["account"] == "me@gmail.com"
    assert status["accounts"] == [{"email": "me@gmail.com", "gmail": False, "events": True, "mail_error": None}]
    assert fake.calls == [google_auth.LOGIN_SCOPES]  # the calendars and changing events; no mail while Gmail is off
    assert fake.asked == [None]  # any account: Google's page asks which
    assert [(c["name"], c["account"]) for c in app.do("google_calendars")] == [("me", "me@gmail.com")]
    assert kv_get(app.conn, "sync_now") is not None


def test_connecting_again_adds_another_account_and_the_same_one_again_renews_it(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    with_client(no_personal_config)
    personal = FakeGoogle({"me@gmail.com": [], "family@group": []}, names={"family@group": "Family"})
    school = FakeGoogle({"student@school.edu": [], "dsa@group": []}, names={"dsa@group": "DSA Fall 2026"})
    monkeypatch.setattr(google_auth, "calendar", Accounts({"me@gmail.com": personal, "student@school.edu": school}))
    signed_in(app, monkeypatch, FakeSignIn())
    status = signed_in(app, monkeypatch, FakeSignIn(who="student@school.edu"))
    assert status["account"] == "student@school.edu"
    assert [a["email"] for a in status["accounts"]] == ["me@gmail.com", "student@school.edu"]
    listed = {c["name"]: c["account"] for c in app.do("google_calendars")}
    assert listed == {
        "DSA Fall 2026": "student@school.edu",
        "Family": "me@gmail.com",
        "me": "me@gmail.com",
        "student": "student@school.edu",
    }
    app.do("settings_set", key="gmail", value={"enabled": True})
    again = FakeSignIn()
    status = signed_in(app, monkeypatch, again, account="me@gmail.com")  # Allow Gmail, beside that account
    assert again.asked == ["me@gmail.com"]
    assert [(a["email"], a["gmail"]) for a in status["accounts"]] == [
        ("me@gmail.com", True),
        ("student@school.edu", False),
    ]


def test_remove_forgets_one_account_and_leaves_the_other(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    with_client(no_personal_config)
    monkeypatch.setattr(
        google_auth,
        "calendar",
        Accounts({"me@gmail.com": FakeGoogle({"me@gmail.com": []}), "b@x.edu": FakeGoogle({"b@x.edu": []})}),
    )
    signed_in(app, monkeypatch, FakeSignIn())
    signed_in(app, monkeypatch, FakeSignIn(who="b@x.edu"))
    status = app.do("google_remove", account="me@gmail.com")
    assert [a["email"] for a in status["accounts"]] == ["b@x.edu"]
    assert list(google_auth.tokens(connecting.data_file(app.conn).parent)) == ["b@x.edu"]
    assert [c["account"] for c in app.do("google_calendars")] == ["b@x.edu"]
    with pytest.raises(FieldError, match="isn't connected"):
        app.do("google_remove", account="me@gmail.com")
    assert app.table("command_log")[-1]["command"] != "google_remove"  # nothing an undo could bring back


def test_signing_in_adds_or_renews_the_account_google_says_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[dict[str, Any]] = []

    class Creds:
        def __init__(self, n: int):
            self.n = n

        def to_json(self) -> str:
            return json.dumps({"token": f"t{self.n}", "scopes": list(google_auth.LOGIN_SCOPES)})

    class Flow:
        opened = None

        def run_local_server(self, **options: Any) -> Creds:
            asked.append(options)
            return Creds(len(asked))

    monkeypatch.setattr(google_auth.Flow, "from_client_secrets_file", lambda *args: Flow())
    monkeypatch.setattr(google_auth, "build", lambda *args, **kwargs: None)
    who = iter(["me@gmail.com", "student@school.edu", "me@gmail.com"])
    monkeypatch.setattr(google_auth, "address", lambda service: next(who))
    assert google_auth.login(tmp_path / "client.json", tmp_path) == "me@gmail.com"
    assert google_auth.login(tmp_path / "client.json", tmp_path) == "student@school.edu"
    assert google_auth.login(tmp_path / "client.json", tmp_path, account="me@gmail.com") == "me@gmail.com"
    assert [a.get("prompt") for a in asked] == ["select_account consent", "select_account consent", "consent"]
    assert asked[2]["login_hint"] == "me@gmail.com"  # straight to that account
    kept = google_auth.tokens(tmp_path)
    assert list(kept) == ["me@gmail.com", "student@school.edu"]  # renewed in its place, not added twice
    assert kept["me@gmail.com"]["token"] == "t3"
    assert google_auth.secrets_file(tmp_path).stat().st_mode & 0o777 == 0o600


def test_with_gmail_on_it_asks_for_mail_too(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    with_client(no_personal_config)
    app.do("settings_set", key="gmail", value={"enabled": True})
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: FakeGoogle())
    fake = FakeSignIn()
    assert signed_in(app, monkeypatch, fake)["gmail"]
    assert fake.calls == [(*google_auth.LOGIN_SCOPES, google_auth.GMAIL_SCOPE)]


@pytest.mark.parametrize(
    ("error", "said"),
    [
        (WSGITimeoutError("Timed out waiting for response from authorization server"), "five minutes"),
        (Exception("(access_denied) The user denied the request"), "test user"),
        (Warning("Scope has changed from a to b"), "unticked"),
        (Exception("(invalid_client) The OAuth client was not found."), "key file"),
        (ConnectionError("Max retries exceeded"), "internet"),
    ],
)
def test_a_failed_sign_in_says_why_plainly_and_can_be_tried_again(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path, error: Exception, said: str
) -> None:
    with_client(no_personal_config)
    status = signed_in(app, monkeypatch, FakeSignIn(error))
    assert status["state"] == "failed" and said in status["message"] and not status["calendar"]
    monkeypatch.setattr(google_auth, "calendar", lambda folder, account: FakeGoogle())
    assert signed_in(app, monkeypatch, FakeSignIn())["state"] == "connected"


def test_the_demo_is_connected_already(app: App) -> None:
    kv_set(app.conn, "demo", True)
    kv_set(app.conn, "google_calendars", [{"id": "c@g", "name": "C", "primary": True, "account": "jt673@cornell.edu"}])
    status = app.do("google_connect_status")
    assert status["calendar"] and status["gmail"] and status["client_file"]
    assert [a["email"] for a in status["accounts"]] == ["jt673@cornell.edu"]
    for command, payload in (("google_connect", {}), ("google_remove", {"account": "jt673@cornell.edu"})):
        with pytest.raises(FieldError, match="stand-in"):
            app.do(command, **payload)


def test_google_login_asks_what_connect_asks_and_finds_the_same_key_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    asked = []
    monkeypatch.setattr(
        google_auth, "login", lambda client, folder, scopes: asked.append((client, scopes)) or "me@gmail.com"
    )
    with pytest.raises(SystemExit, match="Settings → Integrations"):
        main(["--data-dir", str(tmp_path), "google-login"])
    with_client(no_personal_config)
    main(["--data-dir", str(tmp_path), "google-login"])
    assert asked == [(no_personal_config / "google_client.json", google_auth.LOGIN_SCOPES)]


def test_a_key_file_named_in_terminal_is_kept_where_friday_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    monkeypatch.setattr(google_auth, "login", lambda client, folder, scopes: "me@gmail.com")
    downloaded = tmp_path / "client_secret_123.json"
    downloaded.write_text(json.dumps(CLIENT))
    main(["--data-dir", str(tmp_path / "data"), "google-login", "--client-file", str(downloaded)])
    kept = no_personal_config / "google_client.json"
    assert json.loads(kept.read_text()) == CLIENT and oct(kept.stat().st_mode & 0o777) == "0o600"
