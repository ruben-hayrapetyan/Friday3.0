"""Slack (C96; C112): messages that mention you, each waiting in your Inbox to decide on. Your answers (11 Nov):
your Slack reminders and mentions; signing in through Friday's own Slack app, its id and secret shipped (as
TickTick's). Slack's reminders methods have been retiring since 2023 (Slack's own reference: "degraded or useless"),
so only mentions come in; said here and in the box.

Signed in on Slack's page as you (a user token, `search:read` only: Friday can't post, read channels beyond search,
or change anything). What comes in is the newest fifty messages mentioning you from the last two weeks (search.messages
for <@you>), each titled with who and where, its text in the notes and its link; they wait in your Inbox (Always in
the Inbox: a mention is a question, not yet a to-do). Read only, and a mention that ages out of search isn't taken
as done. SLACK_CLIENT_ID / _SECRET, FRIDAY_SLACK_* override; until they're set the box says Slack isn't ready."""

import os
import re
import time
from typing import Any, ClassVar, Literal

from friday.integrations.base import Caps, ConnectorError, Http, Remote, Transport
from friday.integrations.oauth import Provider, Session

API = "https://slack.com/api"
# Friday's Slack app (api.slack.com/apps → Friday → Basic Information): set once by Friday's developer
SLACK_CLIENT_ID = ""
SLACK_CLIENT_SECRET = ""
DAYS = 14
REFUSED = ("invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive", "missing_scope")


def client_id() -> str:
    return (os.environ.get("FRIDAY_SLACK_CLIENT_ID") or SLACK_CLIENT_ID).strip()


def client_secret() -> str:
    return (os.environ.get("FRIDAY_SLACK_CLIENT_SECRET") or SLACK_CLIENT_SECRET).strip()


def user_tokens(answer: dict[str, Any]) -> dict[str, Any]:
    """oauth.v2.access answers with the user's token under `authed_user`, or ok: false and an error."""
    if not answer.get("ok"):
        return {"error": answer.get("error") or "refused"}
    return dict(answer.get("authed_user") or {})


PROVIDER = Provider(
    kind="slack", name="Slack", authorize="https://slack.com/oauth/v2/authorize", token=f"{API}/oauth.v2.access",
    client_id=client_id, secret=client_secret, scopes=("search:read",), scope_param="user_scope",
    tokens_of=user_tokens,
)  # fmt: skip


def plain(text: str, me: str = "") -> str:
    """Slack's markup as words: you → @you, <@U1|maria> → @maria, <#C1|general> → #general, <https://x|l> → l."""
    if me:
        text = re.sub(rf"<@{re.escape(me)}(\|[^>]*)?>", "@you", text)
    text = re.sub(r"<@[A-Z0-9]+\|([^>]+)>", r"@\1", text)
    text = re.sub(r"<@([A-Z0-9]+)>", "@someone", text)
    text = re.sub(r"<#[A-Z0-9]+\|([^>]*)>", r"#\1", text)
    text = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


class Slack:
    kind: ClassVar[str] = "slack"
    name: ClassVar[str] = "Slack"
    caps: ClassVar[Caps] = Caps(two_way=False, lengths=False, gone_is_done=False)
    provider: ClassVar[Provider] = PROVIDER
    arrival: ClassVar[str] = "inbox"

    def __init__(self, token: str, config: dict[str, Any] | None = None, transport: Transport = None,
                 now: float | None = None):  # fmt: skip
        self.session = Session(PROVIDER, token, (config or {}).get("_keep"))
        self.now = time.time() if now is None else now
        base = os.environ.get("FRIDAY_API_SLACK") or API  # another address: only a fake service, in system tests

        def bearer() -> dict[str, str]:
            return {"Authorization": f"Bearer {self.session.access()}"}

        self.http = Http(self.name, base, {}, transport, fresh=bearer)

    def ask(self, method: str, **params: Any) -> dict[str, Any]:
        found = self.http.json("GET", f"/{method}", params=params)
        if not isinstance(found, dict):
            raise ConnectorError("answer", "Slack answered in a shape Friday doesn't know")
        if not found.get("ok"):
            error = str(found.get("error") or "")
            if error in REFUSED:
                raise ConnectorError("token", "Slack didn't accept Friday's sign-in: press Sign in with Slack again")
            if error == "ratelimited":
                raise ConnectorError("rate", "Slack asked Friday to slow down: it tries again later")
            raise ConnectorError("answer", f"Slack refused the request ({error or 'no reason given'})")
        return found

    def check(self) -> str:
        me = self.ask("auth.test")
        return f"{me.get('user') or 'you'} in {me.get('team') or 'Slack'}"

    def read(self) -> list[Remote]:
        me = self.ask("auth.test")
        found = self.ask("search.messages", query=f"<@{me['user_id']}>", sort="timestamp", sort_dir="desc", count=50)
        matches = ((found.get("messages") or {}).get("matches")) or []
        since = self.now - DAYS * 86400
        mine = str(me["user_id"])
        return [remote(m, mine) for m in matches if float(m.get("ts") or 0) >= since and m.get("user") != mine]

    def write(self, external_id: str, op: Literal["done", "reopen"]) -> None:
        raise AssertionError("Slack is read only (C112): nothing goes back")


def remote(m: dict[str, Any], me: str = "") -> Remote:
    channel = m.get("channel") or {}
    where = f"#{channel['name']}" if channel.get("name") and not channel.get("is_im") else "a direct message"
    who = m.get("username") or "someone"
    text = plain(str(m.get("text") or ""), me)
    short = text if len(text) <= 70 else text[:67].rstrip() + "…"
    return Remote(
        external_id=f"{channel.get('id', '')}/{m.get('ts')}",
        title=f"Reply to {who} in {where}: {short}" if short else f"Reply to {who} in {where}",
        notes=f"{text}\n\nIn Slack: {where}",
        url=m.get("permalink"),
        firm=True,
    )
