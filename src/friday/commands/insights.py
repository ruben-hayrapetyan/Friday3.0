"""Insights (v22): how long things really take by kind, when you get things done, and the totals, over a few weeks."""

import statistics
from collections import defaultdict
from datetime import timedelta

from friday.api.commands import InsightsInput
from friday.api.views import InsightsOut, KindAccuracy
from friday.commands.registry import Ctx, query
from friday.core.db import rows
from friday.core.time import format_utc, parse_utc, to_local

FIRST_HOUR, LAST_HOUR = 8, 23  # the heatmap's columns
DAYS = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")


# Meals and habits are part of the day, not work: counted, dinner time came out as your best hours (M16).
NOT_WORK = "('Routine', 'Habit')"


@query("insights")
def insights(ctx: Ctx, inp: InsightsInput) -> InsightsOut:
    """The last few weeks: things finished, hours worked, estimates against actual time by kind, and when you work."""
    since = format_utc(ctx.now_utc - inp.weeks * 7 * 1440)
    done = rows(
        ctx.conn,
        "SELECT * FROM completions WHERE user_id = ? AND completed_utc >= ? "
        f"AND coalesce(preset, '') NOT IN {NOT_WORK}",
        [ctx.user_id, since],
    )
    ratios: dict[str, list[float]] = defaultdict(list)
    for r in done:
        estimate = r["your_estimate_units"] or r["friday_estimate_units"]
        if estimate:
            ratios[r["preset"] or "To-do"].append(r["actual_minutes"] / (estimate * 15))
    all_ratios = [x for xs in ratios.values() for x in xs]
    heat = heatmap(ctx, since)
    return InsightsOut(
        weeks=inp.weeks,
        done=len(done),
        hours=round(sum(r["actual_minutes"] for r in done) / 60, 1),
        estimate_ratio=round(statistics.median(all_ratios), 2) if all_ratios else None,
        by_kind=[accuracy(kind, xs) for kind, xs in sorted(ratios.items(), key=lambda kv: -len(kv[1]))],
        heat=heat,
        best_hours=best_hours(heat),
    )


def accuracy(kind: str, ratios: list[float]) -> KindAccuracy:
    xs = sorted(ratios)
    quartile = (lambda q: xs[min(len(xs) - 1, int(q * len(xs)))]) if len(xs) > 1 else (lambda q: xs[0])
    return KindAccuracy(
        kind=kind,
        n=len(xs),
        median=round(statistics.median(xs), 2),
        low=round(quartile(0.25), 2),
        high=round(quartile(0.75), 2),
    )


def heatmap(ctx: Ctx, since: str) -> list[list[int]]:
    """Minutes of recorded work in each weekday's hours, in local time."""
    grid = [[0] * (LAST_HOUR - FIRST_HOUR + 1) for _ in range(7)]
    for r in rows(
        ctx.conn,
        "SELECT p.start_utc, p.end_utc FROM progress p JOIN items i ON i.id = p.item_id WHERE p.user_id = ? "
        f"AND p.start_utc >= ? AND p.end_utc IS NOT NULL AND coalesce(i.preset, '') NOT IN {NOT_WORK}",
        [ctx.user_id, since],
    ):
        at, end = parse_utc(r["start_utc"]), parse_utc(r["end_utc"])
        while at < end:
            local = to_local(at, ctx.tz)
            step = min(end - at, 60 - local.minute)
            if FIRST_HOUR <= local.hour <= LAST_HOUR:
                grid[local.weekday()][local.hour - FIRST_HOUR] += step
            at += step
    return grid


def best_hours(grid: list[list[int]]) -> str | None:
    """The busiest weekday and its best two hours, as a sentence."""
    total = sum(map(sum, grid))
    if total < 120:
        return None
    day = max(range(7), key=lambda d: sum(grid[d]))
    hour = max(range(len(grid[day]) - 1), key=lambda h: grid[day][h] + grid[day][h + 1]) + FIRST_HOUR
    start = timedelta(hours=hour)
    return (
        f"You get the most done on {DAYS[day]}, {start.seconds // 3600:02d}:00 to {start.seconds // 3600 + 2:02d}:00."
    )
