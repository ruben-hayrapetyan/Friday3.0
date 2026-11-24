"""Pro tips (#23): a feature you may be missing, in a line that slides in at the bottom right for five seconds (24 Nov,
the user: "pro tips should be a popup on the bottom right corner that just slides in for 5s. they should be very short
and just tell the user on features that they could be missing out based on their usage. don't tell them that its based
on the usage"). Each tip has a plain check of how Friday is used; at most one a day, the same one at most three times
a week apart, and none once its habit is gone.

Which habits (the user's choices): work made as events, meals made as events, to-dos with no due date or length, most
blocks locked, never timing work, done all at once, huge single to-dos, an overdue pile, no rules of their own, and
work in parts not made a project."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from friday.api.commands import Changed, TipInput
from friday.api.types import Empty
from friday.api.views import TipOut
from friday.commands.registry import Ctx, command, query
from friday.commands.rules import readings
from friday.core.db import rows
from friday.core.guess import STUDY, guess_preset
from friday.core.time import UNIT_MIN, format_utc, parse_utc, to_local
from friday.planner.store import event_links, kv_get, kv_set

DAY = 1440
TIMES = 3  # the same tip at most this often
APART = 7  # days between showings of one tip
# an event's title that's work; "midterm" alone is the exam itself, an event (studying for it says "study for", STUDY)
WORK = {"Assignment", "Reading", "Project"}
MEAL = re.compile(r"^\s*(breakfast|brunch|lunch|dinner|supper)\s*$", re.IGNORECASE)
# a step in a title: "Essay outline", "Essay draft", "Lab report part 2"
STEP = re.compile(r"\s+(outline|draft|first draft|final( draft)?|revis(e|ion)|research|edit|part\s*\d+|step\s*\d+)$",
                  re.IGNORECASE)  # fmt: skip


@dataclass(frozen=True)
class Tip:
    id: str
    text: str
    page: str  # where the feature is: a click on the tip opens it
    applies: Callable[[Ctx], bool]


def todo(ctx: Ctx, where: str = "1", args: tuple = ()) -> list[dict[str, Any]]:
    return rows(ctx.conn, f"SELECT * FROM items WHERE user_id = ? AND status = 'todo' AND {where}",  # noqa: S608
                [ctx.user_id, *args])  # fmt: skip


def near(ctx: Ctx, days: int = 14) -> tuple[str, str]:
    return format_utc(ctx.now_utc - days * DAY), format_utc(ctx.now_utc + days * DAY)


def work_as_events(ctx: Ctx) -> bool:
    """Events you made in Friday whose titles are work ("Study for prelim", "Essay"): two or more around now."""
    lo, hi = near(ctx)
    linked = event_links(ctx.conn, ctx.user_id)
    made = [r for r in todo(ctx, "when_kind = 'fixed' AND end_utc > ? AND start_utc < ?", (lo, hi))
            if r["id"] not in linked and (r["preset"] or "") not in ("Exam", "Class")]  # fmt: skip
    presets = set(ctx.settings["presets"])
    return sum(1 for r in made if STUDY.search(r["title"]) or guess_preset(r["title"], presets) in WORK) >= 2


def meals_as_events(ctx: Ctx) -> bool:
    """Events called just Breakfast, Lunch or Dinner (not "Lunch with Sam"): three or more around now."""
    lo, hi = near(ctx)
    found = todo(ctx, "when_kind = 'fixed' AND end_utc > ? AND start_utc < ?", (lo, hi))
    return sum(1 for r in found if MEAL.match(r["title"])) >= 3


def open_work(ctx: Ctx) -> list[dict[str, Any]]:
    """To-dos of your own: not events, not repeating, not steps."""
    return todo(ctx, "when_kind != 'fixed' AND series_id IS NULL AND parent_id IS NULL")


def no_due_or_length(ctx: Ctx) -> bool:
    """Five or more to-dos with neither a due date nor a length, two in five of them or more."""
    work = open_work(ctx)
    # a length you gave: a to-do added without one plans as a stand-in hour (duration_units), your estimate unset
    bare = [r for r in work if r["due_utc"] is None and r["your_estimate_units"] is None]
    return len(bare) >= 5 and len(bare) * 5 >= len(work) * 2


def most_locked(ctx: Ctx) -> bool:
    """Five or more blocks still to come locked, more than pinned ones."""
    now = format_utc(ctx.now_utc)
    sql = "SELECT p.kind FROM pins p JOIN items i ON i.id = p.item_id WHERE i.user_id = ? AND p.end_utc > ?"
    kinds = [r["kind"] for r in rows(ctx.conn, sql, [ctx.user_id, now])]
    return kinds.count("locked") >= 5 and kinds.count("locked") > kinds.count("preferred")


def finished(ctx: Ctx, days: int) -> list[dict[str, Any]]:
    """Work finished in the last `days` days: not events, not meals or routines."""
    since = format_utc(ctx.now_utc - days * DAY)
    return rows(ctx.conn, "SELECT * FROM items WHERE user_id = ? AND status = 'done' AND when_kind != 'fixed' "
                          "AND completed_utc >= ? AND COALESCE(preset, '') NOT IN ('Routine', 'Habit')",
                [ctx.user_id, since])  # fmt: skip


def timed(ctx: Ctx, days: int) -> set[int]:
    since = format_utc(ctx.now_utc - days * DAY)
    return {r["item_id"] for r in rows(ctx.conn, "SELECT DISTINCT p.item_id FROM progress p JOIN items i ON "
                                                 "i.id = p.item_id WHERE i.user_id = ? AND p.source = 'timer' AND "
                                                 "p.created_utc >= ?", [ctx.user_id, since])}  # fmt: skip


def never_timing(ctx: Ctx) -> bool:
    """Ten or more things finished in three weeks, none of them timed."""
    return len(finished(ctx, 21)) >= 10 and not timed(ctx, 21)


def done_all_at_once(ctx: Ctx) -> bool:
    """On two or more days of the last two weeks, five or more untimed things marked done within a quarter hour."""
    clocked = timed(ctx, 14)
    times = sorted(parse_utc(r["completed_utc"]) for r in finished(ctx, 14) if r["id"] not in clocked)
    days = set()
    for i in range(len(times) - 4):
        if times[i + 4] - times[i] <= 15:
            days.add(to_local(times[i], ctx.tz).date())
    return len(days) >= 2


def huge_todo(ctx: Ctx) -> bool:
    """A to-do of eight hours or more, with no steps, that isn't a project."""
    big = todo(ctx, "when_kind != 'fixed' AND duration_units >= ? AND COALESCE(preset, '') != 'Project'",
               (480 // UNIT_MIN,))
    with_steps = {r["parent_id"] for r in todo(ctx, "parent_id IS NOT NULL")}
    return any(r["id"] not in with_steps for r in big)


def overdue_pile(ctx: Ctx) -> bool:
    """Five or more to-dos more than a week past due."""
    week_ago = format_utc(ctx.now_utc - 7 * DAY)
    return len(todo(ctx, "when_kind != 'fixed' AND due_utc IS NOT NULL AND due_utc < ?", (week_ago,))) >= 5


def no_rules(ctx: Ctx) -> bool:
    """A week into Friday with no rule of your own words."""
    first = rows(ctx.conn, "SELECT MIN(created_utc) AS at FROM items WHERE user_id = ?", [ctx.user_id])[0]["at"]
    return first is not None and ctx.now_utc - parse_utc(first) >= 7 * DAY and not readings(ctx)


def work_in_parts(ctx: Ctx) -> bool:
    """Two or more to-dos that are steps of one piece of work ("Essay outline", "Essay draft"), not in a project; or a
    to-do that waits for another, outside a project."""
    stems: dict[str, int] = {}
    for r in open_work(ctx):
        found = STEP.search(r["title"])
        if found:
            stem = r["title"][: found.start()].strip().lower()
            stems[stem] = stems.get(stem, 0) + 1
    if any(n >= 2 for n in stems.values()):
        return True
    sql = (
        "SELECT d.item_id FROM dependencies d JOIN items i ON i.id = d.item_id "
        "WHERE i.user_id = ? AND i.status = 'todo' AND i.parent_id IS NULL"
    )
    waits = rows(ctx.conn, sql, [ctx.user_id])
    return bool(waits)


# In the order they're offered: what most changes the plan first.
TIPS = (
    Tip("work_events", "Add work as a to-do, and Friday finds the time for it.", "/todo", work_as_events),
    Tip("meal_events", "Friday plans your meals for you: no meal events needed.", "/", meals_as_events),
    Tip(
        "due_and_length",
        "Give a to-do a due date and a length, and Friday plans it at the right time.",
        "/todo",
        no_due_or_length,
    ),
    Tip("projects", "Work in parts? Make it a project, and its steps plan in order.", "/projects", work_in_parts),
    Tip("huge", "Split big work into a project with steps, and Friday spreads it out.", "/projects", huge_todo),
    Tip("overdue", "Old to-dos past due? Drop them or give them a new date in To-do.", "/todo", overdue_pile),
    Tip("locked", "Pin a block instead of locking it: Friday keeps it there unless it has to move.", "/", most_locked),
    Tip("timing", "Time your work from the Now bar, and Friday learns how long things take.", "/", never_timing),
    Tip(
        "done_as_you_go",
        "Mark things done as you finish, and Friday learns how long they take.",
        "/todo",
        done_all_at_once,
    ),
    Tip("rules", "Tell Friday how you like your days in Rules, in your own words.", "/rules", no_rules),
)


def seen(ctx: Ctx) -> dict[str, list[str]]:
    return kv_get(ctx.conn, "tips_shown", {}, ctx.user_id) or {}


def today(ctx: Ctx) -> date:
    return to_local(ctx.now_utc, ctx.tz).date()


def due(shown: dict[str, list[str]], tip: str, on: date) -> bool:
    """Not shown three times yet, and not in the last week."""
    dates = shown.get(tip, [])
    return len(dates) < TIMES and (not dates or date.fromisoformat(max(dates)) <= on - timedelta(days=APART))


@query("tips")
def tips(ctx: Ctx, inp: Empty) -> TipOut:
    """The tip to show now, if any: the first whose habit holds and that's due, none if one was shown today."""
    shown, on = seen(ctx), today(ctx)
    if any(on.isoformat() in dates for dates in shown.values()):
        return TipOut()
    for tip in TIPS:
        if due(shown, tip.id, on) and tip.applies(ctx):
            return TipOut(id=tip.id, text=tip.text, page=tip.page)
    return TipOut()


@command("tip_shown", logged=False)  # what the app showed, nothing of yours to undo
def tip_shown(ctx: Ctx, inp: TipInput) -> Changed:
    """A tip was shown: counted, so it's shown at most three times, a week apart, and nothing else that day."""
    if inp.id not in {t.id for t in TIPS}:
        return Changed(message="No such tip")
    shown = seen(ctx)
    on = today(ctx).isoformat()
    if on not in shown.get(inp.id, []):
        shown[inp.id] = [*shown.get(inp.id, []), on]
    kv_set(ctx.conn, "tips_shown", shown, ctx.user_id)
    return Changed(message="Shown")
