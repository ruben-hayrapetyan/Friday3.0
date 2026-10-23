"""Google OAuth (DESIGN §22.10): your own Desktop OAuth client, the loopback flow once (`fridayd google-login`), and
the token in `data_dir/secrets.json` (mode 0600), refreshed as needed. Only the scopes the features need."""

import json
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.app.created",  # only the "Friday" calendar it makes
)
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def secrets_file(folder: Path) -> Path:
    return folder / "secrets.json"


def login(client_file: Path, folder: Path, scopes: tuple[str, ...] = CALENDAR_SCOPES) -> None:
    """Open the browser for consent and keep the token."""
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), list(scopes))
    save(folder, flow.run_local_server(port=0, open_browser=True))


def save(folder: Path, creds: Credentials) -> None:
    path = secrets_file(folder)
    kept = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps(kept | {"google": json.loads(creds.to_json())}))
    os.chmod(path, 0o600)


def credentials(folder: Path) -> Credentials | None:
    """The saved token, refreshed when expired; None before `fridayd google-login`."""
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
