"""Tracking your meals (Sleep & meals; off until you turn it on, like sleep): "Eating now" and "Done eating", one tap
each, a meal logged after the fact or skipped, a tap at the wrong time put right, and what Friday makes of them
(`learn/meals.py`): each meal's usual time, length and skips, and the length you take offered for its routine.

A meal goes with that day's routine of its name (Lunch, Dinner): while you eat, the plan holds the routine at now (as
it holds a timed task), so no work is planned over your meal; done eating ticks the routine off, skipping skips it,
and taking a meal back opens it again.

What's learned is offered, never changed without a yes: a routine's length when you take longer or shorter, its window
when you eat well outside it or off its middle, and the meal itself: planned when you have it most days and none is,
no longer planned when you mostly skip it. A rule can say yes ahead for some meals ("Let Friday decide breakfast",
`meal_learned`): each night `decide` applies what's offered for them, as the job.
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from friday.api.commands import (
    Changed,
    MealEditInput,
    MealEndInput,
    MealLengthInput,
    MealLogInput,
    MealPlanInput,
    MealRef,
    MealSkipInput,
    MealStartInput,
    SeriesRef,
)
from friday.api.types import Empty
from friday.api.views import MealChangeOut, MealDayOut, MealLearnedOut, MealOut, MealPlanOut, MealsOut, MealTimeOut
from friday.commands.items import edit_from, set_status
from friday.commands.registry import Ctx, command, query, run
from friday.commands.series import create_series, edit_series_from, load_series, series_stop
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.settings import minutes_of
from friday.core.time import (
    UNIT_MIN,
    ampm,
    format_local,
    format_utc,
    parse_local,
    parse_utc,
    planning_date,
    to_local,
    to_zoned,
)
from friday.learn.meals import Learned, Meal, learn, length_changes, meal_name, nths
from friday.planner.store import kv_get, kv_set, load_item, load_settings

SHIFT_OFF_BY = 45  # minutes a usual meal's middle must be off its window's middle (or outside it) to offer moving it
MEAL_ROOM = 45  # a meal Friday starts planning gets a window this far either side of when you have it
PLAN_BELOW, STOP_FROM = 0.4, 0.6  # skipped on fewer days: plan it; on more: stop. In between it stays as it is
SHOWN_DAYS = 14
LEARN_DAYS = 56  # the last eight weeks teach what's usual
LONGEST_MIN = 4 * 60
FORGOT_MIN = 2 * 60  # Done eating this long after starting was a tap forgotten, not a two-hour meal
PLANNED = ("breakfast", "lunch", "dinner")
# When a meal is yours to eat where no routine of its name says (a breakfast you don't plan): local minutes.
WINDOWS = {"breakfast": (6 * 60, 10 * 60 + 30), "lunch": (11 * 60, 14 * 60 + 30), "dinner": (17 * 60, 21 * 60)}


def tracking(ctx: Ctx) -> None:
    if not ctx.settings["meal_tracking"].on:
        raise FieldError("kind", "Meal tracking is off: turn it on in Insights → Meals")


def moment_of(ctx: Ctx, local: str | None, field: str = "at") -> int:
    moment = parse_utc(ctx.utc(local, field)) if local else ctx.now_utc
    if moment > ctx.now_utc + 5:
        raise FieldError(field, "that's later than now")
    return moment


def day_of(ctx: Ctx, moment: int) -> date:
    return planning_date(moment, ctx.tz, ctx.day_start)


def said(ctx: Ctx, moment: int) -> str:
    return ampm(to_local(moment, ctx.tz))


def routine_of(ctx: Ctx, kind: str, day: date) -> dict | None:
    """That day's routine named for the meal (Lunch on Tuesday), if you plan one."""
    return one(
        ctx.conn,
        "SELECT * FROM items WHERE user_id = ? AND preset = 'Routine' AND series_id IS NOT NULL "
        "AND occurrence_date = ? AND lower(title) LIKE ? ORDER BY id LIMIT 1",
        [ctx.user_id, day.isoformat(), f"%{kind}%"],
    )


def open_routine(ctx: Ctx, kind: str, day: date) -> int | None:
    routine = routine_of(ctx, kind, day)
    return int(routine["id"]) if routine and routine["status"] == "todo" else None


def tick_off(ctx: Ctx, item_id: int | None, status: str, at: int) -> int | None:
    """The meal's routine done (eaten) or skipped, so the plan stops holding time for it."""
    routine = one(ctx.conn, "SELECT status FROM items WHERE id = ?", [item_id]) if item_id else None
    if item_id is None or routine is None or routine["status"] != "todo":
        return None
    set_status(ctx, item_id, status, format_utc(at) if status == "done" else None)
    return item_id


def eating(ctx: Ctx) -> dict | None:
    return one(
        ctx.conn,
        "SELECT * FROM meals WHERE user_id = ? AND skipped = 0 AND start_utc IS NOT NULL AND end_utc IS NULL "
        "ORDER BY id DESC LIMIT 1",
        [ctx.user_id],
    )


def in_window(ctx: Ctx, kind: str, moment: int) -> bool:
    """Whether it's that meal's time: its routine's window that day, or (with no routine) the usual hours."""
    routine = routine_of(ctx, kind, day_of(ctx, moment))
    if routine is not None:
        if not (routine["release_utc"] and routine["due_utc"]):
            return False
        return parse_utc(routine["release_utc"]) <= moment <= parse_utc(routine["due_utc"])
    local = to_local(moment, ctx.tz)
    lo, hi = WINDOWS[kind]
    return lo <= local.hour * 60 + local.minute < hi


def kind_at(ctx: Ctx, moment: int) -> str:
    """The meal it's time for (lunch between your lunch routine's 11:30 and 2pm), else a snack."""
    return next((kind for kind in PLANNED if in_window(ctx, kind, moment)), "snack")


def finish(ctx: Ctx, meal: dict, end: int) -> int:
    start = parse_utc(meal["start_utc"])
    if end <= start:
        raise FieldError("at", "that's before you started")
    end = min(end, start + LONGEST_MIN)
    routine = meal["item_id"] or open_routine(ctx, meal["kind"], date.fromisoformat(meal["date"]))
    ticked = tick_off(ctx, routine, "done", end)
    ctx.db.update("meals", {"id": meal["id"]}, {"end_utc": format_utc(end), "item_id": ticked or meal["item_id"]})
    return end - start


@command("meal_start", affects_plan=True)
def meal_start(ctx: Ctx, inp: MealStartInput) -> Changed:
    """Eating now (or since the time you give); a meal you were still eating finishes as this one starts."""
    tracking(ctx)
    moment = moment_of(ctx, inp.at)
    before = eating(ctx)
    if before is not None:
        if parse_utc(before["start_utc"]) >= moment:
            raise FieldError("at", f"you're eating {before['kind']} since then")
        finish(ctx, before, moment)
    kind = inp.kind or kind_at(ctx, moment)
    day = day_of(ctx, moment)
    routine = open_routine(ctx, kind, day)
    nth = eaten_before(ctx, kind, day, moment) + 1
    ctx.db.insert(
        "meals",
        {"kind": kind, "date": day.isoformat(), "start_utc": format_utc(moment), "item_id": routine,
         "created_utc": ctx.now_text},
    )  # fmt: skip
    return Changed(message=f"Eating {'your ' if nth > 1 else ''}{meal_name(kind, nth)} since {said(ctx, moment)}")


@command("meal_end", affects_plan=True)
def meal_end(ctx: Ctx, inp: MealEndInput) -> Changed:
    """Done eating (or done at the time you give)."""
    tracking(ctx)
    meal = eating(ctx)
    if meal is None:
        raise FieldError("at", "you aren't eating")
    end = moment_of(ctx, inp.at)
    start = parse_utc(meal["start_utc"])
    if inp.at is None and end - start > FORGOT_MIN:
        # Done eating tapped hours later: you finished long ago, so it's the meal's usual length, not four hours.
        usual = usual_length(ctx, meal["kind"])
        finish(ctx, meal, start + usual)
        return Changed(
            message=f"{meal['kind'].capitalize()}: counted as your usual {usual} min (Done eating came "
            f"{(end - start) // 60} h {(end - start) % 60} min after you started); change it in Insights → Meals"
        )
    minutes = finish(ctx, meal, end)
    return Changed(message=f"{meal['kind'].capitalize()}: {minutes} min")


def usual_length(ctx: Ctx, kind: str) -> int:
    """How long this meal usually takes you: what's learned, else its routine's planned length, else half an hour."""
    found = usual_of(learned(ctx), kind)
    if found is not None and found.usual_min:
        return int(found.usual_min)
    planned = planned_routines(ctx).get(kind)
    return int(planned[1]) if planned else 30


@command("meal_log", affects_plan=True)
def meal_log(ctx: Ctx, inp: MealLogInput) -> Changed:
    """A meal you didn't tap, from when you started to when you finished."""
    tracking(ctx)
    start, end = moment_of(ctx, inp.start, "start"), moment_of(ctx, inp.end, "end")
    if not start < end <= start + LONGEST_MIN:
        raise FieldError("end", "a meal ends after it starts, within four hours")
    day = day_of(ctx, start)
    nth = eaten_before(ctx, inp.kind, day, start) + 1
    ticked = tick_off(ctx, open_routine(ctx, inp.kind, day), "done", end)
    ctx.db.insert(
        "meals",
        {"kind": inp.kind, "date": day.isoformat(), "start_utc": format_utc(start), "end_utc": format_utc(end),
         "item_id": ticked, "created_utc": ctx.now_text},
    )  # fmt: skip
    return Changed(message=f"Logged {meal_name(inp.kind, nth)}, {said(ctx, start)} to {said(ctx, end)}")


def eaten_before(ctx: Ctx, kind: str, day: date, moment: int) -> int:
    """How many of this meal you'd eaten that day before `moment`: one before makes this a second dinner."""
    found = one(
        ctx.conn,
        "SELECT count(*) AS n FROM meals WHERE user_id = ? AND kind = ? AND date = ? AND skipped = 0 "
        "AND start_utc IS NOT NULL AND start_utc < ?",
        [ctx.user_id, kind, day.isoformat(), format_utc(moment)],
    )
    return int(found["n"]) if found else 0


@command("meal_skip", affects_plan=True)
def meal_skip(ctx: Ctx, inp: MealSkipInput) -> Changed:
    """A meal you skipped (today, or the day you give); its routine is skipped too."""
    tracking(ctx)
    day = date.fromisoformat(inp.date) if inp.date else ctx.today
    if day > ctx.today:
        raise FieldError("date", "that day hasn't come yet")
    taken = "SELECT 1 FROM meals WHERE user_id = ? AND kind = ? AND date = ?"
    if one(ctx.conn, taken, [ctx.user_id, inp.kind, day.isoformat()]):
        raise FieldError("kind", f"{inp.kind} is already recorded that day")
    ticked = tick_off(ctx, open_routine(ctx, inp.kind, day), "skipped", ctx.now_utc)
    ctx.db.insert(
        "meals",
        {"kind": inp.kind, "date": day.isoformat(), "skipped": 1, "item_id": ticked, "created_utc": ctx.now_text},
    )
    return Changed(message=f"Skipped {inp.kind}")


def meal_row(ctx: Ctx, meal_id: int) -> dict:
    found = one(ctx.conn, "SELECT * FROM meals WHERE user_id = ? AND id = ?", [ctx.user_id, meal_id])
    if found is None:
        raise FieldError("id", f"no meal {meal_id}")
    return found


@command("meal_edit", affects_plan=True)
def meal_edit(ctx: Ctx, inp: MealEditInput) -> Changed:
    """A meal's start or end put right (a tap at the wrong time)."""
    meal = meal_row(ctx, inp.id)
    if meal["skipped"]:
        raise FieldError("id", "a skipped meal has no times")
    start = moment_of(ctx, inp.start, "start") if inp.start else parse_utc(meal["start_utc"])
    end = moment_of(ctx, inp.end, "end") if inp.end else (parse_utc(meal["end_utc"]) if meal["end_utc"] else None)
    if end is not None and not start < end <= start + LONGEST_MIN:
        raise FieldError("end", "a meal ends after it starts, within four hours")
    changes = {"start_utc": format_utc(start), "date": day_of(ctx, start).isoformat()}
    ctx.db.update("meals", {"id": inp.id}, changes | ({"end_utc": format_utc(end)} if end is not None else {}))
    until = f" to {said(ctx, end)}" if end is not None else ""
    return Changed(message=f"{meal['kind'].capitalize()} now {said(ctx, start)}{until}")


@command("meal_remove", affects_plan=True)
def meal_remove(ctx: Ctx, inp: MealRef) -> Changed:
    """A meal you didn't mean to record; the routine it ticked off is open again, unless another of that meal that
    day still says you had it or skipped it (27 Oct: removing a duplicate lunch reopened the day's Lunch, which then
    showed hours "over" though you'd logged it)."""
    meal = meal_row(ctx, inp.id)
    ctx.db.delete("meals", {"id": inp.id})
    found = routine_of(ctx, meal["kind"], date.fromisoformat(meal["date"]))
    if found is None:
        return Changed(message=f"Removed {meal['kind']}")
    others = rows(
        ctx.conn,
        "SELECT * FROM meals WHERE user_id = ? AND kind = ? AND date = ?",
        [ctx.user_id, meal["kind"], meal["date"]],
    )
    eaten = [m for m in others if not m["skipped"] and m["end_utc"]]
    want = "done" if eaten else "skipped" if any(m["skipped"] for m in others) else "todo"
    if found["status"] != want and found["status"] in ("todo", "done", "skipped"):
        set_status(ctx, found["id"], want, eaten[-1]["end_utc"] if want == "done" else None)
    for m in others:
        if m["item_id"] is None and want != "todo":
            ctx.db.update("meals", {"id": m["id"]}, {"item_id": found["id"]})
    return Changed(message=f"Removed {meal['kind']}")


def planned_routines(ctx: Ctx) -> dict[str, tuple]:
    """Each planned meal's next routine and its planned length in minutes."""
    out = {}
    for kind in PLANNED:
        row = one(
            ctx.conn,
            "SELECT id FROM items WHERE user_id = ? AND preset = 'Routine' AND series_id IS NOT NULL "
            "AND status = 'todo' AND occurrence_date >= ? AND lower(title) LIKE ? ORDER BY occurrence_date LIMIT 1",
            [ctx.user_id, ctx.today.isoformat(), f"%{kind}%"],
        )
        item = load_item(ctx.conn, row["id"], ctx.user_id) if row else None
        if item is not None:
            out[kind] = (item, (item.ideal_units or item.min_units or 1) * UNIT_MIN)
    return out


def recorded(ctx: Ctx, days: int) -> list[Meal]:
    since = (ctx.today - timedelta(days=days)).isoformat()
    found = rows(
        ctx.conn,
        "SELECT * FROM meals WHERE user_id = ? AND date >= ? ORDER BY date, start_utc, id",
        [ctx.user_id, since],
    )
    local = lambda t: to_zoned(parse_utc(t), ctx.tz) if t else None  # noqa: E731  (zoned: real lengths, 12 Nov)
    return [
        Meal(r["id"], r["kind"], date.fromisoformat(r["date"]), local(r["start_utc"]), local(r["end_utc"]),
             bool(r["skipped"]), r["item_id"])
        for r in found
    ]  # fmt: skip


def learned(ctx: Ctx) -> list[Learned]:
    return learn(recorded(ctx, LEARN_DAYS), ctx.settings["meal_tracking"].min_days)


@command("meal_use_length", affects_plan=True)
def meal_use_length(ctx: Ctx, inp: MealLengthInput) -> Changed:
    """Plan a meal's routine at the length you take, from today on (what Insights → Meals offers)."""
    found = planned_routines(ctx).get(inp.kind)
    if found is None:
        raise FieldError("kind", f"there's no {inp.kind} routine to change")
    item, planned = found
    usual = length_changes(learned(ctx), {inp.kind: planned}).get(inp.kind)
    if usual is None:
        raise FieldError("kind", f"Friday hasn't learned a different length for {inp.kind}")
    length = max(UNIT_MIN, round(usual / UNIT_MIN) * UNIT_MIN)  # plans are in quarter hours
    low, high = (item.min_units or 1) * UNIT_MIN, (item.max_units or 1) * UNIT_MIN
    given = {"ideal_min": length, "min_min": min(low, length), "max_min": max(high, length)}
    edit_from(ctx, item, ctx.today.isoformat(), given)
    return Changed(message=f"{inp.kind.capitalize()} is planned at {length} min from today (you take about {usual})")


def usual_of(found: list[Learned], kind: str) -> Learned | None:
    """What's learned of a meal, weekdays where there are enough of them, else weekends."""
    mine = [x for x in found if x.kind == kind]
    return next((x for x in mine if x.group == "weekdays"), None) or next(iter(mine), None)


def day_minutes(stored: str, ctx: Ctx, day_start: int) -> int:
    """A stored time as minutes from its planning day's midnight (1am is 25:00)."""
    local = to_local(parse_utc(stored), ctx.tz)
    minute = local.hour * 60 + local.minute
    return minute + 1440 if minute < day_start else minute


def hhmm(minutes: int) -> str:
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def time_changes(ctx: Ctx, found: list[Learned], planned: dict[str, tuple]) -> list[MealTimeOut]:
    """Routines whose window is well off when you eat: moved, the same width, to sit around your usual time."""
    out = []
    for kind, (item, minutes) in planned.items():
        usual = usual_of(found, kind)
        if usual is None or usual.usual_start is None or not item.release_utc or not item.due_utc:
            continue
        length = usual.usual_min or minutes
        start = int(usual.usual_start[:2]) * 60 + int(usual.usual_start[3:])
        start += 1440 if start < ctx.day_start else 0
        lo, hi = day_minutes(item.release_utc, ctx, ctx.day_start), day_minutes(item.due_utc, ctx, ctx.day_start)
        inside = lo <= start and start + length <= hi
        if inside and abs((start + length / 2) - (lo + hi) / 2) < SHIFT_OFF_BY:
            continue
        new_lo = round((start + length / 2 - (hi - lo) / 2) / UNIT_MIN) * UNIT_MIN
        out.append(MealTimeOut(kind=kind, usual_start=usual.usual_start, start=hhmm(lo), end=hhmm(hi),
                               new_start=hhmm(new_lo), new_end=hhmm(new_lo + hi - lo)))  # fmt: skip
    return out


def plan_offers(found: list[Learned], planned: dict[str, tuple]) -> list[MealPlanOut]:
    """Meals to plan (you have them most days and none is planned) or to stop planning (you mostly skip them)."""
    out = []
    for kind in PLANNED:
        usual = usual_of(found, kind)
        if usual is None or usual.skip_share is None:
            continue
        start = kind not in planned and usual.skip_share < PLAN_BELOW and usual.usual_start
        if start or (kind in planned and usual.skip_share >= STOP_FROM):
            out.append(MealPlanOut(kind=kind, plan=bool(start), usual_start=usual.usual_start,
                                   usual_min=usual.usual_min))  # fmt: skip
    return out


@command("meal_use_time", affects_plan=True)
def meal_use_time(ctx: Ctx, inp: MealLengthInput) -> Changed:
    """Plan a meal's routine around when you usually eat it, from today on (what Insights → Meals offers)."""
    planned = planned_routines(ctx)
    found = planned.get(inp.kind)
    offer = next((t for t in time_changes(ctx, learned(ctx), planned) if t.kind == inp.kind), None)
    if found is None or offer is None or found[0].series_id is None:
        raise FieldError("kind", f"Friday hasn't learned a different time for {inp.kind}")
    item = found[0]
    first = parse_local(load_series(ctx, item.series_id)["dtstart_local"])
    base = first.hour * 60 + first.minute
    lo = int(offer.new_start[:2]) * 60 + int(offer.new_start[3:])
    lo += 1440 if lo < ctx.day_start else 0
    width = day_minutes(item.due_utc, ctx, ctx.day_start) - day_minutes(item.release_utc, ctx, ctx.day_start)
    offsets = {"release_offset_min": lo - base, "due_offset_min": lo - base + width}
    edit_series_from(ctx, item.series_id, ctx.today.isoformat(), {}, offsets=offsets)
    return Changed(
        message=f"{inp.kind.capitalize()} is planned {ampm(offer.new_start)} to {ampm(offer.new_end)} from today"
    )


@command("meal_plan", affects_plan=True)
def meal_plan(ctx: Ctx, inp: MealPlanInput) -> Changed:
    """Plan a meal every day at the time and length you have it, or stop planning it (what Insights → Meals offers)."""
    kind, planned = inp.kind, planned_routines(ctx)
    if not inp.plan:
        if kind not in planned or planned[kind][0].series_id is None:
            raise FieldError("plan", f"there's no {kind} routine to stop")
        series_stop(ctx, SeriesRef(id=planned[kind][0].series_id))
        return Changed(message=f"{kind.capitalize()} is no longer planned")
    if kind in planned:
        raise FieldError("plan", f"{kind} is already planned")
    usual = usual_of(learned(ctx), kind)
    if usual is None or usual.usual_start is None:
        raise FieldError("plan", f"Friday hasn't learned when you have {kind} yet")
    length = max(UNIT_MIN, round((usual.usual_min or UNIT_MIN) / UNIT_MIN) * UNIT_MIN)
    start = int(usual.usual_start[:2]) * 60 + int(usual.usual_start[3:])
    start += 1440 if start < ctx.day_start else 0
    given = {"title": kind.capitalize(), "preset": "Routine", "min_min": length, "ideal_min": length,
             "max_min": length}  # fmt: skip
    repeat = {"every": "day", "release_offset_min": start - MEAL_ROOM - ctx.day_start,
              "due_offset_min": start + length + MEAL_ROOM - ctx.day_start}  # fmt: skip
    create_series(ctx, given, repeat)
    return Changed(message=f"{kind.capitalize()} is planned around {ampm(usual.usual_start)}, {length} min, every day")


def decided(settings: Mapping[str, Any]) -> list[str]:
    """The meals your rules leave to Friday ("Let Friday decide breakfast")."""
    named = {m for r in settings["rules"] if r.type == "meal_learned" and r.enabled for m in r.params.get("meals", [])}
    return [kind for kind in PLANNED if kind in named]


def decide(conn: sqlite3.Connection, now_utc: int, user_id: int = 1) -> list[str]:
    """What's learned of the meals Friday decides, applied as the job: planned or no longer, then moved to when you
    eat and planned at the length you take. Once a day, and again when the rule changes; returns what changed."""
    settings = load_settings(conn, user_id)
    kinds = decided(settings)
    if not kinds or not settings["meal_tracking"].on:
        return []
    day = planning_date(now_utc, settings["time"].timezone, minutes_of(settings["time"].day_start))
    key = {"date": day.isoformat(), "meals": kinds}
    if kv_get(conn, "meals_decided", None, user_id) == key:
        return []
    said = []
    do = lambda name, payload: said.append(  # noqa: E731
        run(conn, name, payload, now_utc=now_utc, actor="job", user_id=user_id, provisional=False).result["message"]
    )
    look = lambda: MealsOut(**run(conn, "meals", {}, now_utc=now_utc, user_id=user_id).result)  # noqa: E731
    for offered in look().plans:
        if offered.kind in kinds:
            do("meal_plan", {"kind": offered.kind, "plan": offered.plan})
    for moved in look().times:
        if moved.kind in kinds:
            do("meal_use_time", {"kind": moved.kind})
    for change in look().changes:
        if change.kind in kinds:
            do("meal_use_length", {"kind": change.kind})
    kv_set(conn, "meals_decided", key, user_id)
    return said


def linked(ctx: Ctx, m: Meal) -> Meal:
    """A meal eaten with its day's routine, for the calendar to draw it in the routine's place: the one it ticked off,
    else that day's routine of its name, which a timer may have ticked off first (4 Nov: today's lunch drawn twice)."""
    if m.item_id is not None or m.skipped or m.start is None:
        return m
    routine = routine_of(ctx, m.kind, m.date)
    return replace(m, item_id=int(routine["id"])) if routine else m


def meal_out(m: Meal, nth: int = 1) -> MealOut:
    local = lambda t: format_local(t) if t else None  # noqa: E731
    return MealOut(
        id=m.id, kind=m.kind, date=m.date.isoformat(), start=local(m.start), end=local(m.end), minutes=m.minutes,
        skipped=m.skipped, item_id=m.item_id, nth=nth,
    )  # fmt: skip


def again(ctx: Ctx, shown: list[Meal]) -> str | None:
    """The meal you last had today (not a snack): the Now bar offers having another of it (5 Nov: "sometimes i
    have 4 meals (2 dinners)"), so a second dinner isn't tapped as a snack."""
    done = [m for m in shown if m.date == ctx.today and not m.skipped and m.end and m.kind != "snack"]
    return done[-1].kind if done else None  # `shown` is in the order you started them


def offer(ctx: Ctx, today: set[str]) -> str | None:
    """The meal to offer now: one not yet recorded today whose time it is (and whose routine is still to do)."""
    for kind in PLANNED:
        routine = routine_of(ctx, kind, ctx.today)
        if kind in today or (routine is not None and routine["status"] != "todo"):
            continue
        if in_window(ctx, kind, ctx.now_utc):
            return kind
    return None


@query("meals")
def meals(ctx: Ctx, inp: Empty) -> MealsOut:
    """Your meals of the last two weeks, what Friday learned from them, the meal to offer now or the one you're
    eating, and routine lengths worth changing."""
    settings = ctx.settings["meal_tracking"]
    if not settings.on:
        return MealsOut(on=False, min_days=settings.min_days)
    every = recorded(ctx, LEARN_DAYS)
    shown = [m for m in every if m.date > ctx.today - timedelta(days=SHOWN_DAYS)]
    days: dict[str, list[MealOut]] = {}
    shown = [linked(ctx, m) for m in shown]
    place = nths(shown)
    for m in shown:
        days.setdefault(m.date.isoformat(), []).append(meal_out(m, place.get(m.id, 1)))
    now = next((m for m in reversed(shown) if not m.skipped and m.start and m.end is None), None)
    found = learn(every, settings.min_days)
    planned = planned_routines(ctx)
    changes = length_changes(found, {kind: minutes for kind, (_, minutes) in planned.items()})
    return MealsOut(
        on=True,
        eating=meal_out(now, place.get(now.id, 1)) if now else None,
        next=None if now else offer(ctx, {m.kind for m in shown if m.date == ctx.today}),
        again=None if now else again(ctx, shown),
        days=[MealDayOut(date=d, meals=ms) for d, ms in sorted(days.items(), reverse=True)],
        learned=[MealLearnedOut(**vars(x)) for x in found],
        changes=[MealChangeOut(kind=k, planned_min=planned[k][1], usual_min=v) for k, v in changes.items()],
        min_days=settings.min_days,
        times=time_changes(ctx, found, planned),
        plans=plan_offers(found, planned),
        decided=decided(ctx.settings),
    )
