"""Accounts on a hosted Friday (HOSTED.md S4; H81–H87): who may sign in, the one-time links that sign them in and the
sessions that keep them signed in until they sign out (H25). Kept in a file of their own beside the copy's profiles
(H19, H83), never in a Friday's own database. Only a token's hash is stored, so the file opens no session by itself.

Your Friday on the Mac has no accounts file and no sign-in (H2).
"""

import hashlib
import re
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path

LINK_MINUTES = 15  # how long an emailed link works, once
CODE_MINUTES = 2  # how long the browser's hand-back to the Mac app works, once
TYPED_TRIES = 5  # wrong tries an emailed code takes before it stops working (H92)
ADDRESS_TRIES = 20  # wrong tries one address takes in an hour, over all its codes, before codes stop for it
USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,30}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  name TEXT NOT NULL,
  timezone TEXT NOT NULL,
  created INTEGER NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS links (
  hash TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts (id),
  kind TEXT NOT NULL CHECK (kind IN ('email', 'app')),
  app TEXT,
  expires INTEGER NOT NULL,
  used INTEGER
) STRICT;
CREATE TABLE IF NOT EXISTS codes (
  flow TEXT PRIMARY KEY,
  email TEXT NOT NULL COLLATE NOCASE,
  account_id INTEGER REFERENCES accounts (id),
  hash TEXT NOT NULL,
  link TEXT,
  app TEXT,
  made INTEGER NOT NULL,
  expires INTEGER NOT NULL,
  tries INTEGER NOT NULL DEFAULT 0,
  used INTEGER
) STRICT;
CREATE TABLE IF NOT EXISTS sessions (
  hash TEXT PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES accounts (id),
  device TEXT NOT NULL,
  created INTEGER NOT NULL,
  seen INTEGER NOT NULL,
  ended INTEGER
) STRICT;
"""


@dataclass(frozen=True)
class Account:
    id: int
    email: str
    username: str
    name: str
    timezone: str


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    """The accounts file. Times are engine minutes (DESIGN: int minutes since the epoch), passed in."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def add(self, email: str, username: str, name: str, timezone: str, now: int) -> Account:
        """A new account (H84: made by a command on the server); a taken email or username is refused."""
        email, username = email.strip().lower(), username.strip().lower()
        if not EMAIL.match(email):
            raise ValueError(f"email: {email!r} isn't an email address")
        if not USERNAME.match(username):
            raise ValueError("username: 2–31 of a–z, 0–9, '.', '_' or '-', starting with a letter or digit")
        if not name.strip():
            raise ValueError("name: needed")
        with self.connect() as conn:
            taken = conn.execute(
                "SELECT email, username FROM accounts WHERE email = ? OR username = ?", [email, username]
            ).fetchone()
            if taken:
                which = "email" if taken["email"] == email else "username"
                raise ValueError(f"{which}: already has an account")
            conn.execute(
                "INSERT INTO accounts (email, username, name, timezone, created) VALUES (?, ?, ?, ?, ?)",
                [email, username, name.strip(), timezone, now],
            )
        found = self.by_email(email)
        assert found is not None
        return found

    def by_email(self, email: str) -> Account | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE email = ?", [email.strip().lower()]).fetchone()
        return account(row)

    def all(self) -> list[Account]:
        with self.connect() as conn:
            return [a for a in map(account, conn.execute("SELECT * FROM accounts ORDER BY id")) if a]

    def email_link(self, email: str, now: int, app: str | None = None) -> tuple[Account, str] | None:
        """A one-time link's token for the account with this email, or None when there is no such account (the
        page says the same either way, so it tells nobody who has an account). `app`: the Mac app that asked,
        handed back to once signed in (H43)."""
        found = self.by_email(email)
        if found is None:
            return None
        return found, self.token(found.id, "email", now + LINK_MINUTES, app)

    def emailed_code(self, email: str, now: int, app: str | None = None) -> tuple[str, str]:
        """The 6-digit code for the email beside its link (H92), and the flow the sign-in page types it into. An
        address without an account gets a flow too, and its tries count the same, so the page tells nobody who has
        one. The code is stored hashed with its flow: six digits alone are too few to keep."""
        found = self.by_email(email)
        flow, code = secrets.token_urlsafe(24), f"{secrets.randbelow(10**6):06d}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO codes (flow, email, account_id, hash, app, made, expires) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [flow, email.strip().lower(), found.id if found else None, digest(f"{flow}:{code}"), app, now,
                 now + LINK_MINUTES],
            )  # fmt: skip
        return flow, code

    def pair(self, flow: str, link: str) -> None:
        """The emailed code and link are one sign-in: using either uses up both."""
        with self.connect() as conn:
            conn.execute("UPDATE codes SET link = ? WHERE flow = ?", [digest(link), flow])

    def redeem_code(self, flow: str, code: str, now: int) -> tuple[Account, str | None] | str:
        """The account a typed code signs in and the app that asked, used up with its link; or why not, in words."""
        typed = "".join(ch for ch in code if ch.isdigit())
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM codes WHERE flow = ?", [flow]).fetchone()
            if row is None or row["used"] is not None or row["expires"] < now or row["tries"] >= TYPED_TRIES:
                return "That code has run out: send a new one."
            if self.address_tries(conn, row["email"], now) >= ADDRESS_TRIES:
                return "Too many wrong codes for this address. Use the link in the email, or wait an hour."
            if len(typed) != 6 or digest(f"{flow}:{typed}") != row["hash"] or row["account_id"] is None:
                conn.execute("UPDATE codes SET tries = tries + 1 WHERE flow = ?", [flow])
                left = TYPED_TRIES - row["tries"] - 1
                return "That code isn't right." + (f" {left} more {'try' if left == 1 else 'tries'}." if left else "")
            if conn.execute("UPDATE codes SET used = ? WHERE flow = ? AND used IS NULL", [now, flow]).rowcount != 1:
                return "That code has run out: send a new one."
            if row["link"]:
                conn.execute("UPDATE links SET used = ? WHERE hash = ? AND used IS NULL", [now, row["link"]])
            found = conn.execute("SELECT * FROM accounts WHERE id = ?", [row["account_id"]]).fetchone()
        found_account = account(found)
        return (found_account, row["app"]) if found_account else "That code has run out: send a new one."

    @staticmethod
    def address_tries(conn: sqlite3.Connection, email: str, now: int) -> int:
        one = conn.execute("SELECT COALESCE(SUM(tries), 0) FROM codes WHERE email = ? AND made >= ?", [email, now - 60])
        return int(one.fetchone()[0])

    def app_code(self, account_id: int, app: str, now: int) -> str:
        """A one-time code the browser hands to the Mac app, which trades it for a session of its own."""
        return self.token(account_id, "app", now + CODE_MINUTES, app)

    def token(self, account_id: int, kind: str, expires: int, app: str | None) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO links (hash, account_id, kind, app, expires) VALUES (?, ?, ?, ?, ?)",
                [digest(token), account_id, kind, app, expires],
            )
        return token

    def redeem(self, token: str, kind: str, now: int) -> tuple[Account, str | None] | None:
        """The account a link or code signs in, and the app that asked, used up; None when unknown, used or late."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM links WHERE hash = ? AND kind = ? AND used IS NULL AND expires >= ?",
                [digest(token), kind, now],
            ).fetchone()
            if row is None:
                return None
            done = conn.execute("UPDATE links SET used = ? WHERE hash = ? AND used IS NULL", [now, row["hash"]])
            if done.rowcount != 1:  # two tabs at once: only one wins
                return None
            if kind == "email":  # its emailed code goes with it (H92)
                conn.execute("UPDATE codes SET used = ? WHERE link = ? AND used IS NULL", [now, row["hash"]])
            found = conn.execute("SELECT * FROM accounts WHERE id = ?", [row["account_id"]]).fetchone()
        found_account = account(found)
        return (found_account, row["app"]) if found_account else None

    def start_session(self, account_id: int, device: str, now: int) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (hash, account_id, device, created, seen) VALUES (?, ?, ?, ?, ?)",
                [digest(token), account_id, device[:200], now, now],
            )
        return token

    def session(self, token: str | None, now: int) -> Account | None:
        """Whose session a cookie is, while it hasn't been signed out; seen at most once a minute."""
        if not token:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT a.*, s.seen FROM sessions s JOIN accounts a ON a.id = s.account_id "
                "WHERE s.hash = ? AND s.ended IS NULL",
                [digest(token)],
            ).fetchone()
            if row is not None and row["seen"] < now:
                conn.execute("UPDATE sessions SET seen = ? WHERE hash = ?", [now, digest(token)])
        return account(row)

    def end_session(self, token: str | None, now: int) -> None:
        if token:
            with self.connect() as conn:
                conn.execute("UPDATE sessions SET ended = ? WHERE hash = ? AND ended IS NULL", [now, digest(token)])


def account(row: sqlite3.Row | None) -> Account | None:
    if row is None:
        return None
    return Account(row["id"], row["email"], row["username"], row["name"], row["timezone"])
