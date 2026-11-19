"""What only you can decide, waiting in the Inbox (27 Oct: "remove notifications and put that under review…
decisions but in the inbox with a notification symbol and a way to let the user know to actually go check it").

- A lock that makes work late: keep it (`lock_keep`) or let it move (`resolve`). Until you answer, the plan keeps it;
  nothing waits on you. Only a lock that makes work a quarter hour late or more is asked about
  (`planner.service.ASK_FROM_HOURS`).
- Work that will be late: the options (skip an event, a later night, …), or leave it late (`late_accept`).

An answer stands until it costs an hour more: a lock you kept is asked about again only when the work it's about gets
an hour later than when you answered. Leaving work late stands a day, whatever you add, and after that until it's an
hour later than when you answered (19 Nov, a user: asked "3-5 times in the last few hours", every add making it an
hour later; your choice "A day, then only if later"). It's kept until the work is done or dropped."""

import json

from friday.api.commands import Changed, LateAcceptInput, LockKeepInput
from friday.api.views import Decision, DecisionOption, LateItem
from friday.commands.registry import Ctx, command
from friday.core.items import FieldError
from friday.core.time import clock_time, parse_utc, to_local
from friday.planner.service import ASK_FROM_HOURS
from friday.planner.store import current_plan, kv_get

AGAIN_HOURS = 1.0  # an answer is asked again once the work it's about is this much later
QUIET_MIN = 24 * 60  # leaving work late isn't asked about again for a day, however much later it gets


def decisions(ctx: Ctx, report: dict, late: list[LateItem]) -> list[Decision]:
    """The current plan's questions for you, late work first, without those you answered; then where what Friday
    learned disagrees with what you said (commands/conflicts.py)."""
    out = []
    accepted = kv_get(ctx.conn, "late_accepted", {}, ctx.user_id) or {}
    asked = [i for i in late if not answered(accepted, i.item_id, i.hours, ctx.now_utc)]
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
                detail=f"Locked at {at:%a} {clock_time(at)}, {lock_cost(c)}",
                pin_id=c["pin_id"],
                item_id=c["item_id"],
                start=ctx.local(c["start"]),
                hours=c["extra_late_hours"],
            )
        )
    from friday.commands.conflicts import clashes  # noqa: PLC0415 (conflicts reads the rules, which read the plan)

    for c in clashes(ctx):
        out.append(
            Decision(
                key=f"learned:{c.key}",
                kind="learned",
                title=c.title,
                detail=c.detail,
                update=c.update,
                options=[
                    DecisionOption(id=o.id, label=o.label, detail=o.detail, recommended=o.recommended)
                    for o in c.options
                ],  # fmt: skip
            )
        )
    return out


def answered(answers: dict, key: int, hours: float, now_utc: int | None = None) -> bool:
    """Whether an answer about `key` still stands: given, and the work it's about isn't an hour later since. Leaving
    work late (an answer that keeps when it was given) also stands for a day after it, however much later."""
    was = answers.get(str(key))
    if was is None:
        return False
    if isinstance(was, dict):
        if now_utc is not None and now_utc - was["at"] < QUIET_MIN:
            return True
        was = was["hours"]
    return hours < was + AGAIN_HOURS


def lock_cost(conflict: dict) -> str:
    """What a lock makes later, by name: "it makes essay finish 3h later and lab 20 min later." (18 Nov: "it makes
    other work 164h 15m later" was hours summed over several things, read as Friday planning 164 hours ahead.) And,
    when letting it move would make it later itself, by how much."""
    later = conflict.get("later")
    if not later:  # a plan saved before the work was named
        return f"it makes other work {spoken(conflict['extra_late_hours'])} later."
    first = f"{later[0]['title']} finish {spoken(later[0]['hours'])} later"
    if len(later) == 2:
        first += f" and {later[1]['title']} {spoken(later[1]['hours'])} later"
    elif len(later) > 2:
        first += f", and {len(later) - 1} other things later too"
    said = f"it makes {first}."
    if conflict.get("itself_hours", 0) >= ASK_FROM_HOURS:
        said += f" Let go, it would finish {spoken(conflict['itself_hours'])} later itself."
    return said


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
    # Kept until the work is done or dropped (19 Nov: answers for work not late just then were forgotten, and asked
    # again as soon as it was late again).
    open_ids = {
        r[0] for r in ctx.conn.execute("SELECT id FROM items WHERE user_id = ? AND status = 'todo'", [ctx.user_id])
    }
    kept = {k: v for k, v in accepted.items() if int(k) in open_ids}
    for item_id in inp.item_ids:
        if item_id not in late:
            raise FieldError("item_ids", f"item {item_id} isn't late")
        kept[str(item_id)] = {"hours": late[item_id], "at": ctx.now_utc}
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "late_accepted"}, {"value": json.dumps(kept)})
    return Changed(message="Left late" if len(inp.item_ids) != 1 else "Left it late")
