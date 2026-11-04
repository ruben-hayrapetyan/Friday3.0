"""Work your plans showed late that you finished on time anyway, and what Friday learns from it (2 Nov: "tell me what
friday learns from the fact that it consistently proposes schedules that have things late but i don't do anything
late"). The reading is learn/beat_plan.py's; this gathers what it reads and asks in the Inbox (beside
commands/conflicts.py's questions) before changing anything:

- later nights: your margin past bedtime grows on the evenings you worked into, so Friday plans late work there
  before showing it late (the margin stays the time it plans in last);
- a kind you finish faster is planned at the share of its length you take (planner/cushion.py `shortened`).

An answer stands until what it's about changes (a longer reach, a smaller share)."""

import json
from datetime import date, timedelta
from typing import Any

from friday.api.types import Empty
from friday.api.views import BeatFinish, BeatPlanOut
from friday.commands.conflicts import Clash, Option, put
from friday.commands.decisions import spoken
from friday.commands.registry import Ctx, query
from friday.commands.settings import write_setting
from friday.core.db import one, rows
from friday.core.rule_text import days_spoken
from friday.core.time import UNIT_MIN, WEEKDAYS, format_utc, parse_utc, to_local
from friday.learn.beat_plan import Event, Finish, Night, Summary, read, summarize
from friday.planner.build import night_times
from friday.planner.cushion import LEARNED_SOURCES, SHARES
from friday.planner.planned_late import planned_late
from friday.planner.store import kv_get

WINDOW_DAYS = 56  # finishes this recent are read
LONG_EVENT_MIN = 12 * 60  # a whole-day event isn't time you worked through
SAID = {
    "faster": "in less time than planned",
    "nights": "by working later at night",
    "mornings": "by starting before you're up",
    "events": "by working through events",
    "daytime": "in time planned for other things",
    "untold": "without a record of when",
}


def gathered(ctx: Ctx) -> tuple[list[tuple[Finish, dict[str, Any]]], int]:
    """Recent finishes your plans showed late and finished by their due, each with its row; and how many were
    finished after their due."""
    late = planned_late(ctx.conn, ctx.user_id)
    if not late:
        return [], 0
    found = rows(
        ctx.conn,
        f"SELECT * FROM items WHERE user_id = ? AND status = 'done' AND due_utc IS NOT NULL AND completed_utc >= ? "
        f"AND id IN ({', '.join('?' * len(late))}) ORDER BY completed_utc",
        [ctx.user_id, format_utc(ctx.now_utc - WINDOW_DAYS * 1440), *late],
    )
    on_time = [r for r in found if r["completed_utc"] <= r["due_utc"]]
    return [(finish_of(ctx, r), r | {"late_hours": late[r["id"]]}) for r in on_time], len(found) - len(on_time)


def finish_of(ctx: Ctx, r: dict[str, Any]) -> Finish:
    timed = one(
        ctx.conn,
        f"SELECT actual_minutes FROM completions WHERE user_id = ? AND item_id = ? "
        f"AND actual_source IN ({', '.join('?' * len(LEARNED_SOURCES))}) ORDER BY id DESC LIMIT 1",
        [ctx.user_id, r["id"], *LEARNED_SOURCES],
    )
    worked = rows(
        ctx.conn,
        "SELECT start_utc, end_utc FROM progress WHERE user_id = ? AND item_id = ? AND start_utc IS NOT NULL "
        "AND end_utc IS NOT NULL",
        [ctx.user_id, r["id"]],
    )
    fixed = r["amount"] == "fixed" and r["duration_units"]
    return Finish(
        item_id=r["id"],
        title=r["title"],
        kind=r["preset"],
        planned_min=r["duration_units"] * UNIT_MIN if fixed else None,
        actual_min=timed["actual_minutes"] if timed else None,
        worked=tuple((parse_utc(w["start_utc"]), parse_utc(w["end_utc"])) for w in worked),
        scalable=bool(fixed) and r["duration_source"] in ("you", "preset"),
    )


def nights_around(ctx: Ctx, finish: Finish) -> list[Night]:
    """The nights your settings kept free around each recorded sitting (bedtime's margin to waking)."""
    if ctx.settings["sleep"] is None or not finish.worked:
        return []
    days: set[date] = set()
    for lo, hi in finish.worked:
        first, last = to_local(lo, ctx.tz).date() - timedelta(days=1), to_local(hi, ctx.tz).date()
        days |= {first + timedelta(days=n) for n in range((last - first).days + 1)}
    overrides = {
        date.fromisoformat(r["date"]): {k: r[k] for k in ("bedtime", "wake", "margin_min")}
        for r in rows(ctx.conn, "SELECT * FROM day_overrides WHERE user_id = ?", [ctx.user_id])
    }
    out = []
    for day in sorted(days):
        bedtime, wake, margin = night_times(ctx.settings, overrides, day, ctx.tz, ctx.day_start)
        out.append(Night(WEEKDAYS[day.weekday()], bedtime + margin, wake))
    return out


def events_around(ctx: Ctx, finish: Finish) -> list[Event]:
    """Events counted as busy that overlap any recorded sitting."""
    if not finish.worked:
        return []
    lo, hi = min(w[0] for w in finish.worked), max(w[1] for w in finish.worked)
    found = rows(
        ctx.conn,
        "SELECT title, start_utc, end_utc FROM items WHERE user_id = ? AND when_kind = 'fixed' AND blocks_time = 1 "
        "AND status IN ('todo', 'done') AND id != ? AND start_utc < ? AND end_utc > ?",
        [ctx.user_id, finish.item_id, format_utc(hi), format_utc(lo)],
    )
    spans = [(r["title"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"])) for r in found]
    return [Event(t, s, e) for t, s, e in spans if e - s < LONG_EVENT_MIN]


def summary(ctx: Ctx) -> tuple[Summary, list[dict[str, Any]], int]:
    found, finished_late = gathered(ctx)
    hows = [read(f, nights_around(ctx, f), events_around(ctx, f)) for f, _ in found]
    sleep = ctx.settings["sleep"] or {}
    margins = {d: s.margin_min for d, s in sleep.items()}
    return summarize(hows, margins), [r for _, r in found], finished_late


@query("beat_plan")
def beat_plan(ctx: Ctx, inp: Empty) -> BeatPlanOut:
    """Work your plans showed late that you finished on time: how, and what Friday would change."""
    found, found_rows, finished_late = summary(ctx)
    finishes = [
        BeatFinish(
            item_id=h.finish.item_id,
            title=h.finish.title,
            due=ctx.local(r["due_utc"]) or "",
            finished=ctx.local(r["completed_utc"]) or "",
            late_hours=r["late_hours"],
            ways=list(h.ways),
            speed=round(h.speed, 2) if h.speed is not None else None,
            events=list(h.events),
        )
        for h, r in zip(found.hows, found_rows, strict=True)
    ]
    return BeatPlanOut(
        on_time=len(finishes),
        late=finished_late,
        finishes=finishes,
        counts=dict(found.counts),
        said=said(found, finished_late),
        asking=[c.title for c in offers_from(ctx, found)],
    )


def said(found: Summary, finished_late: int) -> list[str]:
    """What Friday learned, in words."""
    n = len(found.hows)
    if not n:
        return []
    shown = n + finished_late
    out = [f"You finished {n} of the {shown} things your plans showed late on time"]
    for way, count in sorted(found.counts.items(), key=lambda kv: -kv[1]):
        out.append(f"{count} {SAID[way]}")
    return out


def offers(ctx: Ctx) -> list[Clash]:
    """The Inbox's questions from what you finished on time: later nights, shorter kinds."""
    found, _, _ = summary(ctx)
    return offers_from(ctx, found)


def offers_from(ctx: Ctx, found: Summary) -> list[Clash]:
    out = []
    if found.nights is not None:
        out.append(nights_offer(found))
    shares = kv_get(ctx.conn, SHARES, {}, ctx.user_id) or {}
    out += [speed_offer(s.kind, s.share, s.cases) for s in found.speeds if shares.get(s.kind) != s.share]
    return out


def nights_offer(found: Summary) -> Clash:
    nights = found.nights
    assert nights is not None
    evenings = tuple(nights.margins)
    extra = spoken(nights.extra_min / 60)
    return Clash(
        key="beat:nights",
        title="You finish work Friday showed late by working later at night",
        detail=f"{nights.cases} things your plans showed late you finished on time, working up to about {extra} past "
        f"where Friday stops planning at night ({days_spoken(evenings)}). Friday can plan into that time before "
        "showing work late; it stays the time it plans in last.",
        update="rule",
        about=json.dumps(dict(nights.margins), sort_keys=True),
        options=(
            Option(
                "later", f"Plan up to {extra} later on those nights", "Only when work would be late otherwise.", True
            ),  # fmt: skip
            Option("keep", "Keep my nights as they are", "Friday keeps showing that work late."),
        ),
        apply=lambda ctx_, option, margins=dict(nights.margins): answer_nights(ctx_, option, margins),
    )


def answer_nights(ctx: Ctx, option: str, margins: dict[str, int]) -> str:
    if option == "keep":
        return "Kept your nights"
    sleep = {d: s.model_dump() for d, s in ctx.settings["sleep"].items()}
    for day, margin in margins.items():
        sleep[day]["margin_min"] = margin
    write_setting(ctx, "sleep", sleep)
    return f"Later nights on {days_spoken(tuple(margins))} when work would be late"


def speed_offer(kind: str, share: float, cases: int) -> Clash:
    pct = round(share * 100)
    return Clash(
        key=f"beat:speed:{kind}",
        title=f"{kind} takes you about {pct}% of the time Friday plans for it",
        detail=f"{cases} times your plans showed {kind} late, you finished it on time in about {pct}% of its length. "
        "Friday can plan it at that share of the length you give it or the kind's default; its own estimates "
        "already learn from your times.",
        update="rule",
        about=str(share),
        options=(
            Option(
                "shorten",
                f"Plan {kind} at {pct}% of its length",
                "Less time set aside; finish early and it's simply done.",
                True,
            ),  # fmt: skip
            Option("keep", "Keep planning full lengths", "Friday keeps showing that work late."),
        ),
        apply=lambda ctx_, option: answer_speed(ctx_, option, kind, share),
    )


def answer_speed(ctx: Ctx, option: str, kind: str, share: float) -> str:
    if option == "keep":
        return f"Planning {kind} at full length"
    put(ctx, SHARES, (kv_get(ctx.conn, SHARES, {}, ctx.user_id) or {}) | {kind: share})
    return f"Planning {kind} at {round(share * 100)}% of its length"
