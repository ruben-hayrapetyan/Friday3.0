"""Signing in to a service in your browser (OAuth 2, the authorization-code flow with PKCE), for the integrations that
can't take a pasted token (C109: Microsoft To Do and Outlook, TickTick, Slack). Friday's server is on your Mac, so
the service's page sends your browser back to it (http://127.0.0.1:<its port>/oauth/callback) with a code, which the
server trades for tokens; the page you land on says it's done. Nothing is pasted, and the tokens go where pasted ones
do (secrets.toml, mode 0600): `access_token`, `refresh_token`, `expires_at`, as JSON, renewed shortly before they
expire and kept again (`Session`).

Each service is a `Provider`: its pages, Friday's app id there (shipped in the app; a service whose app isn't
registered yet says so in its box, as Trello's key does), the secret where the service insists on one (TickTick,
Slack: it can't stay secret in a downloaded app, which you accepted, 11 Nov), and the access asked for."""

import base64
import hashlib
import json
import secrets as random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from friday.integrations.base import ConnectorError, Transport

WAIT_S = 600  # a sign-in page left open longer than this is forgotten
EARLY_S = 120  # tokens are renewed this long before they expire


@dataclass(frozen=True)
class Provider:
    kind: str
    name: str
    authorize: str
    token: str
    client_id: Callable[[], str]  # "" while Friday has no app registered there
    scopes: tuple[str, ...]
    secret: Callable[[], str] | None = None
    scope_param: str = "scope"  # Slack asks a user's access as `user_scope`
    extra: dict[str, str] = field(default_factory=dict)  # more the sign-in page wants (prompt, access_type…)
    secret_in_body: bool = True  # else HTTP Basic, as TickTick wants
    tokens_of: Callable[[dict[str, Any]], dict[str, Any]] = lambda answer: answer  # Slack's sit under authed_user
    # an https page the service sends your browser back to, which forwards it to this Mac (Slack, which lets only
    # https return addresses into other workspaces): the port it forwards to rides in `state`
    relay: str | None = None

    def ready(self) -> bool:
        return bool(self.client_id().strip())


@dataclass
class Pending:
    provider: Provider
    verifier: str
    redirect: str
    fields: dict[str, str]
    at: float


PENDING: dict[str, Pending] = {}  # by `state`: the sign-ins whose page is open
LOCK = threading.Lock()
TRANSPORTS: dict[str, Transport] = {}  # a fake service's token endpoint, in tests


def begin(provider: Provider, redirect: str, fields: dict[str, str] | None = None, now: float | None = None) -> str:
    """The service's sign-in page for this sign-in: its address, remembered under a fresh `state`. A provider with a
    relay page is sent back there instead, with this Mac's port at the front of `state` for it to forward to."""
    if not provider.ready():
        raise ConnectorError(
            "token", f"{provider.name} isn't ready in this copy of Friday yet: it comes with an update"
        )
    now = time.time() if now is None else now
    state, verifier = random.token_urlsafe(24), random.token_urlsafe(48)
    if provider.relay:
        port = redirect.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[-1]
        state, redirect = f"{port}-{state}", provider.relay
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with LOCK:
        for old in [s for s, p in PENDING.items() if now - p.at > WAIT_S]:
            PENDING.pop(old)
        PENDING[state] = Pending(provider, verifier, redirect, dict(fields or {}), now)
    asked = {"client_id": provider.client_id(), "response_type": "code", "redirect_uri": redirect, "state": state,
             provider.scope_param: (" " if provider.scope_param == "scope" else ",").join(provider.scopes),
             "code_challenge": challenge, "code_challenge_method": "S256"} | provider.extra  # fmt: skip
    return f"{provider.authorize}?{urlencode(asked)}"


def finish(state: str, code: str, now: float | None = None) -> tuple[Pending, str]:
    """The tokens for a sign-in the service sent back (as JSON, to keep), with what it was started with."""
    with LOCK:
        pending = PENDING.pop(state, None)
    if pending is None or (time.time() if now is None else now) - pending.at > WAIT_S:
        raise ConnectorError("token", "That sign-in page was too old or was used already: press Sign in again")
    asked = {"grant_type": "authorization_code", "code": code, "redirect_uri": pending.redirect,
             "code_verifier": pending.verifier}  # fmt: skip
    return pending, json.dumps(trade(pending.provider, asked, now))


def trade(provider: Provider, asked: dict[str, str], now: float | None = None) -> dict[str, Any]:
    """A code (or a refresh token) for tokens, at the service's token endpoint."""
    body = {"client_id": provider.client_id()} | asked
    auth = None
    if provider.secret is not None:
        if provider.secret_in_body:
            body["client_secret"] = provider.secret()
        else:
            auth = (provider.client_id(), provider.secret())
    try:
        with httpx.Client(timeout=30, transport=TRANSPORTS.get(provider.kind)) as client:
            answer = client.post(provider.token, data=body, auth=auth, headers={"Accept": "application/json"})
    except httpx.HTTPError as error:
        raise ConnectorError("down", f"Friday couldn't reach {provider.name} to sign in") from error
    try:
        found = provider.tokens_of(answer.json())
    except (ValueError, TypeError, AttributeError) as error:
        raise ConnectorError(
            "answer", f"{provider.name} answered the sign-in with something Friday can't read"
        ) from error
    if answer.status_code >= 400 or not isinstance(found, dict) or not found.get("access_token"):
        said = (found or {}).get("error_description") or (found or {}).get("error") if isinstance(found, dict) else None
        raise ConnectorError("token", f"{provider.name} didn't finish the sign-in" + (f": {said}" if said else ""))
    now = time.time() if now is None else now
    refresh = found.get("refresh_token") or asked.get("refresh_token")  # a renewal may keep the one it had
    kept = {"access_token": found["access_token"], "refresh_token": refresh,
            "expires_at": now + float(found["expires_in"]) if found.get("expires_in") else None}  # fmt: skip
    return {k: v for k, v in kept.items() if v is not None}


class Session:
    """A signed-in service's tokens: the access token, renewed by the refresh token when it's about to expire, and kept
    again (`keep`) so the next read has it."""

    def __init__(self, provider: Provider, token: str, keep: Callable[[str], None] | None = None,
                 clock: Callable[[], float] = time.time):  # fmt: skip
        try:
            self.tokens: dict[str, Any] = (
                json.loads(token) if token.strip().startswith("{") else {"access_token": token}
            )
        except ValueError:
            self.tokens = {}
        if not self.tokens.get("access_token"):
            raise ConnectorError("token", f"Friday isn't signed in to {provider.name}: press Sign in again")
        self.provider, self.keep, self.clock = provider, keep, clock

    def access(self) -> str:
        expires = self.tokens.get("expires_at")
        if expires is not None and self.clock() > float(expires) - EARLY_S:
            if not self.tokens.get("refresh_token"):
                raise ConnectorError("token", f"{self.provider.name}'s sign-in ran out: press Sign in again")
            renew = {"grant_type": "refresh_token", "refresh_token": self.tokens["refresh_token"]}
            self.tokens = trade(self.provider, renew, self.clock())
            if self.keep is not None:
                self.keep(json.dumps(self.tokens))
        return str(self.tokens["access_token"])
