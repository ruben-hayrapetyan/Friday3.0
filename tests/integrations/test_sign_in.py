"""Signing in to a service in the browser (C109; integrations/oauth.py), against Microsoft's stand-in: the page asked
for carries Friday's app id, the access asked, PKCE and a fresh state, and comes back to this Mac only; the code is
traded (with its verifier) for tokens kept only in secrets.toml; the page you land on says it's done or why not; a
state used twice or never given connects nothing; an access token about to expire is renewed and kept again; and a
service whose app isn't registered in this copy of Friday says so instead of opening anything."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from friday.commands.integrations import signed_in
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.integrations import keys, microsoft, oauth, sync
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


def test_a_sign_in_page_left_open_too_long_is_forgotten_when_the_next_begins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth, "PENDING", {})
    first = oauth.begin(microsoft.TODO, f"{ORIGIN}/oauth/callback", now=1000.0)
    old = parse_qs(urlsplit(first).query)["state"][0]
    second = oauth.begin(microsoft.TODO, f"{ORIGIN}/oauth/callback", now=1000.0 + oauth.WAIT_S + 1)
    assert list(oauth.PENDING) == [parse_qs(urlsplit(second).query)["state"][0]] and old not in oauth.PENDING


def test_a_token_endpoint_that_cant_be_reached_or_answers_a_page_is_said(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    monkeypatch.setitem(oauth.TRANSPORTS, "microsoft_todo", httpx.MockTransport(unreachable))
    renew = {"grant_type": "refresh_token", "refresh_token": REFRESH}
    with pytest.raises(ConnectorError, match="couldn't reach Microsoft To Do to sign in") as said:
        oauth.trade(microsoft.TODO, renew)
    assert said.value.problem == "down"
    page = httpx.MockTransport(lambda request: httpx.Response(502, text="<html>Bad gateway</html>"))
    monkeypatch.setitem(oauth.TRANSPORTS, "microsoft_todo", page)
    with pytest.raises(ConnectorError, match="answered the sign-in with something Friday can't read") as said:
        oauth.trade(microsoft.TODO, renew)
    assert said.value.problem == "answer" and REFRESH not in str(said.value)


def test_kept_tokens_that_cant_be_read_say_to_sign_in_again() -> None:
    for kept in ("{not json", json.dumps({"refresh_token": REFRESH}), ""):
        with pytest.raises(ConnectorError, match="isn't signed in to Microsoft To Do: press Sign in again"):
            oauth.Session(microsoft.TODO, kept)


def test_a_token_renewed_with_nowhere_to_keep_it_is_still_used(graph: FakeGraph) -> None:
    old = json.dumps({"access_token": ACCESS, "refresh_token": REFRESH, "expires_at": 1000})
    graph.token = "ms-access-2"
    session = oauth.Session(microsoft.TODO, old, None, clock=lambda: 990.0)
    assert session.access() == "ms-access-2" and session.tokens["refresh_token"] == REFRESH


def test_a_keys_file_that_isnt_a_table_is_passed_over_for_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed, kept = tmp_path / "bundle.json", tmp_path / "checkout.json"
    listed.write_text('["trello_client_id"]')
    kept.write_text('{"ticktick_client_id": "tt-from-the-checkout"}')
    monkeypatch.setattr(keys, "PLACES", [tmp_path / "missing.json", listed, kept])
    keys.kept.cache_clear()
    try:
        assert keys.get("ticktick_client_id") == "tt-from-the-checkout"
    finally:
        keys.kept.cache_clear()
