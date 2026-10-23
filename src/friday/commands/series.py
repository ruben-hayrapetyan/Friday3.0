"""Repeats (DESIGN §6.3): series_add, series_edit, series_stop, skip, and materializing occurrences."""

import contextlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

from friday.api.commands import (
    Changed,
    Empty,
    ItemRef,
    ItemResult,
    SeriesAddInput,
    SeriesEditInput,
    SeriesOut,
    SeriesRef,
)
from friday.api.views import SeriesRow
from friday.commands.eventwrites import queue_event_write
from friday.commands.fields import given_fields, insert_item, item_out, new_item, require_item, to_item_values
from friday.commands.registry import Ctx, command, query
from friday.core.db import one, rows
from friday.core.items import FieldError, with_defaults
from friday.core.recurrence import describe, ending_before, read_repeat
from friday.core.rows import item_to_row
from friday.core.series import Series, materialize
from friday.core.time import ampm, format_local, local_midnight, parse_local, parse_utc, to_local
from friday.planner.store import area_names

TIME_KEYS = ("start_utc", "end_utc", "release_utc", "due_utc")


def rule_from(ctx: Ctx, every: str) -> str:
    words = every.lower().split()
    found = read_repeat(words[words[:1] == ["every"] :], 0, ctx.today)
    if found is None:
        raise FieldError("every", f"{every!r} isn't a repeat like `mon,wed` or `2w thu`")
    return found[0]


def create_series(ctx: Ctx, given: dict[str, Any], repeat: dict[str, Any]) -> tuple[int, int]:
    """A series from item fields and a repeat (`every` shorthand or a parsed `rrule`); returns its id and count."""
    rule = repeat.get("rrule") or rule_from(ctx, repeat["every"])
    values = to_item_values(ctx, given)
    start = values.get("start_utc")
    if start:
        dtstart = format_local(to_local(parse_utc(start), ctx.tz))
        length = (parse_utc(values["end_utc"]) - parse_utc(start)) if values.get("end_utc") else 60
        values |= {"when": "fixed", "length_min": length}
    else:
        dtstart = repeat.get("dtstart_local") or format_local(
            local_midnight(ctx.today) + timedelta(minutes=ctx.day_start)
        )
    template = template_of(ctx, values)
    series_id = ctx.db.insert(
        "series",
        {
            "template": json.dumps(template),
            "rrule": rule,
            "dtstart_local": dtstart,
            "per_window": repeat.get("per_window") or 1,
            "release_offset_min": repeat.get("release_offset_min"),
            "due_offset_min": repeat.get("due_offset_min"),
            "created_utc": ctx.now_text,
            "updated_utc": ctx.now_text,
        },
    )
    return series_id, materialize_series(ctx, series_id)


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
    """Create the missing occurrences from today to `materialize_days` ahead; returns how many."""
    series = as_series(load_series(ctx, series_id))
    existing = {
        (r["occurrence_date"], r["occurrence_n"])
        for r in rows(ctx.conn, "SELECT occurrence_date, occurrence_n FROM items WHERE series_id = ?", [series_id])
    }
    made = materialize(series, ctx.today, ctx.settings["time"].materialize_days, ctx.tz, existing)
    for item in made:
        insert_item(ctx, with_defaults(item))
    return len(made)


def remove_future_occurrences(ctx: Ctx, series_id: int, from_day: date) -> list[int]:
    """Delete undone, undetached occurrences from `from_day` on; returns the detached ones kept."""
    kept = []
    for row in rows(
        ctx.conn,
        "SELECT id, detached FROM items WHERE series_id = ? AND status = 'todo' AND occurrence_date >= ?",
        [series_id, from_day.isoformat()],
    ):
        if row["detached"]:
            kept.append(row["id"])
        else:
            delete_item(ctx, row["id"])
    return kept


def delete_item(ctx: Ctx, item_id: int) -> None:
    """Delete an item and, first, every row that refers to it, so undo can bring all of them back."""
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
) -> int:
    """End the series the day before `from_date` and start a changed copy on it; returns the new series id."""
    old = load_series(ctx, series_id)
    day = date.fromisoformat(from_date)
    ctx.db.update("series", {"id": series_id}, {"rrule": ending_before(old["rrule"], day), "updated_utc": ctx.now_text})
    remove_future_occurrences(ctx, series_id, day)
    template = json.loads(old["template"]) | without_times(to_item_values(ctx, given))
    start_time = parse_local(old["dtstart_local"]).time()
    new_id = ctx.db.insert(
        "series",
        {
            "template": json.dumps(template),
            "rrule": rule_from(ctx, every) if every else old["rrule"],
            "dtstart_local": format_local(datetime.combine(day, start_time)),
            "per_window": per_window or old["per_window"],
            "release_offset_min": old["release_offset_min"],
            "due_offset_min": old["due_offset_min"],
            "created_utc": ctx.now_text,
            "updated_utc": ctx.now_text,
        },
    )
    materialize_series(ctx, new_id)
    return new_id


def without_times(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if k not in TIME_KEYS}


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
    series_id, _ = create_series(ctx, given_fields(inp), repeat)
    return series_out(ctx, series_id)


@command("series_edit", affects_plan=True)
def series_edit(ctx: Ctx, inp: SeriesEditInput) -> SeriesOut:
    """Change a series from a date on (today when left out); an imported calendar repeat's tag and kind only."""
    given = given_fields(inp)
    if is_external(ctx, inp.id) and set(given) <= OWN_KEYS and inp.every is None and inp.per_window is None:
        return retag_imported(ctx, inp.id, given)
    refuse_external(ctx, inp.id)
    from_date = inp.from_date or ctx.today.isoformat()
    new_id = edit_series_from(ctx, inp.id, from_date, given_fields(inp), inp.every, inp.per_window)
    return series_out(ctx, new_id)


@command("series_stop", affects_plan=True)
def series_stop(ctx: Ctx, inp: SeriesRef) -> SeriesOut:
    """Stop a series; its undone future occurrences go (an imported calendar repeat stops coming in too)."""
    load_series(ctx, inp.id)
    ctx.db.update("series", {"id": inp.id}, {"active": 0, "updated_utc": ctx.now_text})
    remove_future_occurrences(ctx, inp.id, ctx.today)
    return series_out(ctx, inp.id)


@command("series_delete", affects_plan=True)
def series_delete(ctx: Ctx, inp: SeriesRef) -> Changed:
    """Delete a repeat: every undone occurrence goes and what you did stays as history. An imported calendar
    repeat is switched off instead, so your calendar doesn't offer it again."""
    found = load_series(ctx, inp.id)
    title = json.loads(found["template"]).get("title", "It")
    if found["external_id"]:
        series_stop(ctx, inp)
        return Changed(message=f"{title} switched off; your calendar won't bring it back")
    remove_future_occurrences(ctx, inp.id, date.min)
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
        materialize_series(ctx, inp.id)
    return series_out(ctx, inp.id)


@query("series_list")
def series_list(ctx: Ctx, inp: Empty) -> list[SeriesRow]:
    """Everything that repeats: what, how often, when next, and where it came from."""
    areas = area_names(ctx.conn, ctx.user_id)
    out = []
    for row in rows(ctx.conn, "SELECT * FROM series WHERE user_id = ? ORDER BY id", [ctx.user_id]):
        template = json.loads(row["template"])
        nxt = one(
            ctx.conn,
            "SELECT COALESCE(start_utc, due_utc, release_utc) AS at FROM items WHERE series_id = ? AND status = 'todo' "
            "ORDER BY at LIMIT 1",
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
                fixed=template.get("when_kind") == "fixed",
                pattern=describe(row["rrule"])
                + (f", {row['per_window']} times" if row["per_window"] > 1 else "")
                + (imported_times(row) if row["external_id"] else ""),
                next=ctx.local(nxt["at"]) if nxt and nxt["at"] else None,
                source=source["name"] if source else "you",
                active=bool(row["active"]),
                external=bool(row["external_id"]),
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


def mirror(ctx: Ctx, item: dict[str, Any], batch: str, external: str) -> int:
    """The series for a calendar event: its first item's fields and the event's repeat, for describing."""
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
            "rrule": calendar_rule(ctx, batch) or weekdays_rule(starts),
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
