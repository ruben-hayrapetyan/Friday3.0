"""Two reads of a signed-in service at once, both finding its access token about to expire (C144 left this: "OAuth
refresh races remain"). Each renewed with the same refresh token: a service that hands out a new refresh token each
time and refuses the old one (Slack's rotation, Microsoft's sometimes) turned the second away, and whichever kept its
tokens last won, perhaps the spent ones. Now renewals take turns (`oauth.REFRESHING`), and each reads the kept tokens
first (`load`): renewed meanwhile, they're used as they are. Google's sign-in (sync/google_auth.py) the same.

Glass box: Session.access with `load`, the lock, a stored token adopted. Black box: two threads against a rotating
token endpoint, one renewal, both reads answered, the newest refresh token kept. Whole system: two connectors for one
connected source (integrations/sync.connector_for) over secrets.toml."""

import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from friday.core.paths import secrets_path
from friday.integrations import microsoft, oauth, sync
from friday.sync import google_auth
from tests.commands.helpers import App, new_app

EXPIRING = 1000.0  # the old access token's expiry; the clock below is 10 s before it, inside EARLY_S


class Rotating:
    """A token endpoint that gives a new refresh token each renewal and refuses a spent one, slowly enough that two
    renewals at once overlap."""

    def __init__(self, delay: float = 0.2) -> None:
        self.live, self.issued, self.refused, self.delay = "refresh-0", 0, 0, delay
        self.lock = threading.Lock()

    def handle(self, request: httpx.Request) -> httpx.Response:
        asked = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        time.sleep(self.delay)
        with self.lock:
            if asked.get("refresh_token") != self.live:
                self.refused += 1
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "refresh token spent"})
            self.issued += 1
            self.live = f"refresh-{self.issued}"
            return httpx.Response(200, json={"access_token": f"access-{self.issued}", "refresh_token": self.live,
                                             "expires_in": 3600})  # fmt: skip


@pytest.fixture
def rotating(monkeypatch: pytest.MonkeyPatch) -> Rotating:
    fake = Rotating()
    monkeypatch.setitem(oauth.TRANSPORTS, "microsoft_todo", httpx.MockTransport(fake.handle))
    return fake


class Store:
    """Where a source's tokens are kept, as secrets.toml keeps them: read whole, written whole."""

    def __init__(self, token: str) -> None:
        self.token = token

    def keep(self, token: str) -> None:
        self.token = token

    def load(self) -> str:
        return self.token


def expiring() -> str:
    return json.dumps({"access_token": "access-0", "refresh_token": "refresh-0", "expires_at": EXPIRING})


def session(store: Store, load: bool = True) -> oauth.Session:
    return oauth.Session(microsoft.TODO, store.load(), store.keep, clock=lambda: EXPIRING - 10,
                         load=store.load if load else None)  # fmt: skip


# glass box


def test_a_session_uses_tokens_renewed_meanwhile_rather_than_renewing_again(rotating: Rotating) -> None:
    store = Store(expiring())
    first, second = session(store), session(store)  # both read the expiring tokens
    assert first.access() == "access-1"
    assert second.access() == "access-1"  # read again under the lock: renewed already, so used
    assert rotating.issued == 1 and rotating.refused == 0
    assert json.loads(store.token)["refresh_token"] == "refresh-1"


def test_tokens_kept_that_are_no_newer_are_renewed_as_before(rotating: Rotating) -> None:
    store = Store(expiring())
    lone = session(store)
    store.token = "not json"  # whatever is kept, if it can't be read or isn't newer, the session renews its own
    assert lone.access() == "access-1" and rotating.issued == 1


# black box


def both_at_once(make: Any) -> tuple[list[str], list[BaseException]]:
    answers: list[str] = []
    errors: list[BaseException] = []
    start = threading.Barrier(2)

    def read() -> None:
        reader = make()
        start.wait()
        try:
            answers.append(reader.access())
        except BaseException as error:  # noqa: BLE001  the test says which
            errors.append(error)

    threads = [threading.Thread(target=read) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return answers, errors


def test_two_reads_at_once_renew_once_and_both_are_answered(rotating: Rotating) -> None:
    store = Store(expiring())
    answers, errors = both_at_once(lambda: session(store))
    assert errors == [] and answers == ["access-1", "access-1"]
    assert rotating.issued == 1 and rotating.refused == 0
    assert json.loads(store.token)["refresh_token"] == rotating.live  # the one the service will take next


# whole system: one connected source, two connectors (a sync and Settings' check, say) over secrets.toml


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_two_connectors_for_one_source_renew_once_and_secrets_keep_the_newest(
    app: App, rotating: Rotating, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth.time, "time", lambda: EXPIRING - 10)
    sync.keep_token(7, "microsoft_todo", expiring())
    source = {"id": 7, "kind": "microsoft_todo", "config": "{}"}
    answers, errors = both_at_once(lambda: sync.connector_for(source).session)
    assert errors == [] and answers == ["access-1", "access-1"] and rotating.issued == 1
    kept = sync.secrets()[sync.section(7)]
    assert json.loads(kept["token"])["refresh_token"] == "refresh-1" and secrets_path().stat().st_mode & 0o077 == 0


# Google's sign-in


class Creds:
    """google.oauth2.credentials.Credentials as credentials() uses it: valid or not, refreshed, saved."""

    made: list["Creds"] = []
    refreshed = 0

    def __init__(self, info: dict[str, Any]) -> None:
        self.info, self.valid, self.refresh_token = info, info.get("fresh", False), "r"
        Creds.made.append(self)

    @classmethod
    def from_authorized_user_info(cls, info: dict[str, Any]) -> "Creds":
        return cls(info)

    def refresh(self, _request: Any) -> None:
        time.sleep(0.2)
        Creds.refreshed += 1
        self.valid, self.info = True, {**self.info, "fresh": True}


def test_google_renews_an_account_once_when_two_ask_at_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, dict[str, Any]] = {"me@gmail.com": {"fresh": False}}
    monkeypatch.setattr(google_auth, "Credentials", Creds)
    monkeypatch.setattr(google_auth, "tokens", lambda folder: dict(saved))
    monkeypatch.setattr(google_auth, "save", lambda folder, account, creds: saved.__setitem__(account, creds.info))
    Creds.refreshed = 0

    class Reader:
        def access(self) -> str:
            creds = google_auth.credentials(tmp_path, "me@gmail.com")
            assert creds is not None and creds.valid
            return "ok"

    answers, errors = both_at_once(Reader)
    assert errors == [] and answers == ["ok", "ok"]
    assert Creds.refreshed == 1 and saved["me@gmail.com"]["fresh"] is True
