"""Connecting Google from the app: the key file is checked and kept where `fridayd google-login` looks, Connect signs
in once in the background with the scopes the CLI asks for, lists the calendars and makes a sync due, and a failure
is said plainly. Google's sign-in is faked throughout; nothing opens a browser or reaches Google."""

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


class FakeSignIn:
    """Google's sign-in, answered when the test says: the token it saves has the scopes asked for."""

    def __init__(self, error: Exception | None = None):
        self.error, self.calls, self.answer = error, [], threading.Event()

    def __call__(
        self, client: Path, folder: Path, scopes: tuple[str, ...], wait_s: int, opened: Callable[[str], None]
    ) -> None:
        self.calls.append(scopes)
        opened(PAGE)
        assert self.answer.wait(5)
        if self.error is not None:
            raise self.error
        google_auth.secrets_file(folder).write_text(json.dumps({"google": {"token": "t", "scopes": list(scopes)}}))


def signed_in(app: App, monkeypatch: pytest.MonkeyPatch, fake: FakeSignIn) -> dict[str, Any]:
    """Connect, let Google answer, and wait for the sign-in to finish."""
    monkeypatch.setattr(google_auth, "login", fake)
    app.do("google_connect")
    fake.answer.set()
    thread = connecting.SIGN_INS[connecting.data_file(app.conn).parent].thread
    assert thread is not None
    thread.join(5)
    return app.do("google_connect_status")


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
    monkeypatch.setattr(
        google_auth, "calendar", lambda folder: FakeGoogle({"me@gmail.com": []}, primary="me@gmail.com")
    )
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
    assert fake.calls == [google_auth.LOGIN_SCOPES]  # the calendars and changing events; no mail while Gmail is off
    assert [c["name"] for c in app.do("google_calendars")] == ["me"]
    assert kv_get(app.conn, "sync_now") is not None


def test_with_gmail_on_it_asks_for_mail_too(
    app: App, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    with_client(no_personal_config)
    app.do("settings_set", key="gmail", value={"enabled": True})
    monkeypatch.setattr(google_auth, "calendar", lambda folder: FakeGoogle())
    fake = FakeSignIn()
    assert signed_in(app, monkeypatch, fake)["gmail"]
    assert fake.calls == [(*google_auth.LOGIN_SCOPES, google_auth.GMAIL_SCOPE)]


@pytest.mark.parametrize(
    ("error", "said"),
    [
        (WSGITimeoutError("Timed out waiting for response from authorization server"), "five minutes"),
        (Exception("(access_denied) The user denied the request"), "didn't allow"),
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
    monkeypatch.setattr(google_auth, "calendar", lambda folder: FakeGoogle())
    assert signed_in(app, monkeypatch, FakeSignIn())["state"] == "connected"


def test_the_demo_is_connected_already(app: App) -> None:
    kv_set(app.conn, "demo", True)
    status = app.do("google_connect_status")
    assert status["calendar"] and status["gmail"] and status["client_file"]
    with pytest.raises(FieldError, match="stand-in"):
        app.do("google_connect")


def test_google_login_asks_what_connect_asks_and_finds_the_same_key_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    asked = []
    monkeypatch.setattr(google_auth, "login", lambda client, folder, scopes: asked.append((client, scopes)))
    with pytest.raises(SystemExit, match="Settings → Integrations"):
        main(["--data-dir", str(tmp_path), "google-login"])
    with_client(no_personal_config)
    main(["--data-dir", str(tmp_path), "google-login"])
    assert asked == [(no_personal_config / "google_client.json", google_auth.LOGIN_SCOPES)]


def test_a_key_file_named_in_terminal_is_kept_where_friday_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_personal_config: Path
) -> None:
    monkeypatch.setattr(google_auth, "login", lambda client, folder, scopes: None)
    downloaded = tmp_path / "client_secret_123.json"
    downloaded.write_text(json.dumps(CLIENT))
    main(["--data-dir", str(tmp_path / "data"), "google-login", "--client-file", str(downloaded)])
    kept = no_personal_config / "google_client.json"
    assert json.loads(kept.read_text()) == CLIENT and oct(kept.stat().st_mode & 0o777) == "0o600"
