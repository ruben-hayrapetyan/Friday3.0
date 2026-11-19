"""Breaks (core/vacations.py): add, change and delete one; a break day's list of things, and ticking one off."""

import json
from datetime import date, timedelta
from typing import Any

from friday.api.commands import (
    BreakSuggestionInput,
    Changed,
    DoneInput,
    ItemRef,
    PauseIn,
    VacationAddInput,
    VacationDayInput,
    VacationEditInput,
    VacationOut,
    VacationResult,
    VacationsOut,
    VacationTickInput,
)
from friday.api.types import Empty, Model
from friday.api.views import (
    BreakChoicesOut,
    CalendarChoice,
    Decision,
    SeriesChoice,
    VacationDay,
    VacationDayOut,
    VacationThing,
)
from friday.commands.registry import Ctx, command, query
from friday.core import vacations as breaks
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.rows import item_from_row
from friday.core.settings import minutes_of
from friday.core.time import format_utc, parse_utc, planning_day_start_utc
from friday.planner.store import area_names, current_plan, kv_get

DEFAULT_NAME = "Break"


def said(day: date) -> str:
    return f"{day:%a}, {day:%b} {day.day}"


def vacation_out(v: breaks.Vacation) -> VacationOut:
    return VacationOut(
        id=v.id, name=v.name, start=v.start, end=v.end, days=v.days, mode=v.mode,  # type: ignore[arg-type]
        per_day=v.per_day, pause=PauseIn.model_validate(v.pause.model_dump()), plan_meals=v.plan_meals,
        keep_sleep=v.keep_sleep, own=sorted(v.own),
    )  # fmt: skip


def all_of(ctx: Ctx) -> tuple[breaks.Vacation, ...]:
    return breaks.load(ctx.conn, ctx.user_id, ctx.settings["breaks"])


def one_of(ctx: Ctx, vacation_id: int) -> breaks.Vacation:
    found = next((v for v in all_of(ctx) if v.id == vacation_id), None)
    if found is None:
        raise FieldError("id", "no such break")
    return found


def check_days(ctx: Ctx, start: date, end: date, other_than: int | None = None) -> None:
    if end < start:
        raise FieldError("end", "a break ends on or after the day it starts")
    for v in all_of(ctx):
        if v.id != other_than and v.first <= end and start <= v.last:
            raise FieldError("start", f"those days are already on {v.name} ({said(v.first)} – {said(v.last)})")


def own_values(inp: Model) -> dict[str, Any]:
    """What a break sets for itself, as stored (None: follows your default)."""
    out: dict[str, Any] = {}
    if getattr(inp, "per_day", None) is not None:
        out["per_day"] = inp.per_day  # type: ignore[attr-defined]
    if getattr(inp, "pause", None) is not None:
        out["pause"] = json.dumps(inp.pause.model_dump())  # type: ignore[attr-defined]
    for key in ("plan_meals", "keep_sleep"):
        if getattr(inp, key, None) is not None:
            out[key] = int(getattr(inp, key))
    return out


@command("vacation_add", affects_plan=True)
def vacation_add(ctx: Ctx, inp: VacationAddInput) -> VacationResult:
    """Add a break: its days, Off or Light, and what it pauses (your defaults, unless it says otherwise)."""
    check_days(ctx, inp.start, inp.end)
    name = (inp.name or "").strip() or DEFAULT_NAME
    made = ctx.db.insert(
        "vacations",
        {"name": name, "start_date": inp.start.isoformat(), "end_date": inp.end.isoformat(), "mode": inp.mode,
         "created_utc": ctx.now_text, **own_values(inp)},
    )  # fmt: skip
    v = one_of(ctx, made)
    return VacationResult(vacation=vacation_out(v), message=f"{v.name} added, {said(v.first)} – {said(v.last)}")


@command("vacation_edit", affects_plan=True)
def vacation_edit(ctx: Ctx, inp: VacationEditInput) -> VacationResult:
    """Change a break; what's named in `defaults` follows your defaults again."""
    was = one_of(ctx, inp.id)
    start, end = inp.start or was.first, inp.end or was.last
    check_days(ctx, start, end, other_than=inp.id)
    changes: dict[str, Any] = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    if inp.name is not None:
        changes["name"] = inp.name.strip() or DEFAULT_NAME
    if inp.mode is not None:
        changes["mode"] = inp.mode
    changes |= own_values(inp) | dict.fromkeys(inp.defaults)
    ctx.db.update("vacations", {"id": inp.id}, changes)
    v = one_of(ctx, inp.id)
    return VacationResult(vacation=vacation_out(v), message=f"{v.name} changed")


@command("vacation_delete", affects_plan=True)
def vacation_delete(ctx: Ctx, inp: ItemRef) -> Changed:
    """Delete a break: its days are planned as usual again. What you ticked stays done."""
    v = one_of(ctx, inp.id)
    ctx.db.delete("vacations", {"id": inp.id})
    return Changed(message=f"{v.name} deleted")


@query("vacations")
def vacations(ctx: Ctx, inp: Empty) -> VacationsOut:
    """Your breaks, first first."""
    return VacationsOut(vacations=[vacation_out(v) for v in all_of(ctx)])


def day_bounds(ctx: Ctx, day: date) -> tuple[int, int]:
    day_start = minutes_of(ctx.settings["time"].day_start)
    return (planning_day_start_utc(day, ctx.tz, day_start),
            planning_day_start_utc(day + timedelta(days=1), ctx.tz, day_start))  # fmt: skip


def vacation_day_of(v: breaks.Vacation, day: date, ctx: Ctx | None = None) -> VacationDay:
    """The break a day is on; with `ctx`, how many things its list has and how many are ticked off."""
    counted = {}
    if ctx is not None:
        things = vacation_things(ctx, day)
        counted = {"things": len(things), "ticked": sum(t.ticked for t in things)}
    return VacationDay(
        id=v.id, name=v.name, mode=v.mode, day_n=v.day_n(day), days=v.days, per_day=v.per_day,  # type: ignore[arg-type]
        keep_sleep=v.keep_sleep, **counted,
    )  # fmt: skip  # type: ignore[arg-type]


def planned_minutes(ctx: Ctx, day: date) -> dict[int, tuple[int, int]]:
    """The current plan's work on a day, by item: its minutes, and its first start (the list's order)."""
    saved = current_plan(ctx.conn, ctx.user_id)
    if saved is None:
        return {}
    lo, hi = day_bounds(ctx, day)
    out: dict[int, tuple[int, int]] = {}
    for r in rows(
        ctx.conn,
        "SELECT item_id, start_utc, end_utc FROM blocks WHERE plan_id = ? AND end_utc > ? AND start_utc < ?",
        [saved["id"], format_utc(lo), format_utc(hi)],
    ):
        start, end = max(lo, parse_utc(r["start_utc"])), min(hi, parse_utc(r["end_utc"]))
        minutes, first = out.get(r["item_id"], (0, start))
        out[r["item_id"]] = (minutes + end - start, min(first, start))
    return out


def timed_minutes(ctx: Ctx, day: date) -> dict[int, int]:
    lo, hi = day_bounds(ctx, day)
    out: dict[int, int] = {}
    for r in rows(
        ctx.conn,
        "SELECT p.item_id, p.minutes FROM progress p JOIN items i ON i.id = p.item_id WHERE i.user_id = ? "
        "AND p.source = 'timer' AND p.start_utc >= ? AND p.start_utc < ?",
        [ctx.user_id, format_utc(lo), format_utc(hi)],
    ):
        out[r["item_id"]] = out.get(r["item_id"], 0) + r["minutes"]
    return out


@query("vacation_day")
def vacation_day(ctx: Ctx, inp: VacationDayInput) -> VacationDayOut:
    """A break day's list: what to get done that day to stay on track, by name, in the order planned, with what you
    ticked off it. A day not on a break has none."""
    v = breaks.on(inp.date, all_of(ctx))
    if v is None:
        return VacationDayOut(date=inp.date.isoformat(), vacation=None, items=[])
    things = vacation_things(ctx, inp.date)
    day = vacation_day_of(v, inp.date).model_copy(
        update={"things": len(things), "ticked": sum(t.ticked for t in things)}
    )
    return VacationDayOut(date=inp.date.isoformat(), vacation=day, items=things)


def vacation_things(ctx: Ctx, day: date) -> list[VacationThing]:
    """A break day's list, in the order planned, ticked ones kept. A meal is never on it unless the break plans meals:
    one planned before the break was added (a break added mid-day) stays in the plan as begun, not as a thing to do."""
    v = breaks.on(day, all_of(ctx))
    inp = VacationDayInput(date=day)
    planned = planned_minutes(ctx, inp.date)
    ticks = {r["item_id"]: r for r in rows(ctx.conn, "SELECT * FROM vacation_ticks WHERE user_id = ? AND date = ?",
                                           [ctx.user_id, inp.date.isoformat()])}  # fmt: skip
    timed = timed_minutes(ctx, inp.date)
    ids = sorted(set(planned) | set(ticks), key=lambda i: (i not in planned, planned.get(i, (0, 0))[1], i))
    found = {r["id"]: r for r in rows(ctx.conn, f"SELECT * FROM items WHERE id IN ({', '.join('?' * len(ids))})", ids)}
    things = []
    areas = area_names(ctx.conn, ctx.user_id)
    for item_id in ids:
        row = found.get(item_id)
        if row is None or row["status"] == "dropped" or (item_id not in ticks and row["status"] != "todo"):
            continue
        item = item_from_row(row)
        if breaks.is_meal(item) and not (v and v.plan_meals) and item_id not in ticks:
            continue
        things.append(
            VacationThing(item_id=item_id, title=item.title, area=areas.get(item.area_id or 0), preset=item.preset,
                          ticked=item_id in ticks, done=row["status"] == "done", timed_min=timed.get(item_id, 0))
        )  # fmt: skip
    return things


@command("vacation_tick", affects_plan=True)
def vacation_tick(ctx: Ctx, inp: VacationTickInput) -> Changed:
    """Tick a thing off a break day's list, or untick it. Ticked, a thing whose work is all on that day is done; a
    bigger one counts that day's share as done (less what you timed of it that day) and stays open."""
    from friday.commands.items import done, reopen  # items imports a great deal: here, not at the top

    v = breaks.on(inp.date, all_of(ctx))
    if v is None:
        raise FieldError("date", f"{said(inp.date)} isn't on a break")
    day = inp.date.isoformat()
    tick = one(ctx.conn, "SELECT * FROM vacation_ticks WHERE user_id = ? AND date = ? AND item_id = ?",
               [ctx.user_id, day, inp.item_id])  # fmt: skip
    row = one(ctx.conn, "SELECT * FROM items WHERE id = ? AND user_id = ?", [inp.item_id, ctx.user_id])
    if row is None:
        raise FieldError("item_id", "no such task")
    title = row["title"]
    if not inp.ticked:
        if tick is None:
            return Changed(message=f"{title} wasn't ticked")
        if tick["finished"] and row["status"] == "done":
            reopen(ctx, ItemRef(id=inp.item_id))
        if tick["progress_id"] is not None:
            ctx.db.delete("progress", {"id": tick["progress_id"]})
        ctx.db.delete("vacation_ticks", {"id": tick["id"]})
        return Changed(message=f"{title} back on the list")
    if tick is not None:
        return Changed(message=f"{title} is ticked already")
    if row["status"] != "todo":
        raise FieldError("item_id", f"{title} isn't open")
    share, _ = planned_minutes(ctx, inp.date).get(inp.item_id, (0, 0))
    _, hi = day_bounds(ctx, inp.date)
    saved = current_plan(ctx.conn, ctx.user_id)
    later = saved is not None and one(
        ctx.conn, "SELECT 1 FROM blocks WHERE plan_id = ? AND item_id = ? AND start_utc >= ?",
        [saved["id"], inp.item_id, format_utc(hi)],
    )  # fmt: skip
    progress_id = None
    finished = not later
    if finished:
        done(ctx, DoneInput(id=inp.item_id))
    else:
        logged = max(0, share - timed_minutes(ctx, inp.date).get(inp.item_id, 0))
        if logged:
            progress_id = ctx.db.insert(
                "progress",
                {"item_id": inp.item_id, "minutes": logged, "source": "review", "created_utc": ctx.now_text},
            )
    ctx.db.insert(
        "vacation_ticks",
        {"date": day, "item_id": inp.item_id, "finished": int(finished), "progress_id": progress_id,
         "created_utc": ctx.now_text},
    )  # fmt: skip
    return Changed(message=f"{title} done" if finished else f"{title}: today's part done")


def paused_events(ctx: Ctx, fixed: list[Any]) -> list[int]:
    """Of these fixed items (rows), the ones a break pauses."""
    found = all_of(ctx)
    if not found or not fixed:
        return []
    from friday.planner.snapshot import break_calendars

    items = tuple(item_from_row(r) for r in fixed)
    _, paused = breaks.on_break(items, found, ctx.settings, break_calendars(ctx.conn, ctx.user_id))
    return sorted(paused)


@query("break_choices")
def break_choices(ctx: Ctx, inp: Empty) -> BreakChoicesOut:
    """What a break can pause: every calendar, tag and repeating event (events made here are on "Friday").

    For a chooser that stays usable with twenty calendars (18 Nov)."""
    from friday.core.recurrence import describe
    from friday.planner.hidden import CALENDAR_KINDS
    from friday.planner.snapshot import break_calendars

    calendars = break_calendars(ctx.conn, ctx.user_id)
    series = []
    for r in rows(
        ctx.conn,
        "SELECT s.id, s.rrule, s.template, (SELECT min(i.id) FROM items i WHERE i.series_id = s.id "
        "AND i.when_kind = 'fixed') AS one FROM series s WHERE s.user_id = ? AND s.active = 1",
        [ctx.user_id],
    ):
        if r["one"] is None:
            continue  # a repeating task, not an event
        title = str(json.loads(r["template"]).get("title") or "Event")
        calendar = calendars.get(r["one"]) or breaks.FRIDAY_CALENDAR
        series.append(SeriesChoice(id=r["id"], title=title, calendar=calendar, every=describe(r["rrule"])))
    series.sort(key=lambda s: (s.calendar.lower(), s.title.lower()))
    names = [
        r["name"]
        for r in rows(
            ctx.conn,
            f"SELECT DISTINCT name FROM sources WHERE user_id = ? AND kind IN ({', '.join('?' * len(CALENDAR_KINDS))})",
            [ctx.user_id, *CALENDAR_KINDS],
        )
    ]
    counts: dict[str, int] = {}
    for s in series:
        counts[s.calendar] = counts.get(s.calendar, 0) + 1
    every = sorted(set(names) | set(counts), key=str.lower)
    shown = "SELECT name FROM areas WHERE user_id = ? AND archived = 0 ORDER BY name"
    tags = [r["name"] for r in rows(ctx.conn, shown, [ctx.user_id])]
    return BreakChoicesOut(
        calendars=[CalendarChoice(name=n, repeats=counts.get(n, 0)) for n in every], tags=tags, series=series
    )


def suggested(ctx: Ctx) -> list[breaks.Suggested]:
    if ctx.settings["time"].timezone is None:
        return []  # before Setup there's no today to suggest from (18 Nov: `status` failed, "server isn't running")
    declined = kv_get(ctx.conn, breaks.DECLINED, [], ctx.user_id) or []
    return breaks.suggest(ctx.conn, ctx.user_id, ctx.settings, ctx.today, declined)


def break_decisions(ctx: Ctx) -> list[Decision]:
    """Each suggested break, as a decision in the Inbox: yours to take or not; nothing waits on it."""
    return [
        Decision(key=s.key, kind="break", title=f"{s.name}, {said(date.fromisoformat(s.start))} – "
                 f"{said(date.fromisoformat(s.end))}: a break?",
                 detail=f"{s.why}. As a break, those days pause your repeating events and list a few things to do "
                 "instead of times.", start=s.start, end=s.end, name=s.name)
        for s in suggested(ctx)
    ]  # fmt: skip


@command("break_suggestion", affects_plan=True)
def break_suggestion(ctx: Ctx, inp: BreakSuggestionInput) -> Changed:
    """Take a suggested break (it's added, with your defaults) or say it isn't one (not asked again)."""
    found = next((s for s in suggested(ctx) if s.key == inp.key), None)
    if found is None:
        raise FieldError("key", "that break isn't suggested any more")
    if inp.take:
        made = vacation_add(ctx, VacationAddInput(name=found.name[:80], start=found.start, end=found.end))
        return Changed(message=made.message)
    declined = kv_get(ctx.conn, breaks.DECLINED, [], ctx.user_id) or []
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": breaks.DECLINED}, {"value": json.dumps([*declined, inp.key])})
    return Changed(message="Not a break: Friday won't ask about it again")
