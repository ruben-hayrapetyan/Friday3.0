"""Connecting Google from the app (DESIGN §22.10), no terminal needed: Connect starts the same loopback sign-in as
`fridayd google-login`. The server runs on your Mac, so the browser that opens is yours; the sign-in waits there in a
thread of its own, five minutes at most, while the page asks how it is going (`google_connect_status`). One at a time:
pressing again while it waits starts nothing new. Once you allow it, your calendars are listed at once and a sync is
due, so their events come in within the minute.

Without the OAuth client JSON Friday signs in with, the page takes the file you downloaded from Google Cloud and keeps
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

from friday.api.commands import GoogleClientInput
from friday.api.types import Empty
from friday.api.views import GoogleConnectOut
from friday.commands.registry import Ctx, command, query
from friday.core.db import connect
from friday.core.items import FieldError
from friday.planner.store import kv_get, kv_set
from friday.sync import gcal, google_auth

log = logging.getLogger("friday.google")
WAIT_S = 300  # how long Google's page may stay open before the sign-in gives up


@dataclass
class SignIn:
    state: Literal["waiting", "connected", "failed"] = "waiting"
    message: str | None = None
    url: str | None = None
    thread: threading.Thread | None = field(default=None, repr=False)


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
    """How connecting Google is going, and what Google lets Friday do: read calendars, read mail, change events."""
    if demo(ctx):  # the sample term's stand-in Google is always connected
        return GoogleConnectOut(state="idle", client_file=True, calendar=True, gmail=True, events=True)
    folder = data_file(ctx.conn).parent
    sign_in = SIGN_INS.get(folder)
    return GoogleConnectOut(
        state=sign_in.state if sign_in else "idle",
        message=sign_in.message if sign_in else None,
        url=sign_in.url if sign_in and sign_in.state == "waiting" else None,
        client_file=google_auth.client_file(ctx.settings["google"].client_file).exists(),
        calendar=google_auth.connected(folder),
        gmail=google_auth.connected(folder, (google_auth.GMAIL_SCOPE,)),
        events=google_auth.connected(folder, (google_auth.EVENTS_SCOPE,)),
    )


# Unlogged: it opens your browser, and what it brings back (the token) is a secret, not a change to undo.
@command("google_connect", logged=False)
def google_connect(ctx: Ctx, inp: Empty) -> GoogleConnectOut:
    """Connect Google: opens Google's page in your browser to let Friday read your calendars.
    Your mail too when Gmail is on. It returns at once; `google_connect_status` says how it goes."""
    if demo(ctx):
        raise FieldError("google", "the demo uses a stand-in Google, so there's nothing to connect")
    db = data_file(ctx.conn)
    client = google_auth.client_file(ctx.settings["google"].client_file)
    if not client.exists():
        raise FieldError("google", "Friday needs the key file from Google Cloud first")
    with LOCK:
        if (found := SIGN_INS.get(db.parent)) is None or found.state != "waiting":
            sign_in = SIGN_INS[db.parent] = SignIn()
            asked = google_auth.scopes(ctx.settings["gmail"].enabled)  # as `fridayd google-login` asks
            sign_in.thread = threading.Thread(
                target=wait_for_google,
                args=(sign_in, db, client, asked, ctx.user_id, ctx.now_text),
                name="friday-google-sign-in",
                daemon=True,
            )
            sign_in.thread.start()
    return google_connect_status(ctx, inp)


def wait_for_google(
    sign_in: SignIn, db: Path, client: Path, scopes: tuple[str, ...], user_id: int, now_text: str
) -> None:
    """The sign-in itself, in its own thread: the token is saved, the calendars listed and a sync made due."""

    def opened(url: str) -> None:
        sign_in.url = url

    try:
        google_auth.login(client, db.parent, scopes, WAIT_S, opened=opened)
    except Exception as error:
        log.warning("connecting Google didn't finish: %s: %s", type(error).__name__, error)
        sign_in.state, sign_in.message, sign_in.url = "failed", plainly(error), None
        return
    try:
        conn = connect(db)
        try:  # listed now, so Settings shows them the moment it says connected; the sync reads their events
            kv_set(conn, "google_calendars", gcal.calendars(google_auth.calendar(db.parent)), user_id)
        finally:
            kv_set(conn, "sync_now", now_text, user_id)
            conn.close()
    except Exception as error:  # the token is kept; the sync job lists them within the minute instead
        log.warning("listing Google calendars after connecting failed: %s", error)
    log.info("Google connected")
    sign_in.state, sign_in.message, sign_in.url = "connected", None, None


def plainly(error: Exception) -> str:
    """Why the sign-in failed, said for you rather than a programmer."""
    text = str(error)
    if isinstance(error, WSGITimeoutError):
        return "Google's page waited five minutes without an answer. Press Connect to try again."
    if "access_denied" in text:
        return "Google says you didn't allow Friday, so it isn't connected. Press Connect to try again."
    if "Scope has changed" in text:
        return "Some boxes on Google's page were left unticked. Press Connect again and tick them all."
    if "invalid_client" in text or "unauthorized_client" in text or isinstance(error, ValueError):
        return "Google didn't accept the key file. Download it again from Google Cloud and choose it here."
    if isinstance(error, OSError):
        return "Friday couldn't reach Google. Check the internet connection, then press Connect again."
    return f"Connecting didn't finish ({type(error).__name__}: {text[:160]}). Press Connect to try again."


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
