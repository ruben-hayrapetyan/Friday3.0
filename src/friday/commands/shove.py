"""Shove: clear time for yourself (DESIGN §15.4). Nothing is created if it would make something later, unless you
choose to: the answer is the must-do list, and `decision` says what to do about it."""

import dataclasses
import json
from datetime import date, timedelta

from friday.api.commands import Changed, MustDo, ShoveInput, ShoveOutput, UnshoveInput
from friday.commands.fields import insert_item, new_item
from friday.commands.registry import Ctx, command
from friday.commands.series import delete_item
from friday.core.dates import WEEKDAY_NAMES, next_weekday, parse_duration, parse_time, read_date
from friday.core.db import one
from friday.core.items import FieldError, Item
from friday.core.time import ampm, format_utc, local_midnight, to_local, to_utc
from friday.engine.executor import edf, subtract
from friday.planner.build import BuildInput, build_problem
from friday.planner.inputs import executor_input
from friday.planner.prepare import build_input
from friday.planner.service import what_if
from friday.planner.snapshot import Snapshot, read_snapshot
from friday.planner.store import current_plan

Range = tuple[int, int]


def parse_range(ctx: Ctx, text: str) -> list[Range]:
    """`30m`, `1h`, `12:00-13:30` (today, or `12:00-13:30 wed`), `rest`, `day fri` or `day fri sat`: one range per
    day."""
    words = text.lower().split()
    if not words:
        raise FieldError("range", "say how long, or which times or days")
    if words[0] == "rest":
        return [(ctx.now_utc, day_start_utc(ctx, ctx.today + timedelta(days=1)))]
    if words[0] == "day":
        return [whole_day(ctx, day) for day in days_named(ctx, words[1:])]
    if "-" in words[0]:
        first, _, last = words[0].partition("-")
        a, b = parse_time(first), parse_time(last)
        if a is None or b is None or b <= a:
            raise FieldError("range", f"{text!r} isn't a time range like 12:00-13:30")
        on = read_date(words, 1, ctx.today) if len(words) > 1 else None
        if len(words) > 1 and (on is None or on[1] != len(words) - 1):
            raise FieldError("range", f"{' '.join(words[1:])!r} isn't a day")
        midnight = local_midnight(on[0] if on else ctx.today)
        return [(to_utc(midnight + timedelta(minutes=a), ctx.tz), to_utc(midnight + timedelta(minutes=b), ctx.tz))]
    minutes = parse_duration(words[0])
    if minutes is None:
        raise FieldError("range", f"{text!r} isn't a length, a time range, `rest` or `day …`")
    return [(ctx.now_utc, ctx.now_utc + minutes)]


def day_start_utc(ctx: Ctx, day: date) -> int:
    return to_utc(local_midnight(day) + timedelta(minutes=ctx.day_start), ctx.tz)


def whole_day(ctx: Ctx, day: date) -> Range:
    start = max(ctx.now_utc, day_start_utc(ctx, day))  # today's starts now
    return start, day_start_utc(ctx, day + timedelta(days=1))


def days_named(ctx: Ctx, words: list[str]) -> list[date]:
    out, i = [], 0
    while i < len(words):
        found = read_date(words, i, ctx.today)
        if found is None:
            raise FieldError("range", f"{words[i]!r} isn't a day")
        out.append(found[0])
        i += found[1]
    return out or [next_weekday(ctx.today, WEEKDAY_NAMES["mon"])]


def shove_item(ctx: Ctx, span: Range, fake_id: int | None = None) -> Item:
    item = new_item(
        ctx,
        {
            "title": "Shoved",
            "preset": "Event",
            "when": "fixed",
            "event_kind": "shove",
            "start_utc": format_utc(span[0]),
            "end_utc": format_utc(span[1]),
        },
    )
    return dataclasses.replace(item, id=fake_id) if fake_id is not None else item


def nothing_late_now(ctx: Ctx) -> bool:
    plan = current_plan(ctx.conn, ctx.user_id)
    return plan is None or json.loads(plan["stage_values"])["deadlines"] == 0


def must_dos(ctx: Ctx, snapshot: Snapshot, inp: BuildInput, spans: list[Range]) -> list[MustDo]:
    """Items that would get later with the range cleared, and the hours each had planned in it."""
    fakes = [shove_item(ctx, span, -(n + 1)) for n, span in enumerate(spans)]
    extra = what_if(inp, lambda i: dataclasses.replace(i, items=[*i.items, *fakes]), with_fallback=True)
    titles = {i.id: i.title for i in snapshot.items}
    out = []
    for item_id, hours in sorted(extra.items()):
        planned = (
            sum(
                max(0, min(b.end_utc, hi) - max(b.start_utc, lo))
                for b in snapshot.plan_blocks
                if b.item_id == item_id
                for lo, hi in spans
            )
            / 60
        )
        out.append(
            MustDo(
                item_id=item_id,
                title=titles.get(item_id, ""),
                extra_late_hours=hours,
                planned_hours_in_range=round(planned, 2),
            )
        )
    return out


def executor_says_fine(inp: BuildInput, spans: list[Range]) -> bool:
    deadlines = executor_input(inp, build_problem(inp))
    return edf(deadlines.jobs, subtract(deadlines.free, spans)).feasible


@command("shove", affects_plan=True)
def shove(ctx: Ctx, inp: ShoveInput) -> ShoveOutput:
    """Clear time: `30m`, `12:00-13:30`, `rest`, `day fri`. Nothing is made later without your say."""
    spans = parse_range(ctx, inp.range)
    if inp.decision == "cancel":
        return ShoveOutput(message="Nothing changed")
    snapshot = read_snapshot(ctx.conn, ctx.now_utc, ctx.user_id)
    planning = build_input(snapshot)
    late = [] if inp.decision == "shove_anyway" else must_dos_if_any(ctx, snapshot, planning, spans)
    if late and inp.decision == "ask":
        names = ", ".join(f"{m.title} (+{m.extra_late_hours:g} h)" for m in late)
        return ShoveOutput(must_do=late, message=f"Clearing that would make these later: {names}")
    if late and inp.decision == "keep_must_dos":
        spans = keep_must_dos(ctx, snapshot, late, spans)
    created = [insert_item(ctx, shove_item(ctx, span)) for span in spans if span[1] > span[0]]
    cleared = "; ".join(spoken(ctx, a, b) for a, b in spans)
    return ShoveOutput(created=created, must_do=late, message=f"Cleared {cleared}")


def spoken(ctx: Ctx, start: int, end: int) -> str:
    """A cleared stretch as you'd say it: "today 4–5pm", "Mon Oct 26 4–5pm"."""
    a, b = to_local(start, ctx.tz), to_local(end, ctx.tz)
    day = "today" if a.date() == ctx.today else a.strftime("%a %b ") + str(a.day)
    first = ampm(a)
    if (a.hour < 12) == (b.hour < 12):
        first = first.removesuffix("am").removesuffix("pm")  # "4–5pm", not "4pm–5pm"
    return f"{day} {first}–{ampm(b)}"


def must_dos_if_any(ctx: Ctx, snapshot: Snapshot, planning: BuildInput, spans: list[Range]) -> list[MustDo]:
    if nothing_late_now(ctx) and executor_says_fine(planning, spans):
        return []
    return must_dos(ctx, snapshot, planning, spans)


def keep_must_dos(ctx: Ctx, snapshot: Snapshot, late: list[MustDo], spans: list[Range]) -> list[Range]:
    """Lock the must-do items' planned blocks inside the range; return the gaps left to shove."""
    keep = {m.item_id for m in late}
    kept: list[Range] = []
    for block in snapshot.plan_blocks:
        if block.item_id not in keep:
            continue
        for lo, hi in spans:
            a, b = max(block.start_utc, lo), min(block.end_utc, hi)
            if a < b:
                ctx.db.insert(
                    "pins",
                    {
                        "item_id": block.item_id,
                        "start_utc": format_utc(a),
                        "end_utc": format_utc(b),
                        "kind": "locked",
                        "created_utc": ctx.now_text,
                    },
                )
                kept.append((a, b))
    return subtract(spans, kept)


@command("unshove", affects_plan=True)
def unshove(ctx: Ctx, inp: UnshoveInput) -> Changed:
    """Remove the most recent shove, or a given one."""
    found = one(
        ctx.conn,
        "SELECT id FROM items WHERE user_id = ? AND event_kind = 'shove' AND status = 'todo' "
        "AND (? IS NULL OR id = ?) ORDER BY id DESC LIMIT 1",
        [ctx.user_id, inp.id, inp.id],
    )
    if found is None:
        raise FieldError("id", "no shove to remove")
    delete_item(ctx, found["id"])
    return Changed(message=f"Removed shove T{found['id']}")
