"""Sign in with Google on a hosted Friday (HOSTED.md S4 step 3; H22, H38, H86): Google's sign-in page, then back to
/auth/google with a code, traded for Google's signed statement of who you are. It signs in the account whose email
Google has checked (invites only, H24: an address without an account is told so). Only sign-in is asked for
(openid, email, profile); calendars and Gmail through this client come in S7.

The client's id is in the copy's friday.env (FRIDAY_GOOGLE_CLIENT_ID) and its secret comes from Bitwarden
(FRIDAY_GOOGLE_CLIENT_SECRET, scripts/server/with-secrets.sh). Each sign-in carries a one-time state, a nonce and a
PKCE verifier, kept ten minutes in the copy's accounts file.
"""

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from friday.server.accounts import Accounts

AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
CERTS = "https://www.googleapis.com/oauth2/v1/certs"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
STATE_MINUTES = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS google_states (
  id TEXT PRIMARY KEY,
  verifier TEXT NOT NULL,
  nonce TEXT NOT NULL,
  app TEXT,
  expires INTEGER NOT NULL
) STRICT;
"""


class GoogleError(Exception):
    """A Google sign-in that didn't hold; the message is for the page."""


@dataclass(frozen=True)
class Client:
    id: str
    secret: str
    token_url: str = TOKEN
    certs_url: str = CERTS
    authorize_url: str = AUTHORIZE

    @staticmethod
    def from_environment() -> "Client | None":
        """The copy's Google client, or None when it has none yet (no button then)."""
        client_id, secret = os.environ.get("FRIDAY_GOOGLE_CLIENT_ID"), os.environ.get("FRIDAY_GOOGLE_CLIENT_SECRET")
        if not client_id or not secret:
            return None
        return Client(client_id, secret, os.environ.get("FRIDAY_GOOGLE_TOKEN_URL", TOKEN),
                      os.environ.get("FRIDAY_GOOGLE_CERTS_URL", CERTS),
                      os.environ.get("FRIDAY_GOOGLE_AUTHORIZE_URL", AUTHORIZE))  # fmt: skip


def challenge_of(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


class GoogleSignIn:
    def __init__(self, accounts: Accounts, client: Client) -> None:
        self.accounts, self.client = accounts, client
        with accounts.connect() as conn:
            conn.executescript(SCHEMA)

    def start(self, redirect_uri: str, now: int, app: str | None) -> str:
        """Google's sign-in page for a new one-time state."""
        state, verifier, nonce = (secrets.token_urlsafe(32) for _ in range(3))
        with self.accounts.connect() as conn:
            conn.execute("DELETE FROM google_states WHERE expires < ?", [now])
            conn.execute(
                "INSERT INTO google_states (id, verifier, nonce, app, expires) VALUES (?, ?, ?, ?, ?)",
                [state, verifier, nonce, app, now + STATE_MINUTES],
            )
        query = {"client_id": self.client.id, "redirect_uri": redirect_uri, "response_type": "code",
                 "scope": "openid email profile", "state": state, "nonce": nonce, "prompt": "select_account",
                 "code_challenge": challenge_of(verifier), "code_challenge_method": "S256"}  # fmt: skip
        return f"{self.client.authorize_url}?{urlencode(query)}"

    def take(self, state: str, now: int) -> tuple[str, str, str | None]:
        with self.accounts.connect() as conn:
            row = conn.execute("SELECT * FROM google_states WHERE id = ? AND expires >= ?", [state, now]).fetchone()
            conn.execute("DELETE FROM google_states WHERE id = ?", [state])
        if row is None:
            raise GoogleError("That sign-in took too long or was already used; try again.")
        return row["verifier"], row["nonce"], row["app"]

    def finish(self, code: str, state: str, redirect_uri: str, now: int) -> tuple[str, str | None]:
        """The email Google has checked for this sign-in, and the app that asked."""
        verifier, nonce, app = self.take(state, now)
        claims = self.claims(self.trade(code, verifier, redirect_uri))
        if claims.get("nonce") != nonce:
            raise GoogleError("Google's answer wasn't for this sign-in; try again.")
        if claims.get("iss") not in ISSUERS:
            raise GoogleError("That answer didn't come from Google.")
        if not claims.get("email") or claims.get("email_verified") is not True:
            raise GoogleError("Google hasn't checked that account's email address.")
        return str(claims["email"]).lower(), app

    def trade(self, code: str, verifier: str, redirect_uri: str) -> str:
        """Google's ID token for the code."""
        try:
            answer = httpx.post(self.client.token_url, timeout=20, data={
                "code": code, "client_id": self.client.id, "client_secret": self.client.secret,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier,
            })  # fmt: skip
        except httpx.HTTPError as error:
            raise GoogleError("Google couldn't be reached; try again in a minute.") from error
        token = answer.json().get("id_token") if answer.status_code == 200 else None
        if not token:
            raise GoogleError("Google didn't accept the sign-in; try again.")
        return str(token)

    def claims(self, token: str) -> dict[str, Any]:
        """The token's claims once its signature, audience and times are checked against Google's keys."""
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        try:
            return dict(
                id_token.verify_token(token, Request(), audience=self.client.id, certs_url=self.client.certs_url)
            )
        except ValueError as error:
            raise GoogleError("Google's answer couldn't be checked; try again.") from error
