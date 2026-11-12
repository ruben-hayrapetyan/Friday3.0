"""Google Tasks (C110): riding Friday's Google sign-in, which asks for Tasks only once you want it (and keeps asking
while you do, so signing in again for Gmail doesn't take it away); connected from an account that allowed it, read
with that account's token; one that hasn't allowed it, or isn't signed in, said in words."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from friday.core.items import FieldError
from friday.integrations import google_tasks, sync
from friday.integrations.base import ConnectorError
from friday.planner.store import load_settings
from friday.sync import google_auth
from tests.commands.helpers import App, new_app
from tests.integrations.fake_google_tasks import ACCOUNT, HARNESS, FakeGoogleTasks


def test_tasks_is_asked_only_when_wanted() -> None:
    assert google_auth.TASKS_SCOPE not in google_auth.scopes(mail=True)
    assert google_auth.scopes(mail=False, tasks=True)[-1] == google_auth.TASKS_SCOPE


def test_an_account_without_tasks_or_signed_out_is_said_in_words(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(google_auth, "credentials", lambda folder, account: None)
    with pytest.raises(ConnectorError, match="isn't signed in to Google any more"):
        google_tasks.access_token(Path("."), ACCOUNT)
    no_tasks = SimpleNamespace(has_scopes=lambda scopes: False, token="t")
    monkeypatch.setattr(google_auth, "credentials", lambda folder, account: no_tasks)
    with pytest.raises(ConnectorError, match="hasn't allowed Google Tasks") as error:
        google_tasks.access_token(Path("."), ACCOUNT)
    assert error.value.problem == "access"


def test_an_account_that_allowed_tasks_reads_with_its_sign_ins_token(monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = SimpleNamespace(has_scopes=lambda scopes: scopes == [google_auth.TASKS_SCOPE], token="ya29.stand-in")
    monkeypatch.setattr(google_auth, "credentials", lambda folder, account: allowed)
    assert google_tasks.access_token(Path("."), ACCOUNT) == "ya29.stand-in"


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> App:
    fake = FakeGoogleTasks(HARNESS.token)
    fake.add("Buy milk", "2026-10-22", in_list="MDI")
    monkeypatch.setitem(sync.TRANSPORTS, "google_tasks", fake.transport)
    monkeypatch.setattr(google_tasks, "ACCESS", [lambda folder, account: HARNESS.token])
    return new_app(tmp_path)


def test_connected_from_a_google_account_it_reads_with_that_accounts_token(app: App) -> None:
    out = app.do("google_tasks_connect", account=ACCOUNT)
    assert "Google Tasks connected (maria@gmail.com)" in out["message"]
    (source,) = app.table("sources")
    assert source["kind"] == "google_tasks" and ACCOUNT in source["config"]
    sync.sync_all(app.conn, load_settings(app.conn), app.now_utc, asked=True)
    assert [r["title"] for r in app.table("raw_inputs")] == ["Buy milk"]


def test_an_account_google_refuses_isnt_connected(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(folder: Path, account: str) -> str:
        raise ConnectorError("access", f"{account} hasn't allowed Google Tasks: press Sign in with Google in its box")

    monkeypatch.setattr(google_tasks, "ACCESS", [refused])
    with pytest.raises(FieldError, match="hasn't allowed Google Tasks"):
        app.do("google_tasks_connect", account=ACCOUNT)
    assert app.table("sources") == []
