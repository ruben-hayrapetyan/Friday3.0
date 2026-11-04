"""The timer and progress rows, shared by the progress and item commands. The timer keeps seconds, so the bar can
tick; everything else in Friday is whole minutes. It is an overlay on the plan, never a change to it (§8 rule 2).

Several things can be timed at once (2 Nov: "working on two things at once even if friday didn't originally plan
to"): laundry running while you read. The one started last is "the timer", the one the plan holds at now and the
Now bar shows first; the others run alongside it, and each gets the whole time it ran."""

import time
from datetime import UTC, datetime
from typing import Any

from friday.api.commands import TimerOut
from friday.commands.fields import require_item
from friday.commands.registry import Ctx
from friday.core.db import one, rows
from friday.core.items import FieldError
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


MAX_AT_ONCE = 3  # things timed at once: laundry and the dishwasher while you read


def running(ctx: Ctx, item_id: int | None = None) -> dict[str, Any] | None:
    """The timer on `item_id`; without one, the one started last."""
    if item_id is not None:
        return one(ctx.conn, "SELECT * FROM timer WHERE user_id = ? AND item_id = ?", [ctx.user_id, item_id])
    return one(ctx.conn, "SELECT * FROM timer WHERE user_id = ? ORDER BY start_utc DESC, rowid DESC LIMIT 1",
               [ctx.user_id])  # fmt: skip


def all_running(ctx: Ctx) -> list[dict[str, Any]]:
    """Every timer, the first started first."""
    return rows(ctx.conn, "SELECT * FROM timer WHERE user_id = ? ORDER BY start_utc, rowid", [ctx.user_id])


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
        title=require_item(ctx, timer["item_id"]).title,
        started=ctx.local(timer["start_utc"]),
        minutes=seconds // 60,
        elapsed_s=seconds,
        message=message,
    )


def stop_timer(ctx: Ctx, at: int | None = None, item_id: int | None = None) -> TimerOut:
    """Write a running session as `timer` progress (to the nearest minute; under half a minute, nothing) and clear
    its timer: `item_id`'s, else the one started last; the others go on. `at`: when you really stopped, earlier than
    now (28 Oct: a timer left running counted, and taught Friday, hours you didn't work)."""
    timer = running(ctx, item_id)
    if timer is None:
        said = "No timer running" if item_id is None else f"T{item_id} isn't being timed"
        return TimerOut(item_id=None, started=None, message=said)
    seconds = elapsed_seconds(ctx, timer)
    start = parse_utc(timer["start_utc"])
    if at is not None:
        if at <= start:
            raise FieldError("at", f"must be after you started, at {ctx.local(timer['start_utc'])[11:16]}")
        if at > ctx.now_utc:
            raise FieldError("at", "must not be later than now")
        seconds = min(seconds, (at - start) * 60)
    minutes = round(seconds / 60)
    if minutes:
        write_progress(ctx, timer["item_id"], minutes, "timer", start, start + minutes)
    ctx.db.delete("timer", {"user_id": ctx.user_id, "item_id": timer["item_id"]})
    title = require_item(ctx, timer["item_id"]).title
    said = f"{minutes} min" if minutes else f"{seconds} s, too short to count"
    return TimerOut(
        item_id=timer["item_id"],
        title=title,
        started=ctx.local(timer["start_utc"]),
        minutes=minutes,
        elapsed_s=seconds,
        message=f"Stopped {title} after {said}",
    )
