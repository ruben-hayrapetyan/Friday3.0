"""Questions Friday asks you, set aside with "Not now" (PROGRESS.md C75, 9 Nov: "anything that needs the user's
attention (like questions friday asks to the user) should go into inbox instead of insights"; your answer: "Not now"
asks again once Friday has more to go on). Each is kept with the evidence it was based on (how many timed things, the
learned time); the Inbox leaves it out while that evidence is the same, and asks again when it changes. Kept here, not
in the browser, so the Mac and your phone count the same Inbox."""

import json

from friday.api.commands import AskLaterInput, AsksLaterOut, Changed
from friday.api.types import Empty
from friday.commands.registry import Ctx, command, query
from friday.core.items import FieldError
from friday.planner.store import kv_get

LATER = "asks_later"  # kv: {question key: the evidence it had}


@query("asks_later")
def asks_later(ctx: Ctx, inp: Empty) -> AsksLaterOut:
    """The questions you said "Not now" to, with the evidence each had."""
    return AsksLaterOut(later=kv_get(ctx.conn, LATER, {}, ctx.user_id) or {})


@command("ask_later")
def ask_later(ctx: Ctx, inp: AskLaterInput) -> Changed:
    """Not now: out of the Inbox until Friday has more to go on."""
    if not inp.key.strip():
        raise FieldError("key", "say which question")
    later = (kv_get(ctx.conn, LATER, {}, ctx.user_id) or {}) | {inp.key: inp.evidence}
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": LATER}, {"value": json.dumps(later)})
    return Changed(message="Not now: Friday asks again once it knows more")
