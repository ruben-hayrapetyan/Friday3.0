"""What only you can decide, waiting in the Inbox (27 Oct: "remove notifications and put that under review…
decisions but in the inbox with a notification symbol and a way to let the user know to actually go check it").

- A lock that makes work late: keep it (`lock_keep`) or let it move (`resolve`). Until you answer, the plan keeps it;
  nothing waits on you. Only a lock that makes work a quarter hour late or more is asked about
  (`planner.service.ASK_FROM_HOURS`).
- Work that will be late: the options (skip an event, a later night, …), or leave it late (`late_accept`).

An answer stands until it costs an hour more: a lock you kept, or lateness you accepted, is asked about again only
when the work it's about gets an hour later than when you answered."""

import json

from friday.api.commands import Changed, LateAcceptInput, LockKeepInput
from friday.api.views import Decision, LateItem
from friday.commands.registry import Ctx, command
from friday.core.items import FieldError
from friday.core.time import ampm, parse_utc, to_local
from friday.planner.store import current_plan, kv_get

AGAIN_HOURS = 1.0  # an answer is asked again once the work it's about is this much later


def decisions(ctx: Ctx, report: dict, late: list[LateItem]) -> list[Decision]:
    """The current plan's questions for you, late work first, without those you answered."""
    out = []
    accepted = kv_get(ctx.conn, "late_accepted", {}, ctx.user_id) or {}
    asked = [i for i in late if not answered(accepted, i.item_id, i.hours)]
    if asked:
        out.append(
            Decision(
                key="late",
                kind="late",
                title=f"{asked[0].title} will be late" if len(asked) == 1 else f"{len(asked)} things will be late",
                detail="Friday can make room (skip an event, a later night, something softer later), or leave it late.",
                hours=round(sum(i.hours for i in asked), 2),
                items=asked,
            )
        )
    kept = kv_get(ctx.conn, "locks_kept", {}, ctx.user_id) or {}
    for c in report.get("conflicts", []):
        if answered(kept, c["pin_id"], c["extra_late_hours"]):
            continue
        at = to_local(parse_utc(c["start"]), ctx.tz)
        out.append(
            Decision(
                key=f"lock:{c['pin_id']}",
                kind="lock",
                title=f"Keep {c['title']} where you locked it?",
                detail=f"Locked at {at:%a} {ampm(at)}, it makes other work {spoken(c['extra_late_hours'])} later.",
                pin_id=c["pin_id"],
                item_id=c["item_id"],
                start=ctx.local(c["start"]),
                hours=c["extra_late_hours"],
            )
        )
    return out


def answered(answers: dict, key: int, hours: float) -> bool:
    """Whether an answer about `key` still stands: given, and the work it's about isn't an hour later since."""
    was = answers.get(str(key))
    return was is not None and hours < was + AGAIN_HOURS


def spoken(hours: float) -> str:
    """20 min, 1h 10m, 3h."""
    minutes = max(1, round(hours * 60))
    whole, rest = divmod(minutes, 60)
    return f"{whole}h {rest}m" if whole and rest else f"{whole}h" if whole else f"{rest} min"


def report_of(ctx: Ctx) -> dict:
    saved = current_plan(ctx.conn, ctx.user_id)
    return json.loads(saved["report"]) if saved else {}


@command("lock_keep")
def lock_keep(ctx: Ctx, inp: LockKeepInput) -> Changed:
    """Keep locks that make work late where they are; asked again only if they make work an hour later."""
    asked = {c["pin_id"]: c for c in report_of(ctx).get("conflicts", [])}
    kept = dict(kv_get(ctx.conn, "locks_kept", {}, ctx.user_id) or {})
    for pin_id in inp.pin_ids:
        if pin_id not in asked:
            raise FieldError("pin_ids", f"lock {pin_id} isn't making work late")
        kept[str(pin_id)] = asked[pin_id]["extra_late_hours"]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "locks_kept"}, {"value": json.dumps(kept)})
    titles = ", ".join(asked[p]["title"] for p in inp.pin_ids)
    return Changed(message=f"Kept {titles}")


@command("late_accept")
def late_accept(ctx: Ctx, inp: LateAcceptInput) -> Changed:
    """Leave work late: not asked about again unless it gets an hour later."""
    late = {int(k): hours for k, hours in report_of(ctx).get("late_hours", {}).items()}
    accepted = kv_get(ctx.conn, "late_accepted", {}, ctx.user_id) or {}
    # What's no longer late is forgotten: late again, it's asked again.
    kept = {k: v for k, v in accepted.items() if int(k) in late}
    for item_id in inp.item_ids:
        if item_id not in late:
            raise FieldError("item_ids", f"item {item_id} isn't late")
        kept[str(item_id)] = late[item_id]
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "late_accepted"}, {"value": json.dumps(kept)})
    return Changed(message="Left late" if len(inp.item_ids) != 1 else "Left it late")
