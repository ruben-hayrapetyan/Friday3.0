"""Signing in to a service in the browser (C109; integrations/oauth.py), against Microsoft's stand-in: the page asked
for carries Friday's app id, the access asked, PKCE and a fresh state, and comes back to this Mac only; the code is
traded (with its verifier) for tokens kept only in secrets.toml; the page you land on says it's done or why not; a
state used twice or never given connects nothing; an access token about to expire is renewed and kept again; and a
service whose app isn't registered in this copy of Friday says so instead of opening anything."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from friday.commands.integrations import signed_in
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.integrations import microsoft, oauth, sync
from friday.integrations.base import ConnectorError
from tests.commands.helpers import App, new_app
from tests.integrations.fake_microsoft import ACCESS, REFRESH, FakeGraph

ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    fake = FakeGraph("")
    monkeypatch.setitem(sync.TRANSPORTS, "microsoft_todo", fake.transport)
    monkeypatch.setitem(oauth.TRANSPORTS, "microsoft_todo", fake.transport)
    return fake


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def page(app: App) -> dict[str, str]:
    url = app.do("integration_sign_in", kind="microsoft_todo", origin=ORIGIN)["url"]
    assert url.startswith(f"{microsoft.AUTHORITY}/authorize?")
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_the_page_carries_fridays_app_the_access_asked_and_pkce(app: App, graph: FakeGraph) -> None:
    asked = page(app)
    assert asked["client_id"] == microsoft.client_id() and asked["response_type"] == "code"
    assert asked["redirect_uri"] == f"{ORIGIN}/oauth/callback"
    assert asked["scope"] == "offline_access User.Read Tasks.ReadWrite"
    assert asked["code_challenge_method"] == "S256" and len(asked["code_challenge"]) == 43
    assert asked["state"] != page(app)["state"]  # a fresh state each time


def test_signing_in_connects_it_with_the_tokens_only_in_secrets(app: App, graph: FakeGraph) -> None:
    graph.add("Pay rent", "2026-10-22")
    asked = page(app)
    graph.codes["code-1"] = asked["code_challenge"]
    ok, words = signed_in(app.conn, asked["state"], "code-1", None)
    assert ok and "connected to Microsoft To Do (maria@outlook.com)" in words, words
    (source,) = app.do("integrations")
    assert source["kind"] == "microsoft_todo" and source["signs_in"] is True
    kept = secrets_path().read_text()
    assert REFRESH in kept and oct(secrets_path().stat().st_mode)[-3:] == "600"
    assert REFRESH not in str(app.table("sources")) + str(app.table("command_log"))
    again = signed_in(app.conn, asked["state"], "code-1", None)
    assert again == (False, "That sign-in page was too old or was used already: press Sign in again")


def test_saying_no_or_a_bad_code_connects_nothing(app: App, graph: FakeGraph) -> None:
    asked = page(app)
    assert signed_in(app.conn, asked["state"], None, "access_denied") == (
        False, "Microsoft To Do didn't connect: you said no")  # fmt: skip
    asked = page(app)
    ok, words = signed_in(app.conn, asked["state"], "made-up", None)
    assert not ok and "didn't finish the sign-in" in words
    assert app.do("integrations") == []


def test_only_this_mac_is_where_the_page_sends_you_back(app: App) -> None:
    with pytest.raises(FieldError, match="this Mac"):
        app.do("integration_sign_in", kind="microsoft_todo", origin="https://evil.example")
    with pytest.raises(FieldError, match="isn't connected by signing in"):
        app.do("integration_sign_in", kind="todoist", origin=ORIGIN)


def test_an_unregistered_app_says_so(app: App, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRIDAY_MICROSOFT_CLIENT_ID")
    with pytest.raises(FieldError, match="isn't ready in this copy of Friday"):
        app.do("integration_sign_in", kind="microsoft_todo", origin=ORIGIN)


def test_an_expiring_token_is_renewed_and_kept_again(graph: FakeGraph) -> None:
    kept: list[str] = []
    old = json.dumps({"access_token": ACCESS, "refresh_token": REFRESH, "expires_at": 1000})
    graph.token = "ms-access-2"  # what the stand-in will accept once renewed
    session = oauth.Session(microsoft.TODO, old, kept.append, clock=lambda: 990.0)
    assert session.access() == "ms-access-2"
    assert json.loads(kept[0])["refresh_token"] == REFRESH and json.loads(kept[0])["expires_at"] == 990 + 3599
    with pytest.raises(ConnectorError, match="press Sign in again"):
        oauth.Session(microsoft.TODO, json.dumps({"access_token": "x", "expires_at": 1}), clock=lambda: 9e9).access()
