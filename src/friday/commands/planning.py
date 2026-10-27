"""Planning on demand: replan, and let locks that make work late move (DESIGN §15.3; keeping them is
`decisions.lock_keep`)."""

import json

from friday.api.commands import Empty, ReplanOutput, ResolveInput
from friday.commands.registry import Ctx, command
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.planner.service import replan as solve_and_save
from friday.planner.store import kv_get


@command("replan", logged=False)
def replan(ctx: Ctx, inp: Empty) -> ReplanOutput:
    """Solve now."""
    reason = f"replan by {ctx.actor}"
    if ctx.solver is not None:
        plan_id = ctx.solver(reason)
    else:
        plan_id = solve_and_save(ctx.conn, ctx.now_utc, ctx.user_id, warm=True, reason=reason)
    if plan_id is None:
        return ReplanOutput(plan_id=None, status="skipped", message="A newer plan was already saved")
    saved = one(ctx.conn, "SELECT status, report FROM plans WHERE id = ?", [plan_id])
    conflicts = json.loads(saved["report"]).get("conflicts", []) if saved else []
    named = "; ".join(f"locked {c['title']} makes work {c['extra_late_hours']:g} h late" for c in conflicts)
    asked = f" (to decide in the Inbox: {named})" if named else ""
    return ReplanOutput(
        plan_id=plan_id, status=saved["status"] if saved else "current", message=f"Plan P{plan_id}{asked}"
    )


@command("resolve", affects_plan=True)
def resolve(ctx: Ctx, inp: ResolveInput) -> ReplanOutput:
    """Let locks that make work late move: a lock becomes a pin, so it still prefers its place, and an event's hold
    lets work in (Hold it brings it back); Friday replans."""
    if not inp.unlock_pin_ids:
        raise FieldError("unlock_pin_ids", "name the locks to let move")
    locks = {
        r["id"] for r in rows(ctx.conn, "SELECT id FROM pins WHERE user_id = ? AND kind = 'locked'", [ctx.user_id])
    }
    loose = set(kv_get(ctx.conn, "event_holds_loose", [], ctx.user_id) or [])
    for pin_id in inp.unlock_pin_ids:
        if pin_id < 0:  # an event's time held for a task (planner/holds.py): the event asks for it instead
            loose.add(-pin_id)
            continue
        if pin_id not in locks:
            raise FieldError("unlock_pin_ids", f"no locked pin {pin_id}")
        ctx.db.update("pins", {"id": pin_id}, {"kind": "preferred"})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "event_holds_loose"}, {"value": json.dumps(sorted(loose))})
    return ReplanOutput(plan_id=None, status="replanning", message="Unlocked; replanning")
