"""A repeating event moved to another day from one of its times on (5 Nov: "change jaspers bday to nov 6 yearly" was
refused four times, and nothing else could move a repeat's day): the repeat moves with it."""

import dataclasses
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from friday.commands.eventwrites import queue_event_write
from friday.commands.fields import require_item, update_item
from friday.commands.registry import Ctx
from friday.commands.series import (
    calendar_of,
    keep_calendar,
    load_series,
    materialize_series,
    refuse_external,
    remove_occurrence,
    timing_on,
)
from friday.core.db import rows
from friday.core.items import FieldError, Item, validate
from friday.core.recurrence import ending_before, moved_rule, occurrences, rule_parts
from friday.core.time import format_local, format_utc, local_midnight, parse_local, parse_utc, to_local, to_utc
from friday.planner.store import event_links

COPIED = ("template", "rrule", "dtstart_local", "per_window", "release_offset_min", "due_offset_min")


def moves_day(ctx: Ctx, item: Item, times: dict[str, str]) -> bool:
    """Whether new times put an event that repeats on another day than the one it's on."""
    if item.when != "fixed" or "start_utc" not in times or item.start_utc is None:
        return False
    return local_day(ctx, times["start_utc"]) != local_day(ctx, item.start_utc)


def move_from(ctx: Ctx, item: Item, times: dict[str, str], values: dict[str, Any]) -> Item:
    """Move `item` to its new day and time, and the repeat with it from `item`'s day on. The first time moved moves
    the whole repeat; a later one ends it the day before and goes on as a new one, so what came before stays. A
    weekday it names follows (Mon and Wed, a Monday to Tuesday: Tue and Wed); the times kept keep their ids and work."""
    assert item.series_id is not None and item.occurrence_date is not None and item.start_utc and item.end_utc
    row = load_series(ctx, item.series_id)
    refuse_external(ctx, row["id"])
    if re.search(r"FREQ=(HOURLY|MINUTELY|SECONDLY)|BY(HOUR|MINUTE|SECOND)=", row["rrule"].upper()):
        raise FieldError("start", f"{item.title}'s times are part of how it repeats: change them one at a time")
    was, start = to_local(parse_utc(item.start_utc), ctx.tz), to_local(parse_utc(times["start_utc"]), ctx.tz)
    if "end_utc" in times:
        end = to_local(parse_utc(times["end_utc"]), ctx.tz)
    else:  # only a new start: it keeps its length
        end = start + timedelta(minutes=parse_utc(item.end_utc) - parse_utc(item.start_utc))
    length = (end - start) // timedelta(minutes=1)
    if length <= 0:
        raise FieldError("end", "the end comes before the start")
    rule = moved_rule(row["rrule"], was.date(), start.date())
    if rule is None:
        raise FieldError("start", f"{item.title} repeats on set dates: change how it repeats in its drawer")
    from_day = date.fromisoformat(item.occurrence_date)
    first = parse_local(row["dtstart_local"]).date()
    template = json.loads(row["template"]) | values | {"length_min": length}
    changed = {
        "rrule": rule,
        "dtstart_local": format_local(
            datetime.combine(anchor(row["rrule"], first, from_day, was, start), start.time())
        ),
        "template": json.dumps(template),
        "updated_utc": ctx.now_text,
    }
    series_id = moved_series(ctx, row, from_day, changed, whole=from_day <= first)
    move_occurrences(ctx, item, series_id, from_day, start.date() - was.date(), values)
    exact = {"start_utc": format_utc(to_utc(start, ctx.tz)), "end_utc": format_utc(to_utc(end, ctx.tz))}
    before = require_item(ctx, item.id)
    after = dataclasses.replace(before, **exact)
    validate(after)
    update_item(ctx, before, after)
    queue_event_write(ctx, after, "save", target=calendar_of(ctx, series_id))
    materialize_series(ctx, series_id)
    return after


def anchor(old_rule: str, first: date, from_day: date, was: datetime, start: datetime) -> date:
    """The repeat's new first date. A rule naming weekdays keeps its own first date (or the moved one's, if earlier)
    so its other days and its every-other-week stay; any other repeats from its first date, moved as far."""
    base = first if from_day <= first else from_day
    if "BYDAY" in rule_parts(old_rule):
        return min(base, start.date())
    return base + (start.date() - was.date())


def moved_series(ctx: Ctx, row: dict[str, Any], from_day: date, changed: dict[str, Any], whole: bool) -> int:
    """The series the moved times belong to: this one changed, or a new one from `from_day` with this one ended."""
    if whole:
        ctx.db.update("series", {"id": row["id"]}, changed)
        return int(row["id"])
    ctx.db.update(
        "series", {"id": row["id"]}, {"rrule": ending_before(row["rrule"], from_day), "updated_utc": ctx.now_text}
    )
    new_id = ctx.db.insert("series", {k: row[k] for k in COPIED} | changed | {"created_utc": ctx.now_text})
    keep_calendar(ctx, new_id, calendar_of(ctx, row["id"]))
    return new_id


def move_occurrences(
    ctx: Ctx, item: Item, series_id: int, from_day: date, shift: timedelta, values: dict[str, Any]
) -> None:
    """Each undone time from `from_day` on to its day under the moved repeat, where it is: the ones on the moved
    weekday (all of them, for a repeat naming none) by `shift`, the others staying. One the moved repeat no longer
    has, or one landing where another time already is, goes as a time the repeat lost does; the repeat then makes
    what's missing."""
    series = load_series(ctx, series_id)
    weekday = date.fromisoformat(item.occurrence_date or "").weekday()
    by_weekday = "BYDAY" in rule_parts(series["rrule"])
    found = rows(
        ctx.conn,
        "SELECT id, occurrence_date, occurrence_n FROM items WHERE series_id = ? AND status = 'todo' "
        "AND (detached = 0 OR id = ?) AND occurrence_date >= ?",
        [item.series_id, item.id, from_day.isoformat()],
    )
    moving = {r["id"] for r in found}
    target = {
        r["id"]: (moved_day(date.fromisoformat(r["occurrence_date"]), weekday, by_weekday, shift), r["occurrence_n"])
        for r in found
    }
    days = [d for d, _ in target.values()]
    has = repeat_days(series, min([from_day, *days]), max([from_day, *days]))
    held = {
        (r["occurrence_date"], r["occurrence_n"])
        for r in rows(ctx.conn, "SELECT id, occurrence_date, occurrence_n FROM items WHERE series_id = ?", [series_id])
        if r["id"] not in moving
    }
    kept: dict[int, tuple[date, int]] = {}
    for item_id in sorted(target, key=lambda i: i != item.id):  # the one you moved first
        day, n = target[item_id]
        if item_id == item.id or (day in has and (day.isoformat(), n) not in held):
            kept[item_id] = (day, n)
            held.add((day.isoformat(), n))
    links = event_links(ctx.conn, ctx.user_id)
    for item_id in moving - set(kept):
        remove_occurrence(ctx, item_id, item_id in links)
    # Later ones first when moving later (earlier ones first when earlier), so none lands on a time not yet moved.
    for item_id in sorted(kept, key=lambda i: kept[i][0], reverse=shift.days > 0):
        day = kept[item_id][0]
        before = require_item(ctx, item_id)
        timing = timing_on(ctx, series, day.isoformat())
        after = dataclasses.replace(before, **values, **timing, series_id=series_id, occurrence_date=day.isoformat())
        validate(after)
        update_item(ctx, before, after)
        if item_id != item.id:  # the moved one is written once, at its exact times
            queue_event_write(ctx, after, "save", target=calendar_of(ctx, series_id))


def moved_day(day: date, weekday: int, by_weekday: bool, shift: timedelta) -> date:
    return day + shift if not by_weekday or day.weekday() == weekday else day


def repeat_days(series: dict[str, Any], lo: date, hi: date) -> set[date]:
    start = parse_local(series["dtstart_local"])
    found = occurrences(series["rrule"], start, local_midnight(lo), local_midnight(hi + timedelta(days=1)))
    return {moment.date() for moment in found}


def local_day(ctx: Ctx, utc: str) -> date:
    return to_local(parse_utc(utc), ctx.tz).date()
