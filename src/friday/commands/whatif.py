"""What if: changes staged on the calendar (an event added or moved, a task, an optional event skipped, a shove, a
rule) tried together on a copy of your plan, and kept only when you say so.

- `whatif` applies the staged changes in one transaction that is always rolled back (`registry.tried_many`), plans
  the week with them as a replan would and without them, side by side (the plan without them is kept per plan
  generation, so staging one more change plans once), and answers with the calendar as it would be (the plan query
  itself, run on the trial plan written in a second rolled-back transaction) and what the changes cost together:
  work that would end later past its due, days whose work ends later, optional events given up, blocks that move.
  Each change also gets the quick deadline check on top of the ones before it, so you can see which one does it.
- `whatif_keep` makes them all, in order, as one command: one Undo takes them all back.

An item a staged change makes has no id until it's made, so a later change naming it (moving the event you just
added) uses a placeholder: -(1000 × that change's place + the item's place + 1), resolved each time they're tried.
"""

import json
import sqlite3
import time
from dataclasses import replace
from datetime import date
from typing import Any

from friday.api.commands import Changed, RangeInput, WhatIfChange, WhatIfInput, WhatIfKeepInput
from friday.api.views import FitLate, PlanOut, WhatIfChangeOut, WhatIfDay, WhatIfOut
from friday.commands.fitting import deadlines, hours, late_minutes, listed, short_minutes, worst_first
from friday.commands.registry import REGISTRY, Ctx, Tried, command, query, tried_many
from friday.commands.writer import Writer
from friday.core.db import rows
from friday.core.items import FieldError, Item
from friday.core.rule_text import read, sentence
from friday.core.settings import minutes_of
from friday.core.time import ampm, parse_utc, planning_date, to_local
from friday.planner.assemble import AssembledPlan, PlannedBlock
from friday.planner.build import id_of
from friday.planner.service import plan_snapshot, write_plan
from friday.planner.snapshot import BlockRow, Snapshot, read_snapshot, take_snapshot
from friday.planner.store import current_plan, load_settings

PLACE = 1000
ID_KEYS = {"id", "item_id", "depends_on_id", "ids"}
EACH_UP_TO = 8  # changes each checked on their own; more, and only all of them together
LATER_BY = 15  # minutes a day's work must end later to count
NOISE_H = 0.25  # hours a finish must move past its due to count as later (or sooner)
BEFORE: dict[tuple[str, int, int], tuple[int, AssembledPlan]] = {}  # (database, user, generation) → (now, plan)
KEPT_MIN = 10  # how long the plan without the changes stays good for the same generation
SAVED_FRESH_MIN = 30  # your saved plan stands for the plan without the changes while it's this fresh


def placeholder(change: int, item: int) -> int:
    return -(PLACE * change + item + 1)


def resolved(value: Any, made: list[list[int]], key: str = "") -> Any:
    """A staged change's input with the placeholders for items made by earlier changes put as their ids."""
    if isinstance(value, dict):
        return {k: resolved(v, made, k) for k, v in value.items()}
    if isinstance(value, list):
        return [resolved(v, made, key) for v in value]
    if key in ID_KEYS and isinstance(value, int) and value < 0:
        change, item = divmod(-value - 1, PLACE)
        if change < len(made) and item < len(made[change]):
            return made[change][item]
        raise FieldError(key, "that's an item from a change that was taken out")
    return value


def staged(changes: list[WhatIfChange]) -> list[tuple[str, dict[str, Any]]]:
    return [(c.command, c.input) for c in changes]


def resolver(payload: dict[str, Any], done: list[Tried]) -> dict[str, Any]:
    return resolved(payload, [t.created for t in done])


@query("whatif")
def whatif(ctx: Ctx, inp: WhatIfInput) -> WhatIfOut:
    """What if: the calendar with these changes, and what they'd cost together; nothing is kept."""
    began = time.perf_counter()
    changes = staged(inp.changes)
    before = take_snapshot(ctx.conn, ctx.now_utc, ctx.user_id)
    look = lambda conn, done: (done, read_snapshot(conn, ctx.now_utc, ctx.user_id))  # noqa: E731
    each = (lambda conn: read_snapshot(conn, ctx.now_utc, ctx.user_id)) if len(changes) <= EACH_UP_TO else None
    (done, after), steps = tried_many(ctx.conn, changes, look, now_utc=ctx.now_utc, user_id=ctx.user_id,
                                      each=each, resolve=resolver)  # fmt: skip
    was = without(ctx, before)
    # Started from the plan without them, so what moves is what the changes move: two plans made apart on a full
    # week wandered apart on their own (one dinner "moved" 49 blocks and slid overdue readings by days).
    started = tuple(BlockRow(b.item_id, b.start_utc, b.end_utc, b.tentative) for b in was.blocks)
    plan = plan_snapshot(replace(after, plan_blocks=started), warm=True)
    shown, again = trial_plan(ctx, changes, after, plan, inp)
    if [t.created for t in again] != [t.created for t in done]:  # something was added meanwhile: ids moved on
        raise FieldError("changes", "your plan changed while Friday tried this; try again")
    titles = {i.id: i for i in before.items} | {i.id: i for i in after.items}
    outs = []
    for n, ((name, payload), t) in enumerate(zip(changes, done, strict=True)):
        now = {i.id: i for i in (steps[n] if steps else after).items}  # as it was just after this change
        try:
            given = resolved(payload, [d.created for d in done[:n]])
        except FieldError:
            given = payload
        words = said(ctx, name, given, t, titles, now)
        outs.append(WhatIfChangeOut(said=words, error=t.error, created=t.created, changed=t.changed))
    if steps:
        for out, earlier, now, t in zip(outs, [before, *steps[:-1]], steps, done, strict=True):
            out.late = [] if t.error else newly_short(earlier, now, titles)
    return summed(ctx, before, after, was, plan, shown, outs, inp, began)


def without(ctx: Ctx, before: Snapshot) -> AssembledPlan:
    """The week without the changes: your plan as it is when nothing has changed since it was made (what you see,
    and no solve), else planned now as a replan would, kept per generation."""
    saved = current_plan(ctx.conn, ctx.user_id)
    if (
        saved is not None
        and saved["status"] == "current"
        and saved["generation"] == before.generation
        and ctx.now_utc - parse_utc(saved["created_utc"]) <= SAVED_FRESH_MIN
    ):
        return as_assembled(ctx, saved)
    key = (str(ctx.conn.execute("PRAGMA database_list").fetchone()[2]), ctx.user_id, before.generation)
    found = BEFORE.get(key)
    if found is not None and abs(found[0] - ctx.now_utc) <= KEPT_MIN:
        return found[1]
    plan = plan_snapshot(before, warm=True)
    BEFORE.clear()  # one at a time: an older generation is no use again
    BEFORE[key] = (ctx.now_utc, plan)
    return plan


def as_assembled(ctx: Ctx, saved: dict[str, Any]) -> AssembledPlan:
    """The saved plan's blocks from now on, and its report, as a solve would give them."""
    found = rows(
        ctx.conn,
        "SELECT item_id, start_utc, end_utc, tentative FROM blocks WHERE plan_id = ? AND end_utc > ? "
        "ORDER BY start_utc",
        [saved["id"], ctx.now_text],
    )
    blocks = [
        PlannedBlock(r["item_id"], parse_utc(r["start_utc"]), parse_utc(r["end_utc"]), {}, bool(r["tentative"]))
        for r in found
    ]
    report = json.loads(saved["report"] or "{}")
    stages = json.loads(saved["stage_values"] or "{}")
    return AssembledPlan(saved["generation"], int(report.get("settings_version", 0)), blocks, stages, report)


def trial_plan(
    ctx: Ctx, changes: list[tuple[str, dict[str, Any]]], after: Snapshot, plan: AssembledPlan, inp: WhatIfInput
) -> tuple[PlanOut, list[Tried]]:
    """The calendar as it would be: the trial plan written as the current one, and read back as the calendar reads
    it, in a second transaction rolled back like the first."""
    from friday.commands.queries import plan as calendar  # the plan query; imported here, as queries imports a lot

    def look(conn: sqlite3.Connection, done: list[Tried]) -> tuple[PlanOut, list[Tried]]:
        write_plan(conn, after, plan, "what if", current_plan(conn, ctx.user_id))
        settings = load_settings(conn, ctx.user_id)
        trial = Ctx(conn, Writer(conn, ctx.user_id), ctx.now_utc, "you", ctx.user_id, settings)
        return calendar(trial, RangeInput(start=inp.start, end=inp.end)), done

    return tried_many(ctx.conn, changes, look, now_utc=ctx.now_utc, user_id=ctx.user_id, resolve=resolver)[0]


def newly_short(earlier: Snapshot, now: Snapshot, titles: dict[int | None, Item]) -> list[str]:
    """What one change leaves short of its due, on top of those before it, in the quick check: "Essay 2 h"."""
    base, ex = deadlines(earlier), deadlines(now)
    was_late, late = late_minutes(base), late_minutes(ex)
    was_short, short = short_minutes(base), short_minutes(ex)
    out = []
    for key, minutes in sorted(short.items(), key=lambda kv: -kv[1] + was_short.get(kv[0], 0)):
        if late[key] > was_late.get(key, 0) + 5 and minutes > was_short.get(key, 0):
            item = titles.get(id_of(key))
            out.append(f"{item.title if item else key} {hours(minutes - was_short.get(key, 0))}")
    return out


def when(ctx: Ctx, stored: str | None) -> str:
    """ "Fri 7pm"."""
    if not stored:
        return ""
    local = to_local(parse_utc(stored), ctx.tz)
    return f"{local:%a} {ampm(f'{local:%H:%M}')}"


def said(
    ctx: Ctx, name: str, payload: dict[str, Any], t: Tried, items: dict[int | None, Item], now: dict[int | None, Item]
) -> str:
    """A staged change in words, as things were just after it (`now`): "Add Dinner with Sam, Fri 7pm", "Skip
    Climbing Club, Wed 6pm"."""
    made = now.get(t.created[0]) if t.created else None
    named = payload.get("id") if isinstance(payload.get("id"), int) else None
    target = now.get(named) or items.get(named)
    title = (made or target).title if (made or target) else payload.get("title") or payload.get("text") or "it"
    if name in ("add", "series_add"):
        if made is None:
            return f"Add {payload.get('text') or payload.get('title') or 'an item'}"
        repeats = " (repeating)" if name == "series_add" or made.series_id else ""
        if made.when == "fixed":
            return f"Add {title}, {when(ctx, made.start_utc)}{repeats}"
        due = f", due {when(ctx, made.due_utc)}" if made.due_utc else ""
        length = (made.duration_units or 0) * 15
        return f"Add {title}{f' ({hours(length)})' if length else ''}{due}{repeats}"
    if name == "edit":
        moved = target is not None and target.when == "fixed" and ("start" in payload or "end" in payload)
        new = now.get(target.id) if target is not None else None
        return f"Move {title} to {when(ctx, new.start_utc if new else None)}" if moved else f"Change {title}"
    if name == "skip":
        return f"Skip {title}, {when(ctx, target.start_utc if target else None)}".rstrip(", ")
    if name == "drop":
        return f"Delete {title}"
    if name == "pin":
        start = payload.get("start")
        return f"Plan {title} at {when(ctx, ctx.utc(start))}" if start else f"Pin {title}"
    if name == "unpin":
        return f"Let Friday place {title}"
    if name == "shove":
        return f"Keep {payload.get('range', 'that time')} free"
    if name == "rule_add":
        reading, _ = read(str(payload.get("text", "")))
        return f"Rule: {sentence(reading) if reading else payload.get('text', '')}"
    if name == "day_override":
        return f"Change {payload.get('date', 'a day')}'s limits"
    return name.replace("_", " ").capitalize()


def work_ends(ctx: Ctx, snapshot: Snapshot, plan: AssembledPlan) -> dict[str, int]:
    """When each planning day's work ends (minutes after its midnight; past midnight runs on): routines and tasks that
    run by themselves left out."""
    kinds = {i.id: i for i in snapshot.items}
    day_start = minutes_of(snapshot.settings["time"].day_start)
    out: dict[str, int] = {}
    for b in plan.blocks:
        item = kinds.get(b.item_id)
        if item is None or item.preset == "Routine" or item.background:
            continue
        day = planning_date(b.end_utc - 1, ctx.tz, day_start)
        local = to_local(b.end_utc, ctx.tz)
        minute = local.hour * 60 + local.minute + (1440 if local.date() > day else 0)
        out[day.isoformat()] = max(out.get(day.isoformat(), 0), minute)
    return out


def dues_ahead(snapshot: Snapshot, firmness: str) -> dict[int, int]:
    """Tasks due from now on, by firmness. Work already overdue is left out: it's late wherever it goes, so the plan
    moves it freely, and on a full week that read as days of slipping for one dinner."""
    return {
        i.id: parse_utc(i.due_utc)
        for i in snapshot.items
        if i.id is not None and i.due_utc and i.when != "fixed" and i.preset != "Routine"
        and (i.firmness == "hard") == (firmness == "hard") and parse_utc(i.due_utc) > snapshot.now_utc
    }  # fmt: skip


def hard_late(snapshot: Snapshot, plan: AssembledPlan) -> dict[int, float]:
    """Hours each hard due ahead finishes late, as the plan counts it (what didn't fit at all counted too)."""
    dues = dues_ahead(snapshot, "hard")
    return {int(k): float(h) for k, h in plan.report.get("late_hours", {}).items() if int(k) in dues}


def soft_past(snapshot: Snapshot, plan: AssembledPlan) -> set[int]:
    """Soft dues ahead the plan finishes after. Only whether: past a soft due, any time costs the plan the same, so
    how far past it lands means nothing (one dinner moved a reading "166 hours")."""
    dues = dues_ahead(snapshot, "soft")
    ends: dict[int, int] = {}
    for b in plan.blocks:
        if b.item_id in dues:
            ends[b.item_id] = max(ends.get(b.item_id, 0), b.end_utc)
    return {i for i, end in ends.items() if end > dues[i]}


def said_past(titles: list[str]) -> str:
    """ "would push Reading 16.4 past its due"."""
    named = " and ".join(titles[:2]) + (f" and {len(titles) - 2} more" if len(titles) > 2 else "")
    return f"would push {named} past {'its' if len(titles) == 1 else 'their'} due"


def clock(minutes: int | None) -> str | None:
    return None if minutes is None else f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


def summed(
    ctx: Ctx,
    before: Snapshot,
    after: Snapshot,
    was: AssembledPlan,
    plan: AssembledPlan,
    shown: PlanOut,
    outs: list[WhatIfChangeOut],
    inp: WhatIfInput,
    began: float,
) -> WhatIfOut:
    """What the changes cost together, against the plan without them; days that end later, in the range shown."""
    shown_from, shown_to = inp.start[:10], inp.end[:10]
    titles = {i.id: i.title for i in after.items} | {i.id: i.title for i in before.items}
    old, new = hard_late(before, was), hard_late(after, plan)
    late = lambda i, b, a: FitLate(item_id=i, title=titles.get(i, f"T{i}"), before_h=round(b, 2), after_h=round(a, 2))  # noqa: E731
    later = worst_first(late(i, old.get(i, 0.0), h) for i, h in new.items() if h > old.get(i, 0.0) + NOISE_H)
    sooner = [late(i, h, new.get(i, 0.0)) for i, h in old.items() if new.get(i, 0.0) < h - NOISE_H]
    slipped = sorted(titles.get(i, f"T{i}") for i in soft_past(after, plan) - soft_past(before, was))
    ends_was, ends = work_ends(ctx, before, was), work_ends(ctx, after, plan)
    later_days = [
        WhatIfDay(date=d, before=clock(ends_was.get(d)), after=clock(m))
        for d, m in sorted(ends.items())
        if m > ends_was.get(d, 0) + LATER_BY and max(ctx.today.isoformat(), shown_from) <= d < shown_to
    ]
    notices = [n for n in plan.report.get("notices", []) if n not in was.report.get("notices", [])]
    blocks = lambda p: {(b.item_id, b.start_utc, b.end_utc) for b in p.blocks}  # noqa: E731
    known = {i.id for i in before.items}
    moved = len({b for b in blocks(plan) - blocks(was) if b[0] in known})
    if not [o for o in outs if not o.error]:
        verdict, words = "fits", "Nothing to try yet"
    elif later:
        verdict, words = "late", listed(later) + (f"; and {said_past(slipped)}" if slipped else "")
    elif slipped:
        verdict, words = "late", said_past(slipped)[0].upper() + said_past(slipped)[1:]
    elif later_days:
        named = " and ".join(date.fromisoformat(d.date).strftime("%A") for d in later_days[:2])
        verdict, words = "tight", f"Fits, with work ending later on {named}"
    else:
        verdict, words = "fits", "Fits: nothing gets later"
    if sooner and verdict != "late":
        words += f"; {sooner[0].title} {'and more ' if len(sooner) > 1 else ''}less late"
    return WhatIfOut(
        plan=shown, changes=outs, verdict=verdict, said=words, later=later, sooner=sooner, slipped=slipped,
        later_days=later_days,
        notices=notices, moved=moved, seconds=round(time.perf_counter() - began, 2),
    )  # fmt: skip


@command("whatif_keep", affects_plan=True)
def whatif_keep(ctx: Ctx, inp: WhatIfKeepInput) -> Changed:
    """Keep what you tried in What if: every change made, in order, as one; one Undo takes them all back."""
    made: list[list[int]] = []
    for n, (name, payload) in enumerate(staged(inp.changes)):
        spec = REGISTRY.get(name)
        if spec is None or not spec.mutates or not spec.logged:
            raise FieldError("changes", f"{name!r} isn't a change Friday can keep")
        before = len(ctx.db.changes)
        given = spec.input_type.model_validate(resolved(payload, made))
        settings = load_settings(ctx.conn, ctx.user_id)  # a rule kept before it counts for it
        try:
            spec.fn(Ctx(ctx.conn, ctx.db, ctx.now_utc, ctx.actor, ctx.user_id, settings, ctx.command_id), given)
        except FieldError as error:
            raise FieldError("changes", f"change {n + 1} ({name.replace('_', ' ')}): {error}") from error
        new = ctx.db.changes[before:]
        made.append([int(c["key"]["id"]) for c in new if c["table"] == "items" and c["op"] == "insert"])
    count = len(inp.changes)
    return Changed(message=f"Kept {count} change{'' if count == 1 else 's'} from What if")
