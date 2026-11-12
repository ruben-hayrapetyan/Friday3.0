"""Mail beyond Gmail by app password (C99): iCloud Mail, Yahoo, Fastmail and other IMAP servers. The password is
checked with the server before it's kept, never logged, and kept only in secrets.toml; once one is kept, Friday reads
that inbox's new mail as it reads Gmail's (commands/mail.py), into a source of its own."""

import re

from friday.api.commands import Changed, MailAppAccount, MailAppForgetInput, MailAppInput
from friday.api.types import Empty
from friday.commands.ai import toml_of
from friday.commands.gmail_app import secrets, switch_off
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.items import FieldError
from friday.core.paths import secrets_path
from friday.integrations import outlook
from friday.planner.store import kv_set
from friday.sync import imap_any
from friday.sync.google_auth import write_private
from friday.sync.imap_mail import ImapRefused

HOST = r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"


@command("mail_app_set", logged=False)  # the password is never logged, so there is nothing to undo with
def mail_app_set(ctx: Ctx, inp: MailAppInput) -> Changed:
    provider = imap_any.PROVIDERS[inp.provider]
    address = inp.address.strip().lower()
    password = inp.password.strip()
    host = (inp.host or "").strip().lower() or None
    if "@" not in address or " " in address:
        raise FieldError("address", "that isn't an email address: type the address the app password is for")
    if not password:
        raise FieldError("password", f"paste the app password made at {provider.passwords}")
    if inp.provider == "other" and not (host and re.match(HOST, host)):
        raise FieldError("host", "the IMAP server's name, like imap.example.com (your provider's help says it)")
    try:
        imap_any.check(inp.provider, address, password, host)
    except ImapRefused as error:
        raise FieldError("password", str(error)) from error
    except OSError as error:
        raise FieldError(
            "address", f"Friday couldn't reach {provider.name}: check the connection and server"
        ) from error
    kept = secrets()
    mine = [
        k for k, v in kept.items() if k.startswith(imap_any.SECTION) and str(v.get("address", "")).lower() == address
    ]
    section = (
        mine[0]
        if mine
        else next(s for s in [imap_any.SECTION, *(f"{imap_any.SECTION}_{n}" for n in range(2, 99))] if s not in kept)
    )
    kept[section] = {"provider": inp.provider, "address": address, "password": password} | (
        {"host": host} if host else {}
    )
    write_private(secrets_path(), toml_of(kept))
    gmail = ctx.settings["gmail"]  # the mail settings every mailbox shares (what's read, the pre-filter)
    if not gmail.enabled:
        write_setting(ctx, "gmail", gmail.model_dump() | {"enabled": True})
    kv_set(ctx.conn, "sync_now", True, ctx.user_id)
    return Changed(message=f"{provider.name} connected: Friday reads {address}'s new mail within the minute")


@command("mail_app_forget", logged=False)
def mail_app_forget(ctx: Ctx, inp: MailAppForgetInput) -> Changed:
    address = inp.address.strip().lower()
    kept = secrets()
    gone = [
        k
        for k, v in kept.items()
        if k.startswith((imap_any.SECTION, outlook.SECTION)) and str(v.get("address", "")).lower() == address
    ]
    if not gone:
        raise FieldError("address", f"{address or 'that address'} isn't connected")
    for k in gone:
        del kept[k]
    write_private(secrets_path(), toml_of(kept))
    switch_off(ctx, "mail", address)
    return Changed(message=f"Removed: Friday no longer reads {address}. What its mail brought in stays")


def of_address(kept: dict, address: str) -> list[str]:
    """secrets.toml's sections for this mailbox."""
    return [
        k for k, v in kept.items() if k.startswith(imap_any.SECTION) and str(v.get("address", "")).lower() == address
    ]


@query("mail_app_accounts")
def mail_app_accounts(ctx: Ctx, inp: Empty) -> list[MailAppAccount]:
    """The mailboxes read by app password, and Outlook's by Microsoft's sign-in; never their passwords or tokens."""
    return [
        MailAppAccount(provider=a.provider, name=imap_any.PROVIDERS[a.provider].name, address=a.address)
        for a in imap_any.accounts()
    ] + [MailAppAccount(provider="outlook", name=outlook.NAME, address=a.address) for a in outlook.accounts()]
