"""Google OAuth (DESIGN §22.10): your own Desktop OAuth client, the loopback flow once (Connect in Settings →
Integrations, or `fridayd google-login`), and the token in `data_dir/secrets.json` (mode 0600), refreshed as needed.
Only the scopes the features need."""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
DONE_PAGE = "Friday is connected to Google. You can close this tab and go back to Friday."


def secrets_file(folder: Path) -> Path:
    return folder / "secrets.json"


def client_file(named: str | None) -> Path:
    """The OAuth client JSON: where `google.client_file` says, else `google_client.json` beside friday.toml."""
    return Path(named).expanduser() if named else config_path().with_name("google_client.json")


def keep_client(path: Path, text: str) -> None:
    """Save the OAuth client JSON (it holds the client's secret), readable only by you."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        out.write(text)
    os.chmod(path, 0o600)


def scopes(mail: bool) -> tuple[str, ...]:
    """What a sign-in asks for: the calendars, changing your events, and your mail when Gmail is on."""
    return LOGIN_SCOPES + ((GMAIL_SCOPE,) if mail else ())


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
) -> None:
    """Open the browser for consent and keep the token; WSGITimeoutError after `wait_s` without an answer."""
    flow = Flow.from_client_secrets_file(str(client_file), list(scopes))
    flow.opened = opened
    # Asking again each time brings a new refresh token: without it, a second sign-in's token lasts an hour.
    creds = flow.run_local_server(
        port=0, open_browser=True, timeout_seconds=wait_s, success_message=DONE_PAGE, prompt="consent"
    )
    save(folder, creds)


def save(folder: Path, creds: Credentials) -> None:
    path = secrets_file(folder)
    kept = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps(kept | {"google": json.loads(creds.to_json())}))
    os.chmod(path, 0o600)


def credentials(folder: Path) -> Credentials | None:
    """The saved token, refreshed when expired; None before the first sign-in."""
    path = secrets_file(folder)
    info = json.loads(path.read_text()).get("google") if path.exists() else None
    if not info:
        return None
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        save(folder, creds)
    return creds


def calendar(folder: Path) -> Any | None:
    """The Calendar API, or None when not logged in."""
    creds = credentials(folder)
    return build("calendar", "v3", credentials=creds, cache_discovery=False) if creds else None


def gmail(folder: Path) -> Any | None:
    """The Gmail API, or None when not logged in or the login didn't include Gmail."""
    creds = credentials(folder)
    usable = creds is not None and creds.has_scopes([GMAIL_SCOPE])
    return build("gmail", "v1", credentials=creds, cache_discovery=False) if usable else None


def connected(folder: Path, scopes: tuple[str, ...] = ()) -> bool:
    """Logged in, with these scopes granted."""
    path = secrets_file(folder)
    info = json.loads(path.read_text()).get("google") if path.exists() else None
    return bool(info) and set(scopes) <= set(info.get("scopes") or ())
