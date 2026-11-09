"""Connecting Google from the app (DESIGN §22.10), no terminal needed: Connect starts the same loopback sign-in as
`fridayd google-login`. The server runs on your Mac, so the browser that opens is yours; the sign-in waits there in a
thread of its own, five minutes at most, while the page asks how it is going (`google_connect_status`). One at a time:
pressing again while it waits starts nothing new. Once you allow it, your calendars are listed at once and a sync is
due, so their events come in within the minute.

Each account you connect is kept under its address: Connect again adds another (Google's page asks which), and
signing in with one already there renews it. Remove forgets an account's token; its calendars stop being read (and
come back on if you connect it again), and what they and its mail brought in stays.

Friday signs in with your own OAuth client JSON if you keep one, else the one shipped in the Mac app. Without either,
the page takes the file you downloaded from Google Cloud and keeps
it where `google.client_file` points, as `fridayd google-login` expects.
"""

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from google_auth_oauthlib.flow import WSGITimeoutError

from friday.api.commands import GoogleAccountInput, GoogleClientInput, GoogleConnectInput
from friday.api.types import Empty
from friday.api.views import GoogleAccountOut, GoogleConnectOut
from friday.commands.calendars import let_go
from friday.commands.fetching import list_calendars
from friday.commands.registry import Ctx, command, query
from friday.core.db import connect, rows
from friday.core.items import FieldError
from friday.planner.store import kv_get, kv_set
from friday.sync import google_auth

log = logging.getLogger("friday.google")
WAIT_S = 300  # how long Google's page may stay open before the sign-in gives up


@dataclass
class SignIn:
    state: Literal["idle", "waiting", "connected", "failed"] = "waiting"
    message: str | None = None
    url: str | None = None
    account: str | None = None  # asked for (None: any account), then the one it connected
    thread: threading.Thread | None = field(default=None, repr=False)
    cancelled: bool = False


class Cancelled(Exception):
    """Cancel sign-in pressed before Google's page opened."""


SIGN_INS: dict[Path, SignIn] = {}  # by data folder: one sign-in at a time for each
LOCK = threading.Lock()


def data_file(conn: sqlite3.Connection) -> Path:
    """The database this connection opened; the token is kept beside it."""
    found = next((r["file"] for r in conn.execute("PRAGMA database_list") if r["name"] == "main"), "")
    if not found:
        raise FieldError("google", "Friday's database isn't in a folder, so there's nowhere to keep Google's token")
    return Path(found)


def demo(ctx: Ctx) -> bool:
    return bool(kv_get(ctx.conn, "demo", False, ctx.user_id))


@query("google_connect_status")
def google_connect_status(ctx: Ctx, inp: Empty) -> GoogleConnectOut:
    """How connecting Google is going, and what Google lets Friday do: read calendars, read mail, change events,
    for each account."""
    if demo(ctx):  # the sample term's stand-in Google is always connected, as the accounts it lists
        listed = kv_get(ctx.conn, "google_calendars", [], ctx.user_id)
        found = [a for a in dict.fromkeys(c.get("account") for c in listed) if a]
        accounts = [GoogleAccountOut(email=a, gmail=True, events=True) for a in found]
        return GoogleConnectOut(
            state="idle", client_file=True, calendar=True, gmail=True, events=True, accounts=accounts
        )
    folder = data_file(ctx.conn).parent
    sign_in = SIGN_INS.get(folder)
    mail = rows(ctx.conn, "SELECT config, last_error FROM sources WHERE user_id = ? AND kind = 'gmail'", [ctx.user_id])
    mail_errors = {json.loads(r["config"]).get("account", google_auth.LEGACY): r["last_error"] for r in mail}
    accounts = [
        GoogleAccountOut(
            email=account,
            gmail=google_auth.GMAIL_SCOPE in (info.get("scopes") or ()),
            events=google_auth.EVENTS_SCOPE in (info.get("scopes") or ()),
            mail_error=mail_errors.get(account),
        )
        for account, info in google_auth.tokens(folder).items()
    ]
    return GoogleConnectOut(
        state=sign_in.state if sign_in else "idle",
        message=sign_in.message if sign_in else None,
        url=sign_in.url if sign_in and sign_in.state == "waiting" else None,
        account=sign_in.account if sign_in else None,
        client_file=google_auth.client_to_use(ctx.settings["google"].client_file).exists(),
        calendar=bool(accounts),
        gmail=any(a.gmail for a in accounts),
        events=any(a.events for a in accounts),
        accounts=accounts,
    )


# Unlogged: it opens your browser, and what it brings back (the token) is a secret, not a change to undo.
@command("google_connect", logged=False)
def google_connect(ctx: Ctx, inp: GoogleConnectInput) -> GoogleConnectOut:
    """Connect a Google account: opens Google's page in your browser to let Friday read its calendars, and its mail
    when Gmail is on. Again, it adds another account, or with `account` signs that one in again. It returns at once;
    `google_connect_status` says how it goes."""
    if demo(ctx):
        raise FieldError("google", "the demo uses a stand-in Google, so there's nothing to connect")
    db = data_file(ctx.conn)
    client = google_auth.client_to_use(ctx.settings["google"].client_file)
    if not client.exists():
        raise FieldError("google", "Friday needs the key file from Google Cloud first")
    with LOCK:
        if (found := SIGN_INS.get(db.parent)) is None or found.state != "waiting":
            sign_in = SIGN_INS[db.parent] = SignIn(account=inp.account or None)
            asked = google_auth.scopes(ctx.settings["gmail"].enabled)  # as `fridayd google-login` asks
            sign_in.thread = threading.Thread(
                target=wait_for_google,
                args=(sign_in, db, client, asked, ctx.user_id, ctx.now_text),
                name="friday-google-sign-in",
                daemon=True,
            )
            sign_in.thread.start()
    return google_connect_status(ctx, Empty())


def wait_for_google(
    sign_in: SignIn, db: Path, client: Path, scopes: tuple[str, ...], user_id: int, now_text: str
) -> None:
    """The sign-in itself, in its own thread: the token is saved, every account's calendars listed and a sync made
    due."""

    def opened(url: str) -> None:
        if sign_in.cancelled:
            raise Cancelled
        sign_in.url = url

    try:
        account = google_auth.login(client, db.parent, scopes, WAIT_S, opened=opened, account=sign_in.account)
    except Exception as error:
        if sign_in.cancelled:  # Cancel sign-in already said so
            return
        log.warning("connecting Google didn't finish: %s: %s", type(error).__name__, error)
        sign_in.state, sign_in.message, sign_in.url = "failed", plainly(error), None
        return
    try:
        conn = connect(db)
        try:  # listed now, so Settings shows them the moment it says connected; the sync reads their events
            apis = google_auth.per_account(None, db.parent, google_auth.calendar)
            kv_set(conn, "google_calendars", list_calendars(conn, apis, user_id, db.parent)[0], user_id)
        finally:
            kv_set(conn, "sync_now", now_text, user_id)
            conn.close()
    except Exception as error:  # the token is kept; the sync job lists them within the minute instead
        log.warning("listing Google calendars after connecting failed: %s", error)
    log.info("Google connected: %s", account)
    sign_in.state, sign_in.message, sign_in.url, sign_in.account = "connected", None, None, account


@command("google_connect_cancel", logged=False)
def google_connect_cancel(ctx: Ctx, inp: Empty) -> GoogleConnectOut:
    """Cancel a sign-in waiting on Google's page, so you can start again (with another account, say). Google's page,
    if it's still open, connects nothing after this."""
    folder, url = data_file(ctx.conn).parent, None
    with LOCK:
        sign_in = SIGN_INS.get(folder)
        if sign_in is not None and sign_in.state == "waiting":
            url, sign_in.cancelled = sign_in.url, True
            sign_in.state, sign_in.message, sign_in.url = "idle", "Sign-in cancelled.", None
    if url:
        google_auth.stop(url)
    return google_connect_status(ctx, Empty())


# Unlogged: the token it deletes can't be brought back by an undo; connecting the account again does that.
@command("google_remove", logged=False)
def google_remove(ctx: Ctx, inp: GoogleAccountInput) -> GoogleConnectOut:
    """Remove a Google account: its token is deleted and Friday stops reading its calendars and mail. What they
    brought in stays; connect it again and its calendars are read again."""
    if demo(ctx):
        raise FieldError("google", "the demo uses a stand-in Google, so there's nothing to remove")
    folder = data_file(ctx.conn).parent
    if inp.account not in google_auth.tokens(folder):
        raise FieldError("account", f"{inp.account or 'that account'} isn't connected")
    google_auth.remove(folder, inp.account)
    let_go(ctx, inp.account, list(google_auth.tokens(folder)))
    log.info("Google account removed: %s", inp.account)
    return google_connect_status(ctx, Empty())


def plainly(error: Exception) -> str:
    """Why the sign-in failed, said for you rather than a programmer."""
    text = str(error)
    if isinstance(error, WSGITimeoutError):
        return "Google's page waited five minutes without an answer. Try again when you're ready."
    if "access_denied" in text:
        return (  # 8 Nov: everyone but the project's test users is blocked, and the old advice was the owner's
            "Google says Friday wasn't allowed, so nothing changed. If its page said access is blocked, Google isn't "
            "letting this account in yet: bring its calendars in through your Mac instead (Settings → Integrations → "
            "Calendars on this Mac) and its mail with an app password (Gmail, just below). If the Google Cloud "
            "project is your own, add the account as a test user there (Audience) and try again."
        )
    if "Scope has changed" in text:
        return "Some boxes on Google's page were left unticked. Try again and tick them all."
    if "invalid_client" in text or "unauthorized_client" in text or isinstance(error, ValueError):
        return "Google didn't accept the key file. Download it again from Google Cloud and choose it here."
    if isinstance(error, OSError):
        return "Friday couldn't reach Google. Check the internet connection, then try again."
    return f"Connecting didn't finish ({type(error).__name__}: {text[:160]}). Try again."


CLIENT_FIELDS = ("client_id", "client_secret", "auth_uri", "token_uri")


# Unlogged: the file holds the client's secret, and the log keeps every input.
@command("google_client_save", logged=False)
def google_client_save(ctx: Ctx, inp: GoogleClientInput) -> GoogleConnectOut:
    """Keep the OAuth client JSON you downloaded from Google Cloud (a Desktop app's) where `google.client_file`
    points, for Connect and `fridayd google-login`."""
    if len(inp.content) > 64_000:
        raise FieldError("file", "that file is too big to be Google's key file")
    try:
        found = json.loads(inp.content)
    except ValueError:
        found = None
    if isinstance(found, dict) and "web" in found:
        raise FieldError(
            "file",
            "that key is for a website. Friday needs one for a Desktop app: in Google Cloud, create an OAuth client "
            "ID of the type “Desktop app” and download that",
        )
    installed = found.get("installed") if isinstance(found, dict) else None
    if not isinstance(installed, dict) or not all(isinstance(installed.get(k), str) for k in CLIENT_FIELDS):
        raise FieldError("file", "that isn't Google's key file. It's the .json file Google Cloud downloads")
    google_auth.keep_client(google_auth.client_file(ctx.settings["google"].client_file), json.dumps(found))
    return google_connect_status(ctx, Empty())
