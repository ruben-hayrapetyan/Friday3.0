"""Repeats (DESIGN §6.3): series_add, series_edit, series_stop, skip, and materializing occurrences."""

import contextlib
import json
import re
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Any

from friday.api.commands import (
    Changed,
    Empty,
    ItemRef,
    ItemResult,
    RepeatInput,
    SeriesAddInput,
    SeriesEditInput,
    SeriesOut,
    SeriesRef,
    SeriesSpacingInput,
)
from friday.api.views import SeriesRow
from friday.commands.eventwrites import queue_event_write, writes_to
from friday.commands.fields import (
    all_day_is_free,
    given_fields,
    insert_item,
    item_out,
    new_item,
    require_item,
    to_item_values,
)
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError, with_defaults
from friday.core.recurrence import counted_on, describe, ending_before, next_occurrence, read_repeat
from friday.core.rows import item_to_row
from friday.core.series import Series, make_occurrence, materialize, occurrence_timing
from friday.core.time import ampm, format_local, local_midnight, parse_local, parse_utc, to_local
from friday.planner.store import area_names, event_links, kv_get

TIME_KEYS = ("start_utc", "end_utc", "release_utc", "due_utc")


def rule_from(ctx: Ctx, every: str) -> str:
    words = every.lower().split()
    words = words[words[:1] == ["every"] :]
    if not words:
        raise FieldError("every", "say how it repeats, like `fri` or `2w thu`")
    found = read_repeat(words, 0, ctx.today)
    if found is None:
        raise FieldError("every", f"{every!r} isn't a repeat like `mon,wed` or `2w thu`")
    return found[0]


def create_series(
    ctx: Ctx, given: dict[str, Any], repeat: dict[str, Any], calendar: str | None = None
) -> tuple[int, int]:
    """A series from item fields and a repeat (`every` shorthand or a parsed `rrule`); returns its id and count. A
    repeating event goes to `calendar` ("" keeps it only in Friday), else where new events go, as a one-off does."""
    series_id = new_series(ctx, to_item_values(ctx, given), repeat)
    if calendar is not None:
        keep_calendar(ctx, series_id, calendar)
    made = materialize_series(ctx, series_id)
    return series_id, made + placed_first(ctx, series_id)


def placed_first(ctx: Ctx, series_id: int) -> int:
    """The event you placed, on a day its repeat leaves out ("every weekday" for a Saturday's): kept beside the
    repeat, as a calendar keeps a repeat's first time (8 Nov: it vanished). Only when a repeat is made from an event:
    a repeat split or moved later starts where its rule does."""
    row = load_series(ctx, series_id)
    series = as_series(row)
    start = parse_local(series.dtstart_local)
    if series.template.get("when") != "fixed" or start.date() < ctx.today:
        return 0
    timing = occurrence_timing(series, start, ctx.tz)
    there = "SELECT 1 AS yes FROM items WHERE series_id = ? AND start_utc = ?"
    if one(ctx.conn, there, [series_id, timing["start_utc"]]):
        return 0
    placed = replace(make_occurrence(series, start, 0, timing), detached=True)
    item_id = insert_item(ctx, with_defaults(placed))
    if not row["external_id"]:
        queue_event_write(ctx, require_item(ctx, item_id), "save", target=calendar_of(ctx, series_id))
    return 1


def calendar_of(ctx: Ctx, series_id: int) -> str | None:
    """The calendar a repeating event made here goes to: the one you named for it ("" for only in Friday), else None
    (where new events go)."""
    return (kv_get(ctx.conn, "series_calendars", {}, ctx.user_id) or {}).get(str(series_id))


def keep_calendar(ctx: Ctx, series_id: int, calendar: str | None) -> None:
    if calendar is None:
        return
    kept = kv_get(ctx.conn, "series_calendars", {}, ctx.user_id) or {}
    ctx.db.upsert(
        "kv",
        {"user_id": ctx.user_id, "key": "series_calendars"},
        {"value": json.dumps(kept | {str(series_id): calendar})},
    )


def new_series(ctx: Ctx, values: dict[str, Any], repeat: dict[str, Any]) -> int:
    """The series row for item values and a repeat, its occurrences not made yet."""
    rule = repeat.get("rrule") or rule_from(ctx, repeat["every"])
    values = dict(values)
    start = values.get("start_utc")
    if start:
        dtstart = format_local(to_local(parse_utc(start), ctx.tz))
        length = (parse_utc(values["end_utc"]) - parse_utc(start)) if values.get("end_utc") else 60
        values |= {"when": "fixed", "length_min": length}
    else:
        # a task with a due repeats from its due's day (8 Nov: "pay rent" due the 1st came due the 1st, the 31st, …
        # as its offset was counted from today)
        due = to_local(parse_utc(values["due_utc"]), ctx.tz).date() if values.get("due_utc") else ctx.today
        dtstart = repeat.get("dtstart_local") or format_local(local_midnight(due) + timedelta(minutes=ctx.day_start))
    offsets = {k: repeat.get(k) for k in ("release_offset_min", "due_offset_min")}
    for key, field in (("release_offset_min", "release_utc"), ("due_offset_min", "due_utc")):
        if not start and offsets[key] is None and values.get(field):
            # "lunch every day 11:30am-2:30pm": the first day's window, kept for every day after
            offsets[key] = (to_local(parse_utc(values[field]), ctx.tz) - parse_local(dtstart)) // timedelta(minutes=1)
    template = template_of(ctx, values)
    series_id = ctx.db.insert(
        "series",
        {
            "template": json.dumps(template),
            "rrule": rule,
            "dtstart_local": dtstart,
            "per_window": repeat.get("per_window") or 1,
            **offsets,
            "created_utc": ctx.now_text,
            "updated_utc": ctx.now_text,
        },
    )
    return series_id


# What an item's repeat doesn't copy: who it is, and where it stands.
NOT_REPEATED = ("id", "status", "series_id", "occurrence_date", "occurrence_n", "detached", "created_utc",
                "updated_utc", "completed_utc")  # fmt: skip


@command("repeat", affects_plan=True)
def repeat(ctx: Ctx, inp: RepeatInput) -> SeriesOut:
    """Make something you have repeat from its own date and time ("Salsa every Friday", for this Friday's Salsa);
    it stays the first time, with what you've done on it. One from a Google calendar Friday may change repeats there
    (30 Oct: "the friday night salsa that's on this week should be a weekly event" failed with "make it repeat
    there"): the calendar gets the repeat, and its later times come in from it as this series' occurrences."""
    item = require_item(ctx, inp.id)
    if item.series_id is not None:
        raise FieldError("id", f"{item.title} repeats already; change how in its drawer")
    link = event_links(ctx.conn, ctx.user_id).get(item.id or 0)
    made_here = link is not None and written_before_linked(ctx, item.id or 0)
    if link is not None and not made_here:
        if (
            link.kind not in ("gcal", "mac")
            or not link.event_id
            or not writes_to(ctx.conn, ctx.user_id, link.source_id)
        ):
            raise FieldError("id", f"{item.title} comes from {link.calendar or 'your calendar'}: make it repeat there")
        # the repeat's id in the calendar: Google's event, or EventKit's identifier (an occurrence's start dropped)
        found = re.match(r"^(.*)@\d+$", link.event_id) if link.kind == "mac" else None
        rule = rule_from(ctx, inp.every)
        if item.start_utc:
            # this time is the repeat's first, so its own day must be one of the rule's ("every sat", for a Friday's,
            # would leave it out, and the calendar's times and Friday's wouldn't match)
            local = to_local(parse_utc(item.start_utc), ctx.tz)
            day = DAYS[local.weekday()]
            days = next((p.removeprefix("BYDAY=") for p in rule.split(";") if p.startswith("BYDAY=")), "")
            if days and day not in [d[-2:] for d in days.split(",")]:
                raise FieldError("every", f"{item.title} is on a {local:%A}: repeat it from there, or move it first")
        return repeat_in_calendar(ctx, item, found[1] if found else link.event_id, rule)
    values = {k: v for k, v in vars(item).items() if v is not None and k not in NOT_REPEATED}
    repeat_of: dict[str, Any] = {"every": inp.every}
    if not item.start_utc and item.due_utc:
        # a task repeats from its own due day (it began from today's, so a Friday's came due on the wrong days)
        due = to_local(parse_utc(item.due_utc), ctx.tz)
        repeat_of["dtstart_local"] = format_local(local_midnight(due.date()) + timedelta(minutes=ctx.day_start))
    series_id = new_series(ctx, values, repeat_of)
    if item.id in (kv_get(ctx.conn, "friday_only_events", [], ctx.user_id) or []):
        keep_calendar(ctx, series_id, "")  # one you kept only in Friday: its repeats stay here too
    elif made_here and link is not None and link.calendar_id:
        keep_calendar(ctx, series_id, link.calendar_id)  # each later time goes where this one went
    series = as_series(load_series(ctx, series_id))
    times = materialize(series, ctx.today, ctx.settings["time"].materialize_days, ctx.tz, set())
    mine = next((t for t in times if (t.start_utc or t.due_utc) == (item.start_utc or item.due_utc)), None)
    if mine is not None:  # this one is the first time; the series makes the rest
        ctx.db.update("items", {"id": item.id}, {"series_id": series_id, "occurrence_date": mine.occurrence_date,
                                                 "occurrence_n": mine.occurrence_n})  # fmt: skip
    else:  # its own day isn't one of the rule's ("every weekday" for a Saturday's): it stays, beside the repeat
        when = to_local(parse_utc(item.start_utc or item.due_utc or ctx.now_text), ctx.tz)
        ctx.db.update("items", {"id": item.id}, {"series_id": series_id, "occurrence_date": f"{when:%Y-%m-%d}",
                                                 "occurrence_n": 0, "detached": 1})  # fmt: skip
    materialize_series(ctx, series_id)
    return series_out(ctx, series_id)


def written_before_linked(ctx: Ctx, item_id: int) -> bool:
    """An event Friday made and saved to a calendar, rather than one read from it (8 Nov, a user: one made here and
    then made to repeat was handed to Google to repeat, and Friday showed one time until the next read, or for good
    when it doesn't read that calendar): its first save was queued before anything tied it to the calendar's event."""
    found = one(
        ctx.conn,
        "SELECT 1 AS yes FROM event_writes w WHERE w.item_id = ? AND w.op = 'save' AND w.queued_utc <= ("
        "SELECT min(s.created_utc) FROM suggestions s WHERE s.item_id = ? AND s.status = 'accepted') LIMIT 1",
        [item_id, item_id],
    )
    return found is not None


def repeat_in_calendar(ctx: Ctx, item: Any, event_id: str, rule: str) -> SeriesOut:
    """The repeat goes to the event's calendar (`event_writes` op `repeat`: sent to Google, or made by the Mac app
    through EventKit for one of the Mac's calendars), and the series that mirrors a calendar's repeat is made now,
    this time its first: the next sync takes the later times in as its occurrences without asking
    (`suggesting.said_of_series`), and keeps this one (the write ties it to the repeat's first time)."""
    batch = f"repeat:{event_id}"
    row = ctx.db.fetch("items", {"id": item.id})
    assert row is not None
    series_id = mirror(ctx, row, batch, f"gcal:{event_id}", rule)
    on = format_local(to_local(parse_utc(item.start_utc), ctx.tz))[:10]
    ctx.db.update("items", {"id": item.id}, {"series_id": series_id, "occurrence_date": on, "occurrence_n": 1})
    ctx.db.insert("event_writes", {"item_id": item.id, "op": "repeat", "rule": rule, "queued_utc": ctx.now_text})
    return series_out(ctx, series_id)


def template_of(ctx: Ctx, values: dict[str, Any]) -> dict[str, Any]:
    """The item fields every occurrence gets, preset applied and checked on a sample occurrence."""
    length = values.pop("length_min", None)
    sample = {k: v for k, v in values.items() if k not in TIME_KEYS}
    if length is not None:  # a fixed sample needs some start and end to validate
        sample |= {"start_utc": "2000-01-01T00:00Z", "end_utc": "2000-01-01T01:00Z"}
    else:  # and a flexible one the window every occurrence gets (a target needs one)
        sample |= {"release_utc": "2000-01-01T00:00Z", "due_utc": "2000-01-08T00:00Z"}
    item = new_item(ctx, sample)
    if item.when != "fixed" and item.amount in ("fixed", "elastic") and item.firmness == "none":
        item.firmness = "soft"  # an occurrence belongs to its window; with none it could drift into the next one's
    template = {k: v for k, v in vars(item).items() if v is not None and k not in (*TIME_KEYS, "id", "status")}
    return template | ({"length_min": length} if length is not None else {})


def load_series(ctx: Ctx, series_id: int) -> dict[str, Any]:
    found = one(ctx.conn, "SELECT * FROM series WHERE user_id = ? AND id = ?", [ctx.user_id, series_id])
    if found is None:
        raise FieldError("id", f"no series {series_id}")
    return found


def as_series(row: dict[str, Any]) -> Series:
    return Series(
        row["id"],
        json.loads(row["template"]),
        row["rrule"],
        row["dtstart_local"],
        row["created_utc"],
        row["per_window"],
        row["release_offset_min"],
        row["due_offset_min"],
        bool(row["active"]),
    )


def materialize_series(ctx: Ctx, series_id: int) -> int:
    """Create the missing occurrences from today to `materialize_days` ahead; returns how many. Each time of a
    repeating event made here goes to its calendar, as a one-off event does (28 Oct: Gym, CUAI and Salsa, repeats,
    were never put on Google): one event there per time, so each changes or goes on its own."""
    row = load_series(ctx, series_id)
    series = as_series(row)
    existing = {
        (r["occurrence_date"], r["occurrence_n"])
        for r in rows(ctx.conn, "SELECT occurrence_date, occurrence_n FROM items WHERE series_id = ?", [series_id])
    }
    made = materialize(series, ctx.today, ctx.settings["time"].materialize_days, ctx.tz, existing)
    calendar = calendar_of(ctx, series_id)
    for item in made:
        item_id = insert_item(ctx, with_defaults(item))
        if not row["external_id"]:  # a calendar's own repeat is that calendar's already
            queue_event_write(ctx, require_item(ctx, item_id), "save", target=calendar)
    return len(made)


def remove_future_occurrences(ctx: Ctx, series_id: int, from_day: date, and_later: bool = False) -> list[int]:
    """Delete undone, undetached occurrences from `from_day` on; returns the ones kept: detached, or being timed
    (you're on it now, so it isn't taken from under the timer). `and_later`: on a calendar, every later time goes
    from there too, those Friday hasn't made yet included (the repeat itself is going)."""
    kept = []
    timed = {r["item_id"] for r in rows(ctx.conn, "SELECT item_id FROM timer WHERE user_id = ?", [ctx.user_id])}
    links = event_links(ctx.conn, ctx.user_id)
    for row in rows(
        ctx.conn,
        "SELECT id, detached FROM items WHERE series_id = ? AND status = 'todo' AND occurrence_date >= ?",
        [series_id, from_day.isoformat()],
    ):
        if row["detached"] or row["id"] in timed:
            kept.append(row["id"])
        else:
            remove_occurrence(ctx, row["id"], row["id"] in links, and_later)
    return kept


def remove_occurrence(ctx: Ctx, item_id: int, on_calendar: bool, and_later: bool = False) -> None:
    if on_calendar:
        # On a calendar: taken off it too, and kept here as dropped so the calendar's copy stays tied to it until
        # it's gone (deleted outright, the calendar would bring it back as an event of its own).
        dropped = replace(require_item(ctx, item_id), status="dropped")
        ctx.db.update("items", {"id": item_id}, {"status": "dropped", "updated_utc": ctx.now_text})
        queue_event_write(ctx, dropped, "delete_from" if and_later else "delete")
    else:
        delete_item(ctx, item_id)


def delete_item(ctx: Ctx, item_id: int) -> None:
    """Delete an item and, first, every row that refers to it, so undo can bring all of them back: its steps go on
    without it, what a calendar or mail suggested lets go of it (and is tied to it again by undo), and a timer on it
    stops."""
    for row in rows(ctx.conn, "SELECT id FROM items WHERE parent_id = ?", [item_id]):
        ctx.db.update("items", {"id": row["id"]}, {"parent_id": None})
    for column in ("item_id", "duplicate_of"):
        for row in rows(ctx.conn, f"SELECT id FROM suggestions WHERE {column} = ?", [item_id]):
            ctx.db.update("suggestions", {"id": row["id"]}, {column: None})
    if one(ctx.conn, "SELECT 1 FROM timer WHERE user_id = ? AND item_id = ?", [ctx.user_id, item_id]):
        ctx.db.delete("timer", {"user_id": ctx.user_id, "item_id": item_id})
    for table, column in (
        ("pins", "item_id"),
        ("dependencies", "item_id"),
        ("dependencies", "depends_on_id"),
        ("progress", "item_id"),
    ):
        for row in rows(ctx.conn, f"SELECT id FROM {table} WHERE {column} = ?", [item_id]):
            ctx.db.delete(table, {"id": row["id"]})
    ctx.db.delete("items", {"id": item_id})


def edit_series_from(
    ctx: Ctx,
    series_id: int,
    from_date: str,
    given: dict[str, Any],
    every: str | None = None,
    per_window: int | None = None,
    offsets: dict[str, int] | None = None,
) -> int:
    """End the series the day before `from_date` and start a changed copy on it; returns the new series id. `offsets`:
    a new window (`release_offset_min`, `due_offset_min` from the day's start), as a meal's learned time gives."""
    old = load_series(ctx, series_id)
    day = date.fromisoformat(from_date)
    at = parse_local(old["dtstart_local"]).time()
    values = to_item_values(ctx, given)
    template_times = {}
    if every is not None and values.get("start_utc"):
        # a new pattern with its time (8 Nov: the editor sent the time as an edit first, which split the repeat once,
        # and the pattern split it again: every Wednesday twice): one split, at the new time and length
        moved = to_local(parse_utc(values["start_utc"]), ctx.tz)
        at = moved.time()
        if values.get("end_utc"):
            template_times["length_min"] = parse_utc(values["end_utc"]) - parse_utc(values["start_utc"])
    if every is None:
        first = continued_from(old, day)
    else:  # a new rule starts on its first day from then (a start on a day it leaves out would be kept as placed)
        begins = datetime.combine(day, at)
        first = next_occurrence(rule_from(ctx, every), begins, begins - timedelta(seconds=1)) or begins
    ctx.db.update("series", {"id": series_id}, {"rrule": ending_before(old["rrule"], day), "updated_utc": ctx.now_text})
    remove_future_occurrences(ctx, series_id, day)
    template = json.loads(old["template"]) | without_times(values) | template_times
    new_id = ctx.db.insert(
        "series",
        {
            "template": json.dumps(template),
            "rrule": counted_on(
                rule_from(ctx, every) if every else old["rrule"], old["rrule"], parse_local(old["dtstart_local"]), day
            ),  # fmt: skip
            "dtstart_local": format_local(first),
            "per_window": per_window or old["per_window"],
            "release_offset_min": old["release_offset_min"],
            "due_offset_min": old["due_offset_min"],
            **(offsets or {}),
            "created_utc": ctx.now_text,
            "updated_utc": ctx.now_text,
        },
    )
    keep_calendar(ctx, new_id, calendar_of(ctx, series_id))  # the changed copy goes where the series went
    materialize_series(ctx, new_id)
    return new_id


def continued_from(old: dict[str, Any], day: date) -> datetime:
    """Where the same repeat picks up from `day`: its next time on or after it, not the day itself (7 Nov: a yearly
    birthday edited from today started again today, every one of them, as its rule takes its date from the start)."""
    start = parse_local(old["dtstart_local"])
    found = next_occurrence(old["rrule"], start, datetime.combine(day, time.min) - timedelta(microseconds=1))
    return found or datetime.combine(day, start.time())


def without_times(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if k not in TIME_KEYS}


def retimed(ctx: Ctx, row: dict[str, Any], item: Any, times: dict[str, str]) -> dict[str, Any]:
    """The series' row once one of its times has new times from then on (31 Oct: "Salsa at 1:25 from the 7th on"
    moved nothing): a fixed one's time of day and length; a window's opening and due, from its day's start. Within
    the day: a repeat moves to another day by changing how it repeats."""
    template = json.loads(row["template"])
    first = parse_local(row["dtstart_local"])
    if re.search(r"FREQ=(HOURLY|MINUTELY|SECONDLY)|BY(HOUR|MINUTE|SECOND)=", row["rrule"].upper()):
        raise FieldError("start", f"{item.title}'s times are part of how it repeats: change them one at a time")
    if template.get("when") == "fixed":
        was = to_local(parse_utc(item.start_utc), ctx.tz)
        start = to_local(parse_utc(times.get("start_utc", item.start_utc)), ctx.tz)
        end = to_local(parse_utc(times.get("end_utc", item.end_utc)), ctx.tz)
        if start.date() != was.date():
            raise FieldError("start", f"{item.title} moves to another day by changing how it repeats")
        length = (end - start) // timedelta(minutes=1)
        if length <= 0:
            raise FieldError("end", "the end comes before the start")
        return row | {
            "dtstart_local": format_local(datetime.combine(first.date(), start.time())),
            "template": json.dumps(template | {"length_min": length}),
        }
    opens = local_midnight(date.fromisoformat(item.occurrence_date)) + (first - local_midnight(first.date()))
    out = dict(row)
    for key, offset in (("release_utc", "release_offset_min"), ("due_utc", "due_offset_min")):
        if key in times:
            out[offset] = (to_local(parse_utc(times[key]), ctx.tz) - opens) // timedelta(minutes=1)
    return out


def timing_on(ctx: Ctx, row: dict[str, Any], day: str) -> dict[str, str]:
    """The times the series gives its occurrence on a day."""
    first = parse_local(row["dtstart_local"])
    opens = local_midnight(date.fromisoformat(day)) + (first - local_midnight(first.date()))
    return occurrence_timing(as_series(row), opens, ctx.tz)


def series_out(ctx: Ctx, series_id: int) -> SeriesOut:
    row = load_series(ctx, series_id)
    count = one(ctx.conn, "SELECT count(*) AS n FROM items WHERE series_id = ? AND status = 'todo'", [series_id])
    return SeriesOut(
        id=series_id, rule=row["rrule"], description=describe(row["rrule"]), occurrences=int(count["n"]) if count else 0
    )


@command("series_add", affects_plan=True)
def series_add(ctx: Ctx, inp: SeriesAddInput) -> SeriesOut:
    """Start a repeating item."""
    repeat: dict[str, Any] = {
        "every": inp.every,
        "per_window": inp.per_window,
        "release_offset_min": inp.release_offset_min,
        "due_offset_min": inp.due_offset_min,
    }
    if inp.start_date:
        repeat["dtstart_local"] = format_local(
            local_midnight(date.fromisoformat(inp.start_date)) + timedelta(minutes=ctx.day_start)
        )
    series_id, _ = create_series(ctx, all_day_is_free(given_fields(inp)), repeat)
    return series_out(ctx, series_id)


@command("series_edit", affects_plan=True)
def series_edit(ctx: Ctx, inp: SeriesEditInput) -> SeriesOut:
    """Change a series from a date on (today when left out); an imported calendar repeat's tag and kind only."""
    given = given_fields(inp)
    only_tag = set(given) <= OWN_KEYS and inp.every is None and inp.per_window is None
    # A tag, kind, notes or importance isn't about when, so it changes the repeat as it is and its open times, as an
    # imported one's does (3 Nov: from its row in Settings → Repeating, a new tag split "Run" into two rows, one ended
    # and one from today). With a `from_date`, it changes from then on, as before.
    if only_tag and (is_external(ctx, inp.id) or inp.from_date is None):
        return retag_imported(ctx, inp.id, given)
    refuse_external(ctx, inp.id)
    from_date = inp.from_date or ctx.today.isoformat()
    new_id = edit_series_from(ctx, inp.id, from_date, given_fields(inp), inp.every, inp.per_window)
    return series_out(ctx, new_id)


@command("series_spacing", affects_plan=True)
def series_spacing(ctx: Ctx, inp: SeriesSpacingInput) -> SeriesOut:
    """Keep a repeat's times at least so many days apart, from when you did the last one (C50); none to stop."""
    load_series(ctx, inp.id)
    refuse_external(ctx, inp.id)
    if inp.days is not None and not 0 < inp.days <= 366:
        raise FieldError("days", "days apart is more than 0 and at most a year")
    ctx.db.update("series", {"id": inp.id}, {"min_gap_days": inp.days, "updated_utc": ctx.now_text})
    return series_out(ctx, inp.id)


@command("series_stop", affects_plan=True)
def series_stop(ctx: Ctx, inp: SeriesRef) -> SeriesOut:
    """Stop a series; its undone future occurrences go (an imported calendar repeat stops coming in too)."""
    load_series(ctx, inp.id)
    ctx.db.update("series", {"id": inp.id}, {"active": 0, "updated_utc": ctx.now_text})
    remove_future_occurrences(ctx, inp.id, ctx.today)
    return series_out(ctx, inp.id)


@command("series_delete", affects_plan=True)
def series_delete(ctx: Ctx, inp: SeriesRef) -> Changed:
    """Delete a repeat: every undone occurrence goes and what you did stays as history; on a calendar, it goes from
    its first undone time on, every later year or week included. An imported calendar repeat is switched off
    instead, so your calendar doesn't offer it again."""
    found = load_series(ctx, inp.id)
    title = json.loads(found["template"]).get("title", "It")
    if found["external_id"]:
        series_stop(ctx, inp)
        return Changed(message=f"{title} switched off; your calendar won't bring it back")
    remove_future_occurrences(ctx, inp.id, date.min, and_later=True)
    for r in rows(ctx.conn, "SELECT id FROM items WHERE series_id = ?", [inp.id]):
        ctx.db.update("items", {"id": r["id"]}, {"series_id": None, "updated_utc": ctx.now_text})
    ctx.db.delete("series", {"id": inp.id})
    return Changed(message=f"{title} deleted; what you did stays in your history")


@command("skip", affects_plan=True)
def skip(ctx: Ctx, inp: ItemRef) -> ItemResult:
    """Skip one occurrence of a repeating item."""
    item = require_item(ctx, inp.id)
    if item.series_id is None:
        raise FieldError("id", f"T{inp.id} doesn't repeat; drop it instead")
    ctx.db.update("items", {"id": inp.id}, {"status": "skipped", "updated_utc": ctx.now_text})
    queue_event_write(ctx, item, "delete")  # one time of a calendar's repeating event: gone from the calendar too
    return ItemResult(item=item_out(ctx, require_item(ctx, inp.id)))


@command("materialize", affects_plan=True)
def materialize_all(ctx: Ctx, inp: Empty) -> Changed:
    """Create every active series' missing occurrences (the nightly job runs this)."""
    made = sum(
        materialize_series(ctx, r["id"])
        for r in rows(
            ctx.conn, "SELECT id FROM series WHERE user_id = ? AND active = 1 AND external_id IS NULL", [ctx.user_id]
        )
    )
    return Changed(message=f"{made} new occurrences")


@command("series_resume", affects_plan=True)
def series_resume(ctx: Ctx, inp: SeriesRef) -> SeriesOut:
    """Start a stopped series again; its occurrences come back from today (an imported calendar repeat's with the
    next sync, which reads them again)."""
    found = load_series(ctx, inp.id)
    ctx.db.update("series", {"id": inp.id}, {"active": 1, "updated_utc": ctx.now_text})
    if found["external_id"]:
        reread_repeat(ctx, found["external_id"])
    else:
        bring_back_stopped(ctx, inp.id)
        materialize_series(ctx, inp.id)
    return series_out(ctx, inp.id)


def bring_back_stopped(ctx: Ctx, series_id: int) -> None:
    """The times Stop took off a calendar, kept as dropped so its copies stay tied until they're gone, come back on
    Start (8 Nov: they counted as made, and some 17 weeks stayed empty): one whose delete hasn't gone out is simply
    back; one gone from the calendar already is made afresh, and saved there again."""
    for row in rows(
        ctx.conn,
        "SELECT id FROM items WHERE series_id = ? AND status = 'dropped' AND detached = 0 AND occurrence_date >= ?",
        [series_id, ctx.today.isoformat()],
    ):
        pending = rows(
            ctx.conn,
            "SELECT id FROM event_writes WHERE item_id = ? AND op IN ('delete', 'delete_from') AND done_utc IS NULL",
            [row["id"]],
        )
        if pending:
            for write in pending:
                ctx.db.delete("event_writes", {"id": write["id"]})
            ctx.db.update("items", {"id": row["id"]}, {"status": "todo", "updated_utc": ctx.now_text})
        else:
            delete_item(ctx, row["id"])


@query("series_list")
def series_list(ctx: Ctx, inp: Empty) -> list[SeriesRow]:
    """Everything that repeats: what, how often, when next, and where it came from."""
    areas = area_names(ctx.conn, ctx.user_id)
    out = []
    for row in rows(ctx.conn, "SELECT * FROM series WHERE user_id = ? ORDER BY id", [ctx.user_id]):
        template = json.loads(row["template"])
        nxt = one(
            ctx.conn,
            "SELECT id, COALESCE(start_utc, due_utc, release_utc) AS at FROM items WHERE series_id = ? "
            "AND status = 'todo' ORDER BY at LIMIT 1",
            [row["id"]],
        )
        source = one(  # an imported repeat by its event, which stays when its occurrences go
            ctx.conn,
            "SELECT src.name FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
            "JOIN sources src ON src.id = r.source_id LEFT JOIN items i ON i.id = s.item_id "
            "WHERE i.series_id = ? OR s.batch = ? LIMIT 1",
            [row["id"], "repeat:" + (row["external_id"] or "").removeprefix("gcal:")],
        )
        out.append(
            SeriesRow(
                id=row["id"],
                title=template.get("title", ""),
                area=areas.get(template.get("area_id")),
                fixed=template.get("when_kind", template.get("when")) == "fixed",  # `add` keeps it as "when"
                pattern=describe(row["rrule"])
                + (f", {row['per_window']} times" if row["per_window"] > 1 else "")
                + (imported_times(row) if row["external_id"] else ""),
                next=ctx.local(nxt["at"]) if nxt and nxt["at"] else None,
                next_id=nxt["id"] if nxt else None,
                rule=row["rrule"],
                source=source["name"] if source else "you",
                active=bool(row["active"]),
                external=bool(row["external_id"]),
                min_gap_days=row["min_gap_days"],
            )
        )
    return out


DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def attach_to_series(ctx: Ctx, item_id: int, batch: str) -> None:
    """An accepted instance of a repeating calendar event joins the series mirroring it (made with the first one),
    so the event is one repeating item in To-do and Repeating, while its times still come from the calendar."""
    external = "gcal:" + batch.removeprefix("repeat:")
    series = one(ctx.conn, "SELECT id FROM series WHERE user_id = ? AND external_id = ?", [ctx.user_id, external])
    item = ctx.db.fetch("items", {"id": item_id})
    assert item is not None
    series_id = series["id"] if series else mirror(ctx, item, batch, external)
    on = format_local(to_local(parse_utc(item["start_utc"] or item["due_utc"]), ctx.tz))[:10]
    taken = one(
        ctx.conn,
        "SELECT MAX(occurrence_n) AS n FROM items WHERE series_id = ? AND occurrence_date = ?",
        [series_id, on],
    )
    n = (taken["n"] or 0) + 1 if taken else 1
    ctx.db.update("items", {"id": item_id}, {"series_id": series_id, "occurrence_date": on, "occurrence_n": n})


def calendar_rule(ctx: Ctx, batch: str) -> str | None:
    """A repeating calendar event's own RRULE, as Google gave it with its instances."""
    for r in ctx.conn.execute(
        "SELECT r.content FROM suggestions s JOIN raw_inputs r ON r.id = s.raw_input_id "
        "WHERE s.user_id = ? AND s.batch = ? ORDER BY r.id DESC",
        [ctx.user_id, batch],
    ):
        with contextlib.suppress(ValueError):
            if rule := json.loads(r[0]).get("recurrence"):
                return str(rule)
    return None


def weekdays_rule(starts: list[str]) -> str:
    """A weekly rule on the days seen, for a calendar event whose own rule is unknown."""
    days = sorted({date.fromisoformat(s[:10]).weekday() for s in starts if s})
    return "FREQ=WEEKLY;BYDAY=" + ",".join(DAYS[d] for d in days) if days else "FREQ=WEEKLY"


def mirror(ctx: Ctx, item: dict[str, Any], batch: str, external: str, rule: str | None = None) -> int:
    """The series for a calendar event: its first item's fields and the event's repeat (`rule`, when Friday made it
    repeat), for describing."""
    starts = [
        json.loads(r[0]).get("start") or json.loads(r[0]).get("due")
        for r in ctx.conn.execute("SELECT input FROM suggestions WHERE user_id = ? AND batch = ?", [ctx.user_id, batch])
    ]
    template = {k: v for k, v in item.items() if k in TEMPLATE_KEYS and v is not None}
    if item["start_utc"] and item["end_utc"]:  # for saying its times, even once its occurrences are gone
        template["length_min"] = parse_utc(item["end_utc"]) - parse_utc(item["start_utc"])
    first = format_local(to_local(parse_utc(item["start_utc"] or item["due_utc"]), ctx.tz))
    return ctx.db.insert(
        "series",
        {
            "template": json.dumps(template),
            "rrule": rule or calendar_rule(ctx, batch) or weekdays_rule(starts),
            "dtstart_local": first,
            "external_id": external,
            "created_utc": ctx.now_text,
            "updated_utc": ctx.now_text,
        },
    )


TEMPLATE_KEYS = ("title", "preset", "area_id", "when_kind", "event_kind", "blocks_time", "amount", "firmness")


# What Friday keeps about an imported repeat that its calendar doesn't: changing them leaves the mirror intact.
OWN_KEYS = {"area", "tags", "preset", "importance", "notes"}


def retag_imported(ctx: Ctx, series_id: int, given: dict[str, Any]) -> SeriesOut:
    values = to_item_values(ctx, given)
    template = json.loads(load_series(ctx, series_id)["template"]) | values
    ctx.db.update("series", {"id": series_id}, {"template": json.dumps(template), "updated_utc": ctx.now_text})
    for r in rows(ctx.conn, "SELECT id FROM items WHERE series_id = ? AND status = 'todo'", [series_id]):
        before = require_item(ctx, r["id"])
        changes = {k: v for k, v in item_to_row(replace(before, **values)).items() if item_to_row(before).get(k) != v}
        ctx.db.update("items", {"id": r["id"]}, changes | {"updated_utc": ctx.now_text})
    return series_out(ctx, series_id)


def is_external(ctx: Ctx, series_id: int) -> bool:
    found = one(ctx.conn, "SELECT external_id FROM series WHERE user_id = ? AND id = ?", [ctx.user_id, series_id])
    return bool(found and found["external_id"])


def refuse_external(ctx: Ctx, series_id: int) -> None:
    if is_external(ctx, series_id):
        raise FieldError("id", "it repeats in your calendar; change it there, or switch the calendar off")


def reread_repeat(ctx: Ctx, external_id: str) -> None:
    """Mark a calendar repeat's instances unread and sync, so its occurrences come in again."""
    batch = "repeat:" + external_id.removeprefix("gcal:")
    for r in ctx.conn.execute(
        "SELECT DISTINCT raw_input_id FROM suggestions WHERE user_id = ? AND batch = ? AND raw_input_id IS NOT NULL",
        [ctx.user_id, batch],
    ).fetchall():
        ctx.db.update("raw_inputs", {"id": r[0]}, {"content_hash": ""})
    ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": "sync_now"}, {"value": json.dumps(ctx.now_text)})


def imported_fields(ctx: Ctx, batch: str, fields: dict[str, Any]) -> dict[str, Any]:
    """A later instance of an imported repeat gets the tag and kind you picked (its exam prep stays exam prep)."""
    found = one(
        ctx.conn,
        "SELECT template FROM series WHERE user_id = ? AND external_id = ?",
        [ctx.user_id, "gcal:" + batch.removeprefix("repeat:")],
    )
    if found is None:
        return {}
    template = json.loads(found["template"])
    out: dict[str, Any] = {}
    if template.get("area_id") is not None:
        out["area"] = area_names(ctx.conn, ctx.user_id).get(template["area_id"])
    if template.get("preset") and fields.get("preset") != "Exam prep":
        out["preset"] = template["preset"]
    return out


def imported_times(row: dict[str, Any]) -> str:
    """An imported repeat's times, like ", 12:20pm–1:10pm", ", due 11:59pm" or ", all day"; its rule holds only days."""
    start, length = row["dtstart_local"][11:16], json.loads(row["template"]).get("length_min")
    if length is None:
        return f", due {ampm(start)}"
    if length % (24 * 60) == 0 and start == "00:00":
        return ", all day"
    end = (datetime.strptime(start, "%H:%M") + timedelta(minutes=length)).strftime("%H:%M")
    return f", {ampm(start)}–{ampm(end)}"
