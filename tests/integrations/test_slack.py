"""Slack (C112): the messages that mention you, read on your sign-in (search:read only), each waiting in your Inbox
to decide on; read only; a mention that ages out of search isn't taken as done; Slack's markup said as words; its
refusals said in words. Not in the to-do contract: a mention has no due and ages out rather than being done there."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from friday.integrations import oauth, slack, sync
from friday.integrations.base import ConnectorError
from friday.planner.store import load_settings
from tests.commands.helpers import App, new_app

ME, NOW = "U0MARIA", 1_792_500_000.0
TOKEN = json.dumps({"access_token": "xoxp-stand-in"})


class FakeSlack:
    """auth.test, search.messages and oauth.v2.access, as Slack answers them (always 200, ok true or false)."""

    def __init__(self) -> None:
        self.matches: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.error: str | None = None

    def mention(self, text: str, days_ago: float = 1, user: str = "U0SAM", name: str = "sam",
                channel: str = "design", im: bool = False, now: float = NOW) -> None:  # fmt: skip
        ts = f"{now - days_ago * 86400:.6f}"
        self.matches.append({"iid": ts, "ts": ts, "text": text, "user": user, "username": name,
                             "channel": {"id": "C1" if not im else "D1", "name": channel, "is_im": im},
                             "permalink": f"https://acme.slack.com/archives/C1/p{ts.replace('.', '')}"})  # fmt: skip

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "oauth.v2.access":
            user = {"id": ME, "scope": "search:read", "access_token": "xoxp-new", "token_type": "user"}
            return httpx.Response(200, json={"ok": True, "team": {"id": "T1", "name": "Acme"}, "authed_user": user})
        if request.headers.get("authorization") != "Bearer xoxp-stand-in" or self.error:
            return httpx.Response(200, json={"ok": False, "error": self.error or "invalid_auth"})
        if method == "auth.test":
            return httpx.Response(200, json={"ok": True, "user": "maria", "user_id": ME, "team": "Acme"})
        if method == "search.messages":
            assert request.url.params["query"] == f"<@{ME}>", request.url
            return httpx.Response(200, json={"ok": True, "messages": {"matches": self.matches}})
        return httpx.Response(200, json={"ok": False, "error": "unknown_method"})


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeSlack:
    made = FakeSlack()
    monkeypatch.setitem(sync.TRANSPORTS, "slack", httpx.MockTransport(made.handle))
    monkeypatch.setitem(oauth.TRANSPORTS, "slack", httpx.MockTransport(made.handle))
    return made


def connector(fake: FakeSlack) -> slack.Slack:
    return slack.Slack(TOKEN, {}, sync.TRANSPORTS["slack"], now=NOW)


def test_mentions_of_you_from_the_last_two_weeks_as_words(fake: FakeSlack) -> None:
    fake.mention("<@U0MARIA|maria> can you review <https://figma.com/x|the mockups> by Friday?")
    fake.mention("old one <@U0MARIA>", days_ago=20)
    fake.mention("note to self <@U0MARIA>", user=ME, name="maria")
    fake.mention("<@U0MARIA> lunch?", name="lee", im=True)
    found = {r.title: r for r in connector(fake).read()}
    assert set(found) == {"Reply to sam in #design: @you can you review the mockups by Friday?",
                          "Reply to lee in a direct message: @you lunch?"}  # fmt: skip
    review = found["Reply to sam in #design: @you can you review the mockups by Friday?"]
    assert review.due is None and review.notes.endswith("In Slack: #design")
    assert review.url and review.url.startswith("https://acme.slack.com/archives/")


def test_a_long_message_is_cut_in_the_title_and_whole_in_the_notes(fake: FakeSlack) -> None:
    fake.mention("<@U0MARIA> " + "word " * 40)
    (r,) = connector(fake).read()
    assert r.title.endswith("…") and len(r.title) < 110 and r.notes.count("word") == 40


@pytest.mark.parametrize(("error", "problem"), [("invalid_auth", "token"), ("token_revoked", "token"),
                                                ("ratelimited", "rate"), ("fatal_error", "answer")])  # fmt: skip
def test_slacks_refusals_are_said_in_words(fake: FakeSlack, error: str, problem: str) -> None:
    fake.error = error
    with pytest.raises(ConnectorError) as said:
        connector(fake).read()
    assert said.value.problem == problem


def test_the_sign_in_takes_the_users_own_token_and_only_search(fake: FakeSlack) -> None:
    assert slack.PROVIDER.scope_param == "user_scope" and slack.PROVIDER.scopes == ("search:read",)
    assert slack.user_tokens({"ok": False, "error": "bad_redirect_uri"}) == {"error": "bad_redirect_uri"}
    assert slack.user_tokens({"ok": True, "authed_user": {"access_token": "xoxp-1"}}) == {"access_token": "xoxp-1"}


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_connected_mentions_wait_in_the_inbox_and_aging_out_isnt_done(app: App, fake: FakeSlack) -> None:
    fake.mention("<@U0MARIA> can you send the deck?", now=time.time())  # the sync reads by the wall clock
    out = app.do("integration_connect", kind="slack", token=TOKEN)
    assert out["source"]["arrival"] == "inbox" and out["source"]["two_way"] is False
    settings = load_settings(app.conn)
    sync.sync_all(app.conn, settings, app.now_utc, asked=True)
    sync.sync_all(app.conn, settings, app.now_utc, asked=True)
    pending = [s for s in app.table("suggestions") if s["status"] == "pending"]
    assert len(pending) == 1 and app.table("items") == []  # waits to be decided on, every time
    app.do("suggestion_accept", id=pending[0]["id"])
    fake.matches.clear()  # aged out of search
    sync.sync_all(app.conn, settings, app.now_utc, asked=True)
    assert [i["status"] for i in app.table("items")] == ["todo"], "a mention aging out was taken as done"
    app.do("done", id=app.table("items")[0]["id"])
    assert sync.send_writes(app.conn, app.now_utc) == 0 and app.table("source_writes") == []


def test_slacks_sign_in_returns_by_friday_s_https_page_with_this_mac_s_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H182: Slack lets only https return addresses into other workspaces, so it sends you to Friday's page on
    friday-scheduler.com, which forwards to this Mac at the port carried at the front of `state`."""
    from urllib.parse import parse_qs, urlsplit

    monkeypatch.setenv("FRIDAY_SLACK_CLIENT_ID", "1.2")
    monkeypatch.setenv("FRIDAY_SLACK_CLIENT_SECRET", "s")
    url = new_app(tmp_path).do("integration_sign_in", kind="slack", origin="http://127.0.0.1:8770")["url"]
    asked = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert asked["redirect_uri"] == "https://friday-scheduler.com/slack-signin.html"
    assert asked["state"].startswith("8770-") and asked["user_scope"] == "search:read"
    assert oauth.PENDING[asked["state"]].redirect == asked["redirect_uri"]  # the same address when trading the code


def test_it_is_read_only_and_an_odd_answer_is_said_in_words(fake: FakeSlack) -> None:
    with pytest.raises(AssertionError, match="read only"):
        connector(fake).write("C1/1.0", "done")
    odd = httpx.MockTransport(lambda request: httpx.Response(200, json=["ok"]))
    with pytest.raises(ConnectorError, match="Slack answered in a shape Friday doesn't know") as said:
        slack.Slack(TOKEN, {}, odd, now=NOW).check()
    assert said.value.problem == "answer"


def test_markup_reads_as_words_even_without_knowing_who_you_are() -> None:
    assert slack.plain("<@U0MARIA> see <#C1|general> and <@U0SAM|sam>") == "@someone see #general and @sam"


def test_the_sign_in_trades_its_code_with_fridays_secret_in_the_body(
    fake: FakeSlack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FRIDAY_SLACK_CLIENT_ID", "1.2")
    monkeypatch.setenv("FRIDAY_SLACK_CLIENT_SECRET", "slack-stand-in-secret")
    tokens = oauth.trade(slack.PROVIDER, {"grant_type": "authorization_code", "code": "c"}, now=NOW)
    assert tokens == {"access_token": "xoxp-new"}  # the user's own token, from under authed_user
    (asked,) = fake.requests
    assert "client_secret=slack-stand-in-secret" in asked.content.decode() and "authorization" not in asked.headers
