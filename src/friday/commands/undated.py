"""Undated work placed by rules, learned from you (3 Nov: "the undated time slots thing should be completely
learned/dictated by rules"; asked: both a rule you write and one Friday learns, kept only with your yes). The planner
has no special case for work with no due date: a rule about "undated work" (scope `dated: false`) says where it goes.
This reads when you've done undated work (learn/undated.py) and asks in the Inbox, beside commands/conflicts.py's
questions, whether to keep that as a rule; a yes adds it as the Rules page would, in words you can change there."""

from friday.commands.conflicts import Clash, Option
from friday.commands.registry import Ctx
from friday.commands.rules import added
from friday.core.db import rows
from friday.core.time import format_utc, parse_utc, to_local
from friday.learn.undated import Habit, clock_said, habit, sentence

WINDOW_DAYS = 56  # sittings this recent are read
SOURCES = ("timer", "review", "retro")  # work you recorded, not what a plan assumed


def sittings(ctx: Ctx) -> list[tuple]:
    """Your recorded sittings on work with no due date, in local time."""
    found = rows(
        ctx.conn,
        "SELECT p.start_utc, p.end_utc FROM progress p JOIN items i ON i.id = p.item_id AND i.user_id = p.user_id "
        f"WHERE p.user_id = ? AND p.source IN ({', '.join('?' * len(SOURCES))}) AND p.start_utc IS NOT NULL "
        "AND p.end_utc IS NOT NULL AND p.start_utc >= ? AND i.due_utc IS NULL AND i.when_kind != 'fixed'",
        [ctx.user_id, *SOURCES, format_utc(ctx.now_utc - WINDOW_DAYS * 1440)],
    )
    return [
        (
            to_local(parse_utc(r["start_utc"]), ctx.tz).replace(tzinfo=None),
            to_local(parse_utc(r["end_utc"]), ctx.tz).replace(tzinfo=None),
        )
        for r in found
    ]


def has_undated_rule(ctx: Ctx) -> bool:
    """A rule about undated work already says where it goes: yours stands, nothing is asked."""
    return any((r.scope or {}).get("dated") is False and r.enabled for r in ctx.settings["rules"])


def offers(ctx: Ctx) -> list[Clash]:
    if has_undated_rule(ctx):
        return []
    found = habit(sittings(ctx))
    return [offer(found)] if found else []


def offer(h: Habit) -> Clash:
    window = f"{clock_said(h.start)} and {clock_said(h.end)}"
    said = sentence(h)
    pct = round(h.share * 100)
    return Clash(
        key="undated:window",
        title=f"You do work with no due date between {window}",
        detail=f"{pct}% of the {h.hours:.0f} h of undated work you recorded on {h.days} days in the last 8 weeks was "
        f"between {window}. Friday has no rule for where undated work goes; this would be one, on the Rules page "
        "to change or remove.",
        update="rule",
        about=said,
        options=(
            Option("always", f"Plan it only between {window}", "Outside it, undated work waits.", True),
            Option("prefer", f"Plan it mostly between {window}", "Outside it only when there's no room inside."),
            Option("no", "No rule", "Friday asks again if your habit changes."),
        ),
        apply=lambda ctx_, option, said=said: answer(ctx_, option, said),
    )


def answer(ctx: Ctx, option: str, said: str) -> str:
    if option == "no":
        return "No rule for undated work"
    return added(ctx, said, "Always" if option == "always" else "Prefer").message
