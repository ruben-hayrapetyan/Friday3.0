"""What the calendar draws besides blocks (DESIGN §18.4): day headers, sleep, the time axis and due markers."""

from datetime import date, timedelta

from friday.api.commands import AreaOut, CalendarInput
from friday.api.types import Empty
from friday.api.views import CalendarDay, CalendarOut, DueMarker
from friday.commands.registry import Ctx, query
from friday.core.db import rows
from friday.core.items import FieldError
from friday.core.pace import dials_on, pace_label
from friday.core.settings import minutes_of
from friday.core.time import format_local, format_utc, local_midnight, to_local, to_utc
from friday.planner.build import cap_hours_on, sleep_on
from friday.planner.snapshot import day_overrides, pace_periods


@query("calendar")
def calendar(ctx: Ctx, inp: CalendarInput) -> CalendarOut:
    """Day headers, sleep, the time axis (to the latest core sleep) and due markers for a run of days."""
    if ctx.settings["sleep"] is None:
        raise FieldError("sleep", "not set yet; run `fridayd init`")
    first = date.fromisoformat(inp.start) if inp.start else ctx.today
    dates = [first + timedelta(days=n) for n in range(inp.days)]
    overrides = day_overrides(ctx.conn, ctx.user_id)
    periods = list(pace_periods(ctx.conn, ctx.user_id))
    paces, default = ctx.settings["paces"], ctx.settings["pace"].default
    days, wakes, bedtimes = [], [], []
    for day in dates:
        evening, morning = sleep_on(ctx.settings, overrides, day), sleep_on(ctx.settings, overrides, day + timedelta(1))
        bedtime = bedtime_min(ctx, evening.bedtime)
        wakes.append(minutes_of(evening.wake))  # this morning's, by the same weekday rule
        bedtimes.append(bedtime + evening.margin_min)  # the margin can hold work, so it is drawn
        label = pace_label(dials_on(day, periods, paces, default), paces)
        days.append(
            CalendarDay(
                date=day.isoformat(),
                cap_hours=cap_hours_on(ctx.settings, overrides, day),
                pace=None if label == default else label,
                bedtime=at(day, bedtime),
                core=at(day, bedtime + evening.margin_min),
                wake=at(day + timedelta(1), minutes_of(morning.wake)),
            )
        )
    start, end = min(wakes), max(bedtimes)
    return CalendarOut(
        now=format_local(to_local(ctx.now_utc, ctx.tz)),
        today=ctx.today.isoformat(),
        axis_start_min=start,
        axis_end_min=min(end, start + 1440),
        days=days,
        dues=dues(ctx, dates[0], dates[-1] + timedelta(1), windows=False),
    )


def bedtime_min(ctx: Ctx, bedtime: str) -> int:
    minutes = minutes_of(bedtime)
    return minutes + 1440 if minutes < ctx.day_start else minutes  # before the day starts means after midnight


def at(day: date, minutes: int) -> str:
    return format_local(local_midnight(day) + timedelta(minutes=minutes))


def dues(ctx: Ctx, first: date, last: date, hard_only: bool = False, windows: bool = True) -> list[DueMarker]:
    """Due markers; `windows=False` leaves out where a soft repeat's window ends (laundry's week isn't a deadline)."""
    lo, hi = (format_utc(to_utc(local_midnight(d), ctx.tz)) for d in (first, last))
    found = rows(
        ctx.conn,
        "SELECT id, title, due_utc FROM items WHERE user_id = ? AND status = 'todo' AND due_utc >= ? AND due_utc < ? "
        + ("AND firmness = 'hard' " if hard_only else "")
        + ("" if windows else "AND (series_id IS NULL OR firmness = 'hard') ")
        + "ORDER BY due_utc",
        [ctx.user_id, lo, hi],
    )
    return [DueMarker(item_id=r["id"], title=r["title"], due=ctx.local(r["due_utc"]) or "") for r in found]


@query("areas")
def areas(ctx: Ctx, inp: Empty) -> list[AreaOut]:
    """Every area with its colour."""
    found = rows(ctx.conn, "SELECT * FROM areas WHERE user_id = ? ORDER BY name", [ctx.user_id])
    return [AreaOut(id=r["id"], name=r["name"], color=r["color"], archived=bool(r["archived"])) for r in found]
