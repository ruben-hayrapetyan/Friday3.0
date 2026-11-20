"""Insights (v22): how long things really take by kind, when you get things done, and the totals, over a few weeks."""

import statistics
from collections import defaultdict

from friday.api.commands import InsightsInput
from friday.api.views import InsightsOut, KindAccuracy
from friday.commands.registry import Ctx, query
from friday.core.db import rows
from friday.core.settings import minutes_of
from friday.core.time import clock_time, format_utc, parse_utc, to_local
from friday.core.vacations import on_a_break
from friday.estimate.durations import LEARNED_SOURCES

FIRST_HOUR, LAST_HOUR = 8, 23  # the heatmap's columns at least: more when you work earlier, or past midnight
DAYS = ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays")


# Meals and habits are part of the day, not work: counted, dinner time came out as your best hours (M16).
NOT_WORK = "('Routine', 'Habit')"


@query("insights")
def insights(ctx: Ctx, inp: InsightsInput) -> InsightsOut:
    """The last few weeks: things finished, hours worked, estimates against actual time by kind, and when you work."""
    since = format_utc(ctx.now_utc - inp.weeks * 7 * 1440)
    on_break = on_a_break(ctx.conn, ctx.user_id, ctx.settings)  # break days don't count (core/vacations.py)
    done = [
        r
        for r in rows(
            ctx.conn,
            "SELECT * FROM completions WHERE user_id = ? AND completed_utc >= ? "
            f"AND coalesce(preset, '') NOT IN {NOT_WORK}",
            [ctx.user_id, since],
        )
        if not on_break(r["completed_utc"])
    ]
    ratios: dict[str, list[float]] = defaultdict(list)
    timed = [r for r in done if r["actual_source"] in LEARNED_SOURCES]  # not the plan's lengths assumed (audit, 8 Nov)
    for r in timed:
        estimate = r["your_estimate_units"] or r["friday_estimate_units"]
        if estimate:
            ratios[r["preset"] or "To-do"].append(r["actual_minutes"] / (estimate * 15))
    all_ratios = [x for xs in ratios.values() for x in xs]
    heat, heat_hours = heatmap(ctx, since)
    return InsightsOut(
        weeks=inp.weeks,
        done=len(done),
        hours=round(sum(r["actual_minutes"] for r in timed) / 60, 1),
        estimate_ratio=round(statistics.median(all_ratios), 2) if all_ratios else None,
        by_kind=[accuracy(kind, xs) for kind, xs in sorted(ratios.items(), key=lambda kv: -len(kv[1]))],
        heat=heat,
        heat_hours=heat_hours,
        best_hours=best_hours(heat, heat_hours),
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


def heatmap(ctx: Ctx, since: str) -> tuple[list[list[int]], list[int]]:
    """Minutes of recorded work in each weekday's hours, in local time, added up over the weeks shown. Each real hour
    holds at most 60 (16 Nov: three timers running at once made one hour 3h, "Mon 11pm, 357 min"), and a session counts
    the minutes it recorded, spread over its span (a review's "30 minutes" between 10:45 and 11:45 is 30, not 60).

    Every hour counts (20 Nov, a user's notes: "if your work typically starts before 8 or ends after midnight I feel
    like it should show up"; before, only 8am to 11pm did): an hour before your day starts (4am, say) is the night
    before's, on its row, after 11pm. The columns run from 8am to 11pm, wider where you worked: the hours with them."""
    day_start = minutes_of(ctx.settings["time"].day_start) // 60
    order = [(day_start + i) % 24 for i in range(24)]  # your day's hours, its start first
    hours: dict[tuple[int, int, int], float] = defaultdict(float)  # (local date ordinal, weekday, hour) -> minutes
    on_break = on_a_break(ctx.conn, ctx.user_id, ctx.settings)
    for r in rows(
        ctx.conn,
        "SELECT p.start_utc, p.end_utc, p.minutes FROM progress p JOIN items i ON i.id = p.item_id WHERE p.user_id = ? "
        f"AND p.start_utc >= ? AND p.end_utc IS NOT NULL AND coalesce(i.preset, '') NOT IN {NOT_WORK}",
        [ctx.user_id, since],
    ):
        if on_break(r["start_utc"]):
            continue
        at, end = parse_utc(r["start_utc"]), parse_utc(r["end_utc"])
        share = min(1.0, r["minutes"] / (end - at)) if r["minutes"] is not None and end > at else 1.0
        while at < end:
            local = to_local(at, ctx.tz)
            step = min(end - at, 60 - local.minute)
            weekday = (local.weekday() - 1) % 7 if local.hour < day_start else local.weekday()  # the night before's
            hours[(local.toordinal(), weekday, local.hour)] += step * share
            at += step
    full = [[0] * 24 for _ in range(7)]
    for (_, weekday, hour), minutes in hours.items():
        full[weekday][order.index(hour)] += round(min(60.0, minutes))
    worked = [i for i in range(24) if any(full[d][i] for d in range(7))]
    first = min([order.index(FIRST_HOUR), *worked[:1]])
    last = max([order.index(LAST_HOUR), *worked[-1:]])
    return [row[first : last + 1] for row in full], order[first : last + 1]


def best_hours(grid: list[list[int]], hours: list[int]) -> str | None:
    """The busiest weekday and its best two hours, as a sentence; `hours`, each column's hour."""
    total = sum(map(sum, grid))
    if total < 120:
        return None
    day = max(range(7), key=lambda d: sum(grid[d]))
    hour = hours[max(range(len(grid[day]) - 1), key=lambda h: grid[day][h] + grid[day][h + 1])]
    start, end = clock_time(f"{hour:02d}:00"), clock_time(f"{(hour + 2) % 24:02d}:00")
    return f"You get the most done on {DAYS[day]}, {start} to {end}."
