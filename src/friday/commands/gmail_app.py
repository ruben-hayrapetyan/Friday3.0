"""Gmail with an app password (8 Nov: users "can add their own gmails - right now it just errors out for them"):
your address and an app password from your Google account, checked with Gmail once, kept in secrets.toml beside
friday.toml (readable by you alone, never in settings, sent back or logged), and read like any Gmail from then on
(`sync/imap_mail.py`). No Google Cloud project, so it works for anyone with 2-Step Verification on."""

import json
import tomllib

from friday.api.commands import Changed, GmailAppInput
from friday.api.types import Empty
from friday.commands.ai import toml_of
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.planner.store import kv_set
from friday.sync import imap_mail
from friday.sync.google_auth import SECRETS_HELD, write_private


@command("gmail_app_set", logged=False)  # the password is never logged, so there is nothing to undo with
def gmail_app_set(ctx: Ctx, inp: GmailAppInput) -> Changed:
    address = inp.address.strip().lower()
    password = "".join(inp.password.split())
    if not password:
        return forget(ctx, address)
    if "@" not in address or " " in address:
        raise FieldError("address", "that isn't an email address: type the Gmail address the app password is for")
    if len(password) != 16 or not password.isalpha():
        raise FieldError(
            "password",
            f"an app password is 16 letters (Google shows it in four groups of four): make one at "
            f"{imap_mail.APP_PASSWORDS}. Your usual password won't work here",
        )
    try:
        imap_mail.check(address, password)
    except imap_mail.ImapRefused as error:
        raise FieldError("password", str(error)) from error
    except OSError as error:
        raise FieldError(
            "address", "Friday couldn't reach Gmail: check the internet connection, then try again"
        ) from error
    with SECRETS_HELD:  # one change to secrets.toml at a time: two at once lost one (audit, 12 Nov)
        kept = secrets()
        section = next((k for k, v in sections(kept).items() if v.get("address", "").lower() == address), None)
        taken = set(kept)
        section = section or next(s for s in [imap_mail.SECTION, *(f"{imap_mail.SECTION}_{n}" for n in range(2, 99))]
                                  if s not in taken)  # fmt: skip
        kept[section] = {"address": address, "password": password}
        write_private(secrets_path(), toml_of(kept))
    gmail = ctx.settings["gmail"]
    if not gmail.enabled:
        write_setting(ctx, "gmail", gmail.model_dump() | {"enabled": True})
    kv_set(ctx.conn, "sync_now", True, ctx.user_id)  # read within the minute
    return Changed(message=f"Gmail connected: Friday reads {address}'s new mail within the minute")


def forget(ctx: Ctx, address: str) -> Changed:
    with SECRETS_HELD:  # one change to secrets.toml at a time (audit, 12 Nov)
        kept = secrets()
        gone = [k for k, v in sections(kept).items() if v.get("address", "").lower() == address]
        if not gone:
            raise FieldError("address", f"{address or 'that address'} isn't connected with an app password")
        for k in gone:
            del kept[k]
        write_private(secrets_path(), toml_of(kept))
    switch_off(ctx, "gmail", address)
    return Changed(message=f"Removed: Friday no longer reads {address}. What its mail brought in stays")


def switch_off(ctx: Ctx, kind: str, address: str) -> None:
    """The mailbox's own source stops being read: its account, not every one with the address inside it (audit,
    12 Nov: forgetting bob@gmail.com switched off jimbob@gmail.com too)."""
    for source in rows(ctx.conn, "SELECT id, config FROM sources WHERE user_id = ? AND kind = ?", [ctx.user_id, kind]):
        if str(json.loads(source["config"] or "{}").get("account", "")).lower() == address:
            ctx.conn.execute("UPDATE sources SET enabled = 0 WHERE id = ?", [source["id"]])


@query("gmail_app_accounts")
def gmail_app_accounts(ctx: Ctx, inp: Empty) -> list[str]:
    """The addresses read with an app password; never their passwords."""
    return sorted(imap_mail.accounts())


def secrets() -> dict:
    path = secrets_path()
    kept = tomllib.loads(path.read_text()) if path.exists() else {}
    if any(not isinstance(v, dict) or any(isinstance(x, dict | list) for x in v.values()) for v in kept.values()):
        raise FieldError("password", f"{path} holds more than Friday writes there: add the app password to it by hand")
    return kept


def sections(kept: dict) -> dict[str, dict]:
    return {k: v for k, v in kept.items() if k == imap_mail.SECTION or k.startswith(f"{imap_mail.SECTION}_")}
