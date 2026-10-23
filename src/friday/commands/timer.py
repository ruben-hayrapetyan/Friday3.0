"""The timer and progress rows, shared by the progress and item commands. The timer keeps seconds, so the bar can
tick; everything else in Friday is whole minutes. It is an overlay on the plan, never a change to it (§8 rule 2)."""

import time
from datetime import UTC, datetime
from typing import Any

from friday.api.commands import TimerOut
from friday.commands.fields import require_item
from friday.commands.registry import Ctx
from friday.core.db import one
from friday.core.time import EPOCH, format_utc, parse_utc


def write_progress(
    ctx: Ctx,
    item_id: int,
    minutes: int,
    source: str,
    start: int | None = None,
    end: int | None = None,
    key: str | None = None,
) -> None:
    ctx.db.insert(
        "progress",
        {
            "item_id": item_id,
            "start_utc": format_utc(start) if start is not None else None,
            "end_utc": format_utc(end) if end is not None else None,
            "minutes": max(0, minutes),
            "source": source,
            "block_key": key,
            "created_utc": ctx.now_text,
        },
    )


def running(ctx: Ctx) -> dict[str, Any] | None:
    return one(ctx.conn, "SELECT * FROM timer WHERE user_id = ?", [ctx.user_id])


def on_the_wall_clock(ctx: Ctx) -> bool:
    """Whether the command's clock is the real one (a test's or the demo's has no seconds)."""
    return ctx.now_utc == int(time.time() // 60)


def started_text(ctx: Ctx) -> str:
    """Now, to the second when it can be: a timer that ticked only in whole minutes looked dead for a minute."""
    if on_the_wall_clock(ctx):
        return datetime.fromtimestamp(time.time(), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return format_utc(ctx.now_utc)


def elapsed_seconds(ctx: Ctx, timer: dict[str, Any]) -> int:
    start_s = (datetime.fromisoformat(timer["start_utc"]).replace(tzinfo=None) - EPOCH).total_seconds()
    now_s = time.time() if on_the_wall_clock(ctx) else ctx.now_utc * 60
    return max(0, int(now_s - start_s))


def timer_out(ctx: Ctx, timer: dict[str, Any], message: str = "") -> TimerOut:
    seconds = elapsed_seconds(ctx, timer)
    return TimerOut(
        item_id=timer["item_id"],
        started=ctx.local(timer["start_utc"]),
        minutes=seconds // 60,
        elapsed_s=seconds,
        message=message,
    )


def stop_timer(ctx: Ctx) -> TimerOut:
    """Write the running session as `timer` progress (to the nearest minute; under half a minute, nothing) and
    clear the timer."""
    timer = running(ctx)
    if timer is None:
        return TimerOut(item_id=None, started=None, message="No timer running")
    seconds = elapsed_seconds(ctx, timer)
    minutes = round(seconds / 60)
    start = parse_utc(timer["start_utc"])
    if minutes:
        write_progress(ctx, timer["item_id"], minutes, "timer", start, start + minutes)
    ctx.db.delete("timer", {"user_id": ctx.user_id})
    title = require_item(ctx, timer["item_id"]).title
    said = f"{minutes} min" if minutes else f"{seconds} s, too short to count"
    return TimerOut(
        item_id=timer["item_id"],
        started=ctx.local(timer["start_utc"]),
        minutes=minutes,
        elapsed_s=seconds,
        message=f"Stopped {title} after {said}",
    )
