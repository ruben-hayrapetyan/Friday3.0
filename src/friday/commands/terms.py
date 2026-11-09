"""Accepting Friday's terms (PROGRESS.md C71, 9 Nov: everyone accepts them, and people already using Friday get "a
popup on their screen" and accept before going on). The app stays locked on a page with the terms, Accept and Quit
until `needed` is false; each change to the terms asks again. Each acceptance is kept, with its time, as the record
that you agreed; only you can accept, never an assistant (registry.YOURS_ONLY)."""

import json

from friday.api.commands import Changed, TermsAcceptInput, TermsOut
from friday.api.types import Empty
from friday.commands.registry import Ctx, command, query
from friday.core import terms
from friday.core.items import FieldError
from friday.planner.store import kv_get

ACCEPTED = "terms_accepted"  # kv: every acceptance, oldest first: {"version", "at"}


def accepted_version(ctx: Ctx) -> str | None:
    found = kv_get(ctx.conn, ACCEPTED, [], ctx.user_id) or []
    return found[-1]["version"] if found else None


@query("terms")
def terms_now(ctx: Ctx, inp: Empty) -> TermsOut:
    """Friday's terms, and whether you have yet to accept them."""
    now, accepted = terms.current(), accepted_version(ctx)
    return TermsOut(
        version=now.version,
        text=now.text,
        changes=list(now.changes),
        accepted=accepted,
        needed=accepted != now.version,
    )


@command("terms_accept")
def terms_accept(ctx: Ctx, inp: TermsAcceptInput) -> Changed:
    """Accept Friday's terms, the version you read."""
    now = terms.current()
    if inp.version != now.version:
        raise FieldError("version", "These terms changed while you were reading them: read the new ones first")
    found = kv_get(ctx.conn, ACCEPTED, [], ctx.user_id) or []
    ctx.db.upsert(
        "kv",
        {"user_id": ctx.user_id, "key": ACCEPTED},
        {"value": json.dumps([*found, {"version": now.version, "at": ctx.now_text}])},
    )
    return Changed(message="Thanks: you've accepted Friday's terms")
