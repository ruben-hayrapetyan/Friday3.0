"""Friday on your phone, over Tailscale (C61, 8 Nov, your answers: your Mac and phone are both on your tailnet; the
phone can do everything; it pairs by scanning a QR code; it stays paired until you remove it). Settings → Phone
switches it on: Friday then also answers at the Mac's Tailscale address (server/phone.py). A device that isn't the
Mac itself must be paired: the Mac shows a QR code holding a one-time code, good for ten minutes; the phone's camera
opens it, and the phone keeps a sign-in of its own (only its hash is kept here) until you remove it."""

import hashlib
import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from friday.api.commands import Changed, PhoneRef, PhoneSetInput
from friday.api.types import Empty
from friday.api.views import PairCode, PairedPhone, PhoneStatus
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.items import FieldError
from friday.core.time import format_utc
from friday.planner.store import kv_get

PAIR_MINUTES = 10
COOKIE = "friday_phone"


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def stored(conn: sqlite3.Connection, user_id: int, key: str) -> dict[str, Any]:
    return kv_get(conn, key, {}, user_id) or {}


def store(conn: sqlite3.Connection, user_id: int, key: str, value: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO kv (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT (user_id, key) "
        "DO UPDATE SET value = excluded.value",
        [user_id, key, json.dumps(value)],
    )


def yours_only(ctx: Ctx) -> None:
    """Who may open Friday is yours to say: an assistant's token never reaches it (review, 8 Nov: mail an assistant
    read could have steered it to switch this on and hand out a code)."""
    if ctx.actor.startswith("mcp:"):
        raise FieldError("phone", "Only you can change who opens your Friday: do it in Settings → Phone")


@command("phone_set")
def phone_set(ctx: Ctx, inp: PhoneSetInput) -> Changed:
    """Use Friday on your phone over Tailscale, or stop: off, Friday answers on this Mac alone."""
    yours_only(ctx)
    write_setting(ctx, "phone", ctx.settings["phone"].model_dump() | {"on": inp.on})
    if inp.on:
        return Changed(message="Friday answers on your tailnet now: pair your phone with the code in Settings → Phone")
    return Changed(message="Friday answers on this Mac alone now; paired phones stay paired for when it's back on")


# Unlogged: the command log keeps every result, and this one holds the code.
@command("phone_pair", logged=False)
def phone_pair(ctx: Ctx, inp: Empty) -> PairCode:
    """A one-time code for the QR code a phone scans to pair, good for ten minutes."""
    yours_only(ctx)
    if not ctx.settings["phone"].on:
        raise FieldError("phone", "Switch on Use Friday on my phone first")
    from friday.sync.tailnet import address, name

    where = name() or address()
    if where is None:
        raise FieldError("phone", "This Mac isn't on Tailscale right now: open Tailscale and sign in, then try again")
    code = secrets.token_urlsafe(18)
    # alone: a code a phone used a moment ago isn't written back, to work again (audit, 12 Nov)
    with alone(ctx.conn):
        codes = {h: c for h, c in stored(ctx.conn, ctx.user_id, "phone_codes").items() if c["until"] > ctx.now_utc}
        codes[digest(code)] = {"until": ctx.now_utc + PAIR_MINUTES}
        store(ctx.conn, ctx.user_id, "phone_codes", codes)
    # The code after the #: a browser never sends that part, so it's in no address log on the way.
    url = f"http://{where}:{ctx.settings['server'].port}/pair#{code}"
    return PairCode(url=url, svg=qr_svg(url), minutes=PAIR_MINUTES)


def qr_svg(text: str) -> str:
    """The QR code a phone's camera opens, as SVG (segno: 8 Nov, your choice of a library for it)."""
    import segno

    return segno.make(text, error="m").svg_inline(scale=6, border=2, dark="#111", light="#fff")


@contextmanager
def alone(conn: sqlite3.Connection) -> Iterator[None]:
    """Read, change and write back with nothing else writing between (review, 8 Nov: a phone just removed could be
    written back by a request reading it a moment before; one code could pair two phones at once). Inside a
    command's own transaction already, that one holds."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def pair(conn: sqlite3.Connection, user_id: int, code: str, device: str, now_utc: int) -> str | None:
    """Trade a pairing code for a phone's own sign-in: the code works once, within its ten minutes. None: it doesn't."""
    with alone(conn):
        return paired(conn, user_id, code, device, now_utc)


def paired(conn: sqlite3.Connection, user_id: int, code: str, device: str, now_utc: int) -> str | None:
    codes = stored(conn, user_id, "phone_codes")
    found = codes.pop(digest(code), None)
    store(conn, user_id, "phone_codes", codes)
    if found is None or found["until"] <= now_utc:
        return None
    session = "ph_" + secrets.token_urlsafe(32)
    phones = stored(conn, user_id, "phones")
    name = device
    n = 2
    while any(p["name"] == name for p in phones.values()):
        name, n = f"{device} {n}", n + 1
    paired = {"hash": digest(session), "name": name, "paired": format_utc(now_utc), "last_used": None}
    phones[secrets.token_hex(6)] = paired
    store(conn, user_id, "phones", phones)
    return session


def known(conn: sqlite3.Connection, user_id: int, session: str, now_utc: int) -> bool:
    """A paired phone's sign-in, noting when it was last used (at most once a minute)."""
    with alone(conn):
        return noted(conn, user_id, session, now_utc)


def noted(conn: sqlite3.Connection, user_id: int, session: str, now_utc: int) -> bool:
    phones = stored(conn, user_id, "phones")
    for p in phones.values():
        if secrets.compare_digest(p["hash"], digest(session)):
            if p["last_used"] != format_utc(now_utc):
                p["last_used"] = format_utc(now_utc)
                store(conn, user_id, "phones", phones)
            return True
    return False


@command("phone_forget")
def phone_forget(ctx: Ctx, inp: PhoneRef) -> Changed:
    """Remove a paired phone: it can't open Friday again until it's paired again."""
    yours_only(ctx)
    phones = stored(ctx.conn, ctx.user_id, "phones")
    gone = phones.pop(inp.id, None)
    if gone is None:
        raise FieldError("id", "That phone isn't paired any more")
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "phones"}, {"value": json.dumps(phones)})
    return Changed(message=f"Removed {gone['name']}: it can't open Friday until it's paired again")


@query("phone_status")
def phone_status(ctx: Ctx, inp: Empty) -> PhoneStatus:
    """Whether Friday answers on your tailnet, at what address, and the phones paired with it."""
    from friday.sync.tailnet import address, name  # what this Mac's Tailscale says, read when asked

    phones = [
        PairedPhone(id=k, name=p["name"], paired=ctx.local(p["paired"]) or "", last_used=ctx.local(p["last_used"]))
        for k, p in stored(ctx.conn, ctx.user_id, "phones").items()
    ]
    return PhoneStatus(on=ctx.settings["phone"].on, address=address(), name=name(), phones=phones)
