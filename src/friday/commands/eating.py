"""Tracking your meals (Sleep & meals; off until you turn it on, like sleep): "Eating now" and "Done eating", one tap
each, a meal logged after the fact or skipped, a tap at the wrong time put right, and what Friday makes of them
(`learn/meals.py`): each meal's usual time, length and skips, and the length you take offered for its routine.

A meal goes with that day's routine of its name (Lunch, Dinner): while you eat, the plan holds the routine at now (as
it holds a timed task), so no work is planned over your meal; done eating ticks the routine off, skipping skips it,
and taking a meal back opens it again.
"""

from datetime import date, timedelta

from friday.api.commands import (
    Changed,
    MealEditInput,
    MealEndInput,
    MealLengthInput,
    MealLogInput,
    MealRef,
    MealSkipInput,
    MealStartInput,
)
from friday.api.types import Empty
from friday.api.views import MealChangeOut, MealDayOut, MealLearnedOut, MealOut, MealsOut
from friday.commands.items import edit_from, set_status
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError
from friday.core.time import UNIT_MIN, ampm, format_local, format_utc, parse_utc, planning_date, to_local
from friday.learn.meals import Learned, Meal, learn, length_changes
from friday.planner.store import load_item

SHOWN_DAYS = 14
LEARN_DAYS = 56  # the last eight weeks teach what's usual
LONGEST_MIN = 4 * 60
PLANNED = ("breakfast", "lunch", "dinner")
# When a meal is yours to eat where no routine of its name says (a breakfast you don't plan): local minutes.
WINDOWS = {"breakfast": (6 * 60, 10 * 60 + 30), "lunch": (11 * 60, 14 * 60 + 30), "dinner": (17 * 60, 21 * 60)}


def tracking(ctx: Ctx) -> None:
    if not ctx.settings["meal_tracking"].on:
        raise FieldError("kind", "meal tracking is off; turn it on in Sleep & meals")


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
    ctx.db.insert(
        "meals",
        {"kind": kind, "date": day.isoformat(), "start_utc": format_utc(moment), "item_id": routine,
         "created_utc": ctx.now_text},
    )  # fmt: skip
    return Changed(message=f"Eating {kind} since {said(ctx, moment)}")


@command("meal_end", affects_plan=True)
def meal_end(ctx: Ctx, inp: MealEndInput) -> Changed:
    """Done eating (or done at the time you give)."""
    tracking(ctx)
    meal = eating(ctx)
    if meal is None:
        raise FieldError("at", "you aren't eating")
    minutes = finish(ctx, meal, moment_of(ctx, inp.at))
    return Changed(message=f"{meal['kind'].capitalize()}: {minutes} min")


@command("meal_log", affects_plan=True)
def meal_log(ctx: Ctx, inp: MealLogInput) -> Changed:
    """A meal you didn't tap, from when you started to when you finished."""
    tracking(ctx)
    start, end = moment_of(ctx, inp.start, "start"), moment_of(ctx, inp.end, "end")
    if not start < end <= start + LONGEST_MIN:
        raise FieldError("end", "a meal ends after it starts, within four hours")
    day = day_of(ctx, start)
    ticked = tick_off(ctx, open_routine(ctx, inp.kind, day), "done", end)
    ctx.db.insert(
        "meals",
        {"kind": inp.kind, "date": day.isoformat(), "start_utc": format_utc(start), "end_utc": format_utc(end),
         "item_id": ticked, "created_utc": ctx.now_text},
    )  # fmt: skip
    return Changed(message=f"Logged {inp.kind}, {said(ctx, start)} to {said(ctx, end)}")


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
    """A meal you didn't mean to record; the routine it ticked off is open again."""
    meal = meal_row(ctx, inp.id)
    if meal["item_id"] and (meal["end_utc"] or meal["skipped"]):
        routine = one(ctx.conn, "SELECT status FROM items WHERE id = ?", [meal["item_id"]])
        if routine and routine["status"] in ("done", "skipped"):
            set_status(ctx, meal["item_id"], "todo")
    ctx.db.delete("meals", {"id": inp.id})
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
    local = lambda t: to_local(parse_utc(t), ctx.tz) if t else None  # noqa: E731
    return [
        Meal(r["id"], r["kind"], date.fromisoformat(r["date"]), local(r["start_utc"]), local(r["end_utc"]),
             bool(r["skipped"]))
        for r in found
    ]  # fmt: skip


def learned(ctx: Ctx) -> list[Learned]:
    return learn(recorded(ctx, LEARN_DAYS), ctx.settings["meal_tracking"].min_days)


@command("meal_use_length", affects_plan=True)
def meal_use_length(ctx: Ctx, inp: MealLengthInput) -> Changed:
    """Plan a meal's routine at the length you take, from today on (what Sleep & meals offers)."""
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


def meal_out(m: Meal) -> MealOut:
    local = lambda t: format_local(t) if t else None  # noqa: E731
    return MealOut(
        id=m.id, kind=m.kind, date=m.date.isoformat(), start=local(m.start), end=local(m.end), minutes=m.minutes,
        skipped=m.skipped,
    )  # fmt: skip


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
    for m in shown:
        days.setdefault(m.date.isoformat(), []).append(meal_out(m))
    now = next((m for m in reversed(shown) if not m.skipped and m.start and m.end is None), None)
    found = learn(every, settings.min_days)
    planned = planned_routines(ctx)
    changes = length_changes(found, {kind: minutes for kind, (_, minutes) in planned.items()})
    return MealsOut(
        on=True,
        eating=meal_out(now) if now else None,
        next=None if now else offer(ctx, {m.kind for m in shown if m.date == ctx.today}),
        days=[MealDayOut(date=d, meals=ms) for d, ms in sorted(days.items(), reverse=True)],
        learned=[MealLearnedOut(**vars(x)) for x in found],
        changes=[MealChangeOut(kind=k, planned_min=planned[k][1], usual_min=v) for k, v in changes.items()],
        min_days=settings.min_days,
    )
