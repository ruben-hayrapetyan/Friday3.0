"""Your plan as a calendar on this Mac (C96, your choice: the plan as an iCloud calendar; C113). Friday's Mac app
keeps a "Friday" calendar in your iCloud account equal to the plan, from now to the end of the horizon, so your iPhone
(and anything else that shows iCloud calendars) shows it, as Google's "Friday" calendar does for Google (DESIGN
§22.3). It asks for the plan every minute and changes the calendar only when the plan has changed; switched off, it
removes the calendar it made. Friday never reads that calendar back (the Mac app leaves it out of `mac_sync`), so the
plan never becomes busy time."""

from friday.api.commands import MacPlanBlock, MacPlanOut
from friday.api.types import Empty
from friday.commands.google import blocks
from friday.commands.registry import Ctx, query
from friday.planner.store import current_plan


@query("mac_plan")
def mac_plan(ctx: Ctx, inp: Empty) -> MacPlanOut:
    """Whether the Mac app should keep the "Friday" calendar, and the plan's blocks for it."""
    if not ctx.settings["mac_plan"]:
        return MacPlanOut(wanted=False)
    saved = current_plan(ctx.conn, ctx.user_id)
    if saved is None:
        return MacPlanOut(wanted=True)
    until = ctx.now_utc + ctx.settings["time"].horizon_days * 24 * 60
    found = blocks(ctx.conn, saved["id"], ctx.now_utc, until, None)
    return MacPlanOut(
        wanted=True,
        plan=saved["id"],
        blocks=[MacPlanBlock(key=b.key, title=b.title, start=b.start, end=b.end, tentative=b.tentative) for b in found],
    )
