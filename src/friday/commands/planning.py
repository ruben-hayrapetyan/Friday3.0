"""Planning on demand: replan, and resolve a plan waiting on a lock conflict (DESIGN §15.3)."""

import json

from friday.api.commands import Empty, ReplanOutput, ResolveInput
from friday.commands.registry import Ctx, command
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.planner.service import replan as solve_and_save


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
    status = saved["status"] if saved else "current"
    if status == "waiting":
        conflicts = json.loads(saved["report"]).get("conflicts", []) if saved else []
        named = "; ".join(f"locked {c['title']} makes work {c['extra_late_hours']:g} h late" for c in conflicts)
        return ReplanOutput(plan_id=plan_id, status=status, message=f"Waiting: {named}. Use `resolve`.")
    return ReplanOutput(plan_id=plan_id, status=status, message=f"Plan P{plan_id}")


@command("resolve", affects_plan=True)
def resolve(ctx: Ctx, inp: ResolveInput) -> ReplanOutput:
    """Settle a waiting plan: listed locks become preferred (and Friday replans), or none accepts it as it is."""
    waiting = one(
        ctx.conn, "SELECT id FROM plans WHERE user_id = ? AND status = 'waiting' ORDER BY id DESC", [ctx.user_id]
    )
    if waiting is None:
        raise FieldError("unlock_pin_ids", "no plan is waiting")
    if inp.unlock_pin_ids:
        locks = {
            r["id"] for r in rows(ctx.conn, "SELECT id FROM pins WHERE user_id = ? AND kind = 'locked'", [ctx.user_id])
        }
        for pin_id in inp.unlock_pin_ids:
            if pin_id not in locks:
                raise FieldError("unlock_pin_ids", f"no locked pin {pin_id}")
            ctx.db.update("pins", {"id": pin_id}, {"kind": "preferred"})
        return ReplanOutput(plan_id=None, status="replanning", message="Unlocked; replanning")
    # Plans aren't undo data: they are derived, and the next replan writes a new one anyway.
    ctx.conn.execute("UPDATE plans SET status = 'replaced' WHERE user_id = ? AND status = 'current'", [ctx.user_id])
    ctx.conn.execute("UPDATE plans SET status = 'current' WHERE id = ?", [waiting["id"]])
    return ReplanOutput(plan_id=waiting["id"], status="current", message="Accepted the waiting plan, lateness included")
