"""Google OAuth (DESIGN §22.10): your own Desktop OAuth client, the loopback flow once per account (Connect in
Settings → Integrations, or `fridayd google-login`), and each account's token in `data_dir/secrets.json` (mode 0600)
under its address, refreshed as needed. Only the scopes the features need.

Several accounts may be connected (a personal one and a school one, say). Signing in again with one already there
replaces its token. A token saved before Friday kept several sits under `google` with no address; it counts as one
account (`LEGACY`) until the sync lists its calendars, whose primary one names it, and it moves under that name."""

import contextlib
import json
import os
import sys
import tempfile
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from friday.core.paths import config_path

CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.app.created",  # only the "Friday" calendar it makes
)
# Editing your events from Friday (COMBINED.md 69) needs this as well; asked for at every sign-in, and an older login
# without it keeps reading but can't write.
EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
LOGIN_SCOPES = (*CALENDAR_SCOPES, EVENTS_SCOPE)
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"  # Google Tasks (C110): asked for once you connect it
DONE_PAGE = "Friday is connected to Google. You can close this tab and go back to Friday."
LEGACY = ""  # the account of the one token kept before Friday kept several, until its address is known
LOCK = threading.Lock()  # the sync, a sign-in and Remove may all rewrite the file
# Friday's own Desktop client, put beside the server's Python by Mac/bundle.sh, so a downloaded Friday connects Google
# with nothing to set up (HOSTED.md H112, on rhayrapetyan/download-site). Never in git: the repo will be open source.
SHIPPED_CLIENT = Path(sys.prefix) / "share" / "friday" / "google_client.json"


def secrets_file(folder: Path) -> Path:
    return folder / "secrets.json"


def client_file(named: str | None) -> Path:
    """Your own OAuth client JSON: where `google.client_file` says, else `google_client.json` beside friday.toml."""
    return Path(named).expanduser() if named else config_path().with_name("google_client.json")


def client_to_use(named: str | None) -> Path:
    """The client Friday signs in with: yours if you keep one, else the one shipped in the app, else yours (missing,
    so Settings asks for it)."""
    yours = client_file(named)
    return SHIPPED_CLIENT if not yours.exists() and SHIPPED_CLIENT.exists() else yours


def write_private(path: Path, text: str) -> None:
    """Write a file only you can read, from its first byte. Written beside it, then put in its place in one step:
    emptied and then written, a read meanwhile (a sync's token, on another thread) found nothing in it, and one
    written back from that read kept only its own section, every other key and password gone."""
    path = path.resolve()  # a link (a dotfiles folder's) keeps pointing at the file
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")  # 0600 from the start
    try:
        with os.fdopen(handle, "w") as out:
            out.write(text)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    os.chmod(path, 0o600)


def keep_client(path: Path, text: str) -> None:
    """Save the OAuth client JSON (it holds the client's secret), readable only by you."""
    write_private(path, text)


def scopes(mail: bool, tasks: bool = False) -> tuple[str, ...]:
    """What a sign-in asks for: the calendars, changing your events, your mail when Gmail is on, and your tasks once
    Google Tasks is wanted (so signing in again for the mail doesn't take Tasks away)."""
    return LOGIN_SCOPES + ((GMAIL_SCOPE,) if mail else ()) + ((TASKS_SCOPE,) if tasks else ())


class Flow(InstalledAppFlow):
    """The loopback flow, telling `opened` the address of the Google page it opens (to open it again)."""

    opened: Callable[[str], None] | None = None

    def authorization_url(self, **kwargs: Any) -> tuple[str, str]:
        url, state = super().authorization_url(**kwargs)
        if self.opened is not None:
            self.opened(url)
        return url, state


def login(
    client_file: Path,
    folder: Path,
    scopes: tuple[str, ...] = LOGIN_SCOPES,
    wait_s: int | None = None,
    opened: Callable[[str], None] | None = None,
    account: str | None = None,
) -> str:
    """Open the browser for consent and keep the token under the account's address, which it returns;
    WSGITimeoutError after `wait_s` without an answer. `account` (one already connected) goes straight to it."""
    flow = Flow.from_client_secrets_file(str(client_file), list(scopes))
    flow.opened = opened
    # Asking again each time brings a new refresh token: without it, a second sign-in's token lasts an hour. Google
    # would otherwise sign in whichever account the browser is signed in to, so it asks which, unless told.
    asking = {"prompt": "consent", "login_hint": account} if account else {"prompt": "select_account consent"}
    creds = flow.run_local_server(
        port=0, open_browser=True, timeout_seconds=wait_s, success_message=DONE_PAGE, **asking
    )
    found = address(build("calendar", "v3", credentials=creds, cache_discovery=False))
    save(folder, found, creds)
    return found


def stop(url: str) -> None:
    """End a sign-in waiting on Google's page `url`: its address on this Mac gets Google's "access denied", as when
    you click Cancel on Google's page, so the flow stops now instead of when it times out."""
    asked = parse_qs(urlsplit(url).query)
    back, state = asked.get("redirect_uri", [""])[0], asked.get("state", [""])[0]
    if not back.startswith(("http://localhost:", "http://127.0.0.1:")):
        return
    try:
        with urllib.request.urlopen(f"{back}?{urlencode({'error': 'access_denied', 'state': state})}", timeout=3):
            pass
    except OSError:  # it had finished or given up already
        pass


def address(service: Any) -> str:
    """The account's address: its primary calendar's id is the address."""
    return str(service.calendarList().get(calendarId="primary").execute()["id"])


def kept(folder: Path) -> dict[str, Any]:
    path = secrets_file(folder)
    return json.loads(path.read_text()) if path.exists() else {}


def tokens(folder: Path) -> dict[str, dict[str, Any]]:
    """Each connected account's token, by address, in the order they were added (the one from before first)."""
    found = kept(folder)
    old = {LEGACY: found["google"]} if found.get("google") else {}
    return old | dict(found.get("google_accounts") or {})


def accounts(folder: Path, scopes: tuple[str, ...] = ()) -> list[str]:
    """The connected accounts that granted these scopes."""
    return [a for a, info in tokens(folder).items() if set(scopes) <= set(info.get("scopes") or ())]


def connected(folder: Path, scopes: tuple[str, ...] = ()) -> bool:
    """Some account is connected with these scopes granted."""
    return bool(accounts(folder, scopes))


Accounts = dict[str, dict[str, Any]]


def rewrite(folder: Path, change: Callable[[dict[str, Any], Accounts], Accounts]) -> None:
    """Change the saved accounts (`change` gets the whole file and its accounts, and gives the accounts back) and
    write the file again. Whatever else the file keeps stays."""
    with LOCK:
        found = kept(folder)
        found["google_accounts"] = change(found, dict(found.get("google_accounts") or {}))
        write_private(secrets_file(folder), json.dumps(found))


def save(folder: Path, account: str, creds: Credentials) -> None:
    info = json.loads(creds.to_json())

    def put(found: dict[str, Any], saved: Accounts) -> Accounts:
        if account == LEGACY:
            found["google"] = info
            return saved
        return saved | {account: info}

    rewrite(folder, put)


def adopt(folder: Path, account: str) -> None:
    """The token from before Friday kept several, now that its address is known, kept under it (still first);
    dropped when that account has signed in again since, whose newer token stays."""

    def move(found: dict[str, Any], saved: Accounts) -> Accounts:
        old = found.pop("google", None)
        return saved if not old or account in saved else {account: old} | saved

    if account != LEGACY and kept(folder).get("google"):
        rewrite(folder, move)


def remove(folder: Path, account: str) -> None:
    """Forget an account's token; Friday stops reading it."""

    def drop(found: dict[str, Any], saved: Accounts) -> Accounts:
        if account == LEGACY:
            found.pop("google", None)
        return {a: info for a, info in saved.items() if a != account}

    rewrite(folder, drop)


def credentials(folder: Path, account: str | None = None) -> Credentials | None:
    """An account's token (the first account's when none is named), refreshed when expired; None when not
    connected."""
    found = tokens(folder)
    account = next(iter(found), None) if account is None else account
    info = found.get(account) if account is not None else None
    if not info or account is None:
        return None
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        save(folder, account, creds)
    return creds


def calendar(folder: Path, account: str | None = None) -> Any | None:
    """The Calendar API for an account (the first's when none is named), or None when not connected; only for reading
    in a test Friday (`READ_ONLY`)."""
    creds = credentials(folder, account)
    if creds is None:
        return None
    api = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return Reading(api) if os.environ.get(READ_ONLY) == "1" else api


READ_ONLY = "FRIDAY_CALENDARS_READ_ONLY"  # set by Friday Test (Mac/build.sh --test) and scripts/fresh_user.sh


class ReadOnlyCalendars(Exception):
    """A change to a Google calendar, refused: this Friday only reads them."""


class Reading:
    """The Calendar API, reading only (29 Oct): a test Friday, a brand-new user's beside yours, may be signed in with
    your real account, and must never change its calendars. Lists and gets go through; asking for a change fails as
    Google failing would, so an event's change is kept and the status line says it couldn't be saved."""

    CHANGES = frozenset({"insert", "patch", "update", "delete", "move", "import_", "quickAdd", "clear", "watch"})

    def __init__(self, api: Any) -> None:
        self.api = api

    def __getattr__(self, name: str) -> Any:
        if name in self.CHANGES:
            raise ReadOnlyCalendars("a test Friday never changes a real calendar")
        found = getattr(self.api, name)
        if not callable(found):
            return found

        def call(*args: Any, **kwargs: Any) -> Any:
            out = found(*args, **kwargs)
            data = name == "execute" or out is None or isinstance(out, (dict, list, str, bytes, int, float))
            return out if data else Reading(out)  # events(), calendars(), a request: more of the API

        return call


def gmail(folder: Path, account: str | None = None) -> Any | None:
    """The Gmail API for an account (the first's when none is named), or None when not connected or its login
    didn't include Gmail."""
    creds = credentials(folder, account)
    usable = creds is not None and creds.has_scopes([GMAIL_SCOPE])
    return build("gmail", "v1", credentials=creds, cache_discovery=False) if usable else None


Api = Callable[[], Any]  # an account's API, made when first used: making it may refresh the token, and fail


def per_account(
    given: Any, folder: Path | None, make: Callable[[Path, str], Any], needs: tuple[str, ...] = ()
) -> dict[str, Api]:
    """The API of each connected account that granted `needs` (`make` is `calendar` or `gmail`). A stand-in `given`
    (tests, the demo) is one API for an account not named, or one per account by address."""
    if given is not None:
        pairs = given.items() if isinstance(given, dict) else [(LEGACY, given)]
        return {account: (lambda api=api: api) for account, api in pairs}
    if folder is None:
        return {}
    return {account: (lambda account=account: make(folder, account)) for account in accounts(folder, needs)}


def which(apis: dict[str, Any], account: str | None) -> str | None:
    """The account whose API reads or writes a calendar of `account`: that one; else the one whose address isn't
    known yet, which may be it; else, for a calendar listed before Friday kept several accounts, the first."""
    if account in apis:
        return account
    if LEGACY in apis:
        return LEGACY
    return next(iter(apis), None) if not account else None
