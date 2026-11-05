"""Passkeys on a hosted Friday (HOSTED.md S4 step 2; H85, H88–H91): made with Touch ID on a device you're signed in
on, then offered by the browser's autofill in the sign-in page's email box. Kept in the copy's accounts file beside
the accounts (server/accounts.py): each passkey's public key and use count, and each pending ceremony's challenge
for two minutes, used once. The relying party is the copy's own address (FRIDAY_PUBLIC_URL), so a passkey made on
one address isn't offered on another (a domain later means making them again).
"""

import json
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from friday.server.accounts import Account, Accounts, account

CHALLENGE_MINUTES = 10  # the sign-in page waits for autofill while you look at it

SCHEMA = """
CREATE TABLE IF NOT EXISTS passkeys (
  id TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts (id),
  public_key BLOB NOT NULL,
  sign_count INTEGER NOT NULL,
  name TEXT NOT NULL,
  created INTEGER NOT NULL,
  used INTEGER
) STRICT;
CREATE TABLE IF NOT EXISTS ceremonies (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('register', 'signin')),
  account_id INTEGER REFERENCES accounts (id),
  challenge BLOB NOT NULL,
  app TEXT,
  expires INTEGER NOT NULL
) STRICT;
"""


class PasskeyError(Exception):
    """A passkey ceremony that didn't hold; the message is for the page."""


@dataclass(frozen=True)
class Passkey:
    id: str
    name: str
    created: int
    used: int | None


@dataclass(frozen=True)
class Party:
    """Who passkeys are for: the copy's address."""

    origin: str  # https://laptop.tailnet.ts.net:8443
    rp_id: str  # laptop.tailnet.ts.net

    @staticmethod
    def of(public_url: str) -> "Party":
        parts = urlsplit(public_url)
        return Party(f"{parts.scheme}://{parts.netloc}", parts.hostname or "")


def device_name(user_agent: str) -> str:
    """A passkey's first name, from the browser that made it: "Mac, Chrome", "iPhone, Safari"."""
    device = next((d for d, pattern in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"),
                                        ("Mac", "Macintosh"), ("Windows", "Windows"), ("Linux", "Linux"))
                   if pattern in user_agent), "A device")  # fmt: skip
    browser = next((b for b, pattern in (("Edge", r"Edg/"), ("Firefox", r"Firefox/"), ("Chrome", r"Chrome/"),
                                         ("Safari", r"Safari/")) if re.search(pattern, user_agent)), "")  # fmt: skip
    return f"{device}, {browser}" if browser else device


class Passkeys:
    def __init__(self, accounts: Accounts) -> None:
        self.accounts = accounts
        with accounts.connect() as conn:
            conn.executescript(SCHEMA)

    def of(self, account_id: int) -> list[Passkey]:
        with self.accounts.connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created, used FROM passkeys WHERE account_id = ? ORDER BY created", [account_id]
            ).fetchall()
        return [Passkey(r["id"], r["name"], r["created"], r["used"]) for r in rows]

    def remove(self, account_id: int, passkey_id: str) -> bool:
        with self.accounts.connect() as conn:
            gone = conn.execute("DELETE FROM passkeys WHERE id = ? AND account_id = ?", [passkey_id, account_id])
        return gone.rowcount == 1

    def ceremony(self, kind: str, challenge: bytes, now: int, account_id: int | None, app: str | None) -> str:
        flow = secrets.token_urlsafe(24)
        with self.accounts.connect() as conn:
            conn.execute("DELETE FROM ceremonies WHERE expires < ?", [now])
            conn.execute(
                "INSERT INTO ceremonies (id, kind, account_id, challenge, app, expires) VALUES (?, ?, ?, ?, ?, ?)",
                [flow, kind, account_id, challenge, app, now + CHALLENGE_MINUTES],
            )
        return flow

    def take(self, flow: str, kind: str, now: int) -> tuple[bytes, int | None, str | None]:
        """A pending ceremony's challenge, account and app, used up; a stale, used or unknown one is refused."""
        with self.accounts.connect() as conn:
            row = conn.execute(
                "SELECT * FROM ceremonies WHERE id = ? AND kind = ? AND expires >= ?", [flow, kind, now]
            ).fetchone()
            conn.execute("DELETE FROM ceremonies WHERE id = ?", [flow])
        if row is None:
            raise PasskeyError("That took too long; try again.")
        return row["challenge"], row["account_id"], row["app"]

    def registration_options(self, who: Account, party: Party, now: int) -> dict[str, Any]:
        """What the browser needs to make a passkey for `who`, and the ceremony's id to send back with it."""
        made = generate_registration_options(
            rp_id=party.rp_id,
            rp_name="Friday",
            user_id=str(who.id).encode(),
            user_name=who.email,
            user_display_name=who.name,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED, user_verification=UserVerificationRequirement.PREFERRED
            ),
            exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p.id)) for p in self.of(who.id)],
        )
        flow = self.ceremony("register", made.challenge, now, who.id, None)
        return {"flow": flow, "options": json.loads(options_to_json(made))}

    def register(
        self, who: Account, flow: str, credential: dict[str, Any], name: str, party: Party, now: int
    ) -> Passkey:
        challenge, account_id, _ = self.take(flow, "register", now)
        if account_id != who.id:
            raise PasskeyError("That passkey was being made for another account.")
        try:
            done = verify_registration_response(
                credential=credential, expected_challenge=challenge, expected_rp_id=party.rp_id,
                expected_origin=party.origin,
            )  # fmt: skip
        except InvalidRegistrationResponse as error:
            raise PasskeyError(f"The passkey couldn't be checked ({error}).") from error
        passkey_id = bytes_to_base64url(done.credential_id)
        with self.accounts.connect() as conn:
            conn.execute(
                "INSERT INTO passkeys (id, account_id, public_key, sign_count, name, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [passkey_id, who.id, done.credential_public_key, done.sign_count, name[:60], now],
            )
        return Passkey(passkey_id, name[:60], now, None)

    def signin_options(self, party: Party, now: int, app: str | None) -> dict[str, Any]:
        """A challenge for whichever passkey the browser offers (no account named: autofill picks it)."""
        made = generate_authentication_options(rp_id=party.rp_id)
        flow = self.ceremony("signin", made.challenge, now, None, app)
        return {"flow": flow, "options": json.loads(options_to_json(made))}

    def signin(self, flow: str, credential: dict[str, Any], party: Party, now: int) -> tuple[Account, str | None]:
        """The account a passkey signs in, and the app that asked (H91)."""
        challenge, _, app = self.take(flow, "signin", now)
        passkey_id = str(credential.get("id", ""))
        with self.accounts.connect() as conn:
            row = conn.execute("SELECT * FROM passkeys WHERE id = ?", [passkey_id]).fetchone()
        if row is None:
            raise PasskeyError("Friday doesn't know that passkey (removed, or made for another address).")
        try:
            done = verify_authentication_response(
                credential=credential, expected_challenge=challenge, expected_rp_id=party.rp_id,
                expected_origin=party.origin, credential_public_key=row["public_key"],
                credential_current_sign_count=row["sign_count"],
            )  # fmt: skip
        except InvalidAuthenticationResponse as error:
            raise PasskeyError(f"The passkey couldn't be checked ({error}).") from error
        with self.accounts.connect() as conn:
            conn.execute("UPDATE passkeys SET sign_count = ?, used = ? WHERE id = ?",
                         [done.new_sign_count, now, passkey_id])  # fmt: skip
            found = account(conn.execute("SELECT * FROM accounts WHERE id = ?", [row["account_id"]]).fetchone())
        assert found is not None
        return found, app
