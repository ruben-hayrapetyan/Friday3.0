"""Items, dependencies and areas: add, edit, drop, reopen, done, depend, undepend, area_add, area_edit."""

import dataclasses
import json
import math
from typing import Any

from friday.api.commands import (
    AddInput,
    AddOutput,
    AreaEditInput,
    AreaInput,
    AreaOut,
    Changed,
    DependInput,
    DoneInput,
    EditInput,
    ItemRef,
    ItemResult,
    OccurrenceChange,
)
from friday.commands.estimates import learned_minutes
from friday.commands.eventwrites import put_back, queue_event_write
from friday.commands.fields import (
    all_day_is_free,
    check_parent,
    given_fields,
    insert_item,
    item_out,
    new_item,
    preset_name,
    require_item,
    to_item_values,
    update_item,
)
from friday.commands.registry import Ctx, command
from friday.commands.series import (
    TIME_KEYS,
    calendar_of,
    create_series,
    load_series,
    refuse_external,
    retimed,
    timing_on,
    without_times,
)
from friday.commands.series_days import move_from, moves_day
from friday.commands.settings import write_setting
from friday.commands.timer import stop_timer
from friday.core.db import one, rows
from friday.core.guess import course_of, fallback_kind, guess_preset
from friday.core.items import FieldError, Item, amount_units, validate, would_create_cycle
from friday.core.presets import in_use
from friday.core.quickadd import parse
from friday.core.textnorm import identity_text, norm, plain_words
from friday.core.time import UNIT_MIN, to_local
from friday.estimate.durations import Estimate, bias_ratio, estimate_length, history
from friday.planner.progress import actual_minutes, minutes_by_item, progress_rows
from friday.planner.store import area_names, kv_get

PARSED_TIMES = {"start_local": "start", "end_local": "end", "release_local": "release", "due_local": "due"}
PARSED_UNITS = {
    "duration_units": "duration_min",
    "min_units": "min_min",
    "ideal_units": "ideal_min",
    "max_units": "max_min",
}


@command("add", affects_plan=True)
def add(ctx: Ctx, inp: AddInput) -> AddOutput:
    """Create an item from fields or from a quick-add line."""
    given, warnings, repeat = from_text(ctx, inp.text) if inp.text else ({}, [], {})
    given = all_day_is_free(given | given_fields(inp))
    if not str(given.get("title") or "").strip():  # nothing said at all was a crash, not a word (audit, 8 Nov)
        raise FieldError("title", "give it a title: what is it?")
    given = exact_length(ctx, with_guesses(ctx, given))
    after, before = repeat.pop("after", []) + inp.after, repeat.pop("before", []) + inp.before
    if inp.every:  # the picker's repeat over one typed in the text ("Run every tue" with Every day chosen)
        repeat["every"] = inp.every
        repeat.pop("rrule", None)
    given, repeat = weekly_target(ctx, given, repeat)
    if inp.per_window:
        repeat["per_window"] = inp.per_window
    if inp.exceptions and not ("every" in repeat or "rrule" in repeat):
        raise FieldError("exceptions", "only a repeat has times that differ")
    if "every" in repeat or "rrule" in repeat:
        series_id, made = create_series(ctx, given, repeat, calendar=inp.calendar)
        warnings += [said for change in inp.exceptions if (said := excepted(ctx, series_id, change))]
        return AddOutput(series_id=series_id, occurrences=made, warnings=warnings)
    values = to_item_values(ctx, given)
    values |= estimated_length(ctx, values, given, warnings)
    item = due_is_a_deadline(new_item(ctx, values), values)
    check_parent(ctx, None, item.parent_id)
    item_id = insert_item(ctx, item)
    if inp.calendar == "" and item.when == "fixed":  # kept only in Friday, even after a default calendar is chosen
        mine = kv_get(ctx.conn, "friday_only_events", [], ctx.user_id) or []
        ctx.db.upsert(
            "kv", {"user_id": ctx.user_id, "key": "friday_only_events"}, {"value": json.dumps([*mine, item_id])}
        )
    queue_event_write(ctx, require_item(ctx, item_id), "save", target=inp.calendar)
    for other in after:
        add_dependency(ctx, item_id, resolve_ref(ctx, other, warnings), 1.0, 0)
    for other in before:
        add_dependency(ctx, resolve_ref(ctx, other, warnings), item_id, 1.0, 0)
    return AddOutput(item=item_out(ctx, require_item(ctx, item_id)), warnings=warnings)


def excepted(ctx: Ctx, series_id: int, change: OccurrenceChange) -> str | None:
    """One time of a new repeat made different: skipped, or its own place, times or title (an edit of that occurrence
    alone, as any). What couldn't be done, said back; nothing when it was."""
    found = one(
        ctx.conn,
        "SELECT id FROM items WHERE series_id = ? AND occurrence_date = ? AND status = 'todo'",
        [series_id, change.date],
    )
    if found is None:
        return f"It doesn't happen on {change.date}, so nothing changed that day"
    if change.skip:
        ctx.db.update("items", {"id": found["id"]}, {"status": "skipped", "updated_utc": ctx.now_text})
        return None
    fields = change.model_dump(exclude={"date", "skip"}, exclude_none=True)
    if fields:
        edit(ctx, EditInput(id=found["id"], **fields))
    return None


def with_guesses(ctx: Ctx, given: dict[str, Any]) -> dict[str, Any]:
    """A kind and a course tag read from the title when you gave neither (COMBINED.md 55); events are left alone."""
    title = given.get("title") or ""
    if not title or given.get("when") == "fixed" or given.get("start"):
        return given
    out = dict(given)
    if not out.get("preset"):
        guessed = guess_preset(title, in_use(ctx.settings["presets"], ctx.settings["school"]))
        if guessed:
            out["preset"] = guessed
    # "PS 3" with no due date yet is still a problem set, just not a deadline: guessed, or the kind of the section it
    # was added in (28 Oct: an assignment added with no due date was refused, "a hard deadline needs a due time").
    kind = ctx.settings["presets"].get(out.get("preset") or "")
    if kind is not None and kind.firmness == "hard" and not out.get("due") and not out.get("firmness"):
        out["firmness"] = "none"
    if not out.get("area"):
        course = course_of(title)
        if course:
            out["area"] = course
    return out


def exact_length(ctx: Ctx, given: dict[str, Any]) -> dict[str, Any]:
    """One length for a kind that stretches ("lunch every day 15m", where Routine is 30–45 minutes) is exactly that
    long, not the kind's usual range."""
    preset = ctx.settings["presets"].get(preset_name(ctx, given["preset"])) if given.get("preset") else None
    amount = given.get("amount", preset.amount if preset else None)
    length = given.get("duration_min")
    if amount != "elastic" or not length or any(k in given for k in ("min_min", "ideal_min", "max_min")):
        return given
    rest = {k: v for k, v in given.items() if k != "duration_min"}
    return rest | {"amount": "elastic", "min_min": length, "ideal_min": length, "max_min": length}


def weekly_target(ctx: Ctx, given: dict[str, Any], repeat: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """A target with no window ("MCAT practice /goal ~6h") is that much every week, its length the target."""
    preset = ctx.settings["presets"].get(preset_name(ctx, given["preset"])) if given.get("preset") else None
    target = given.get("amount", preset.amount if preset else None) == "target"
    if not target or given.get("due") or "every" in repeat or "rrule" in repeat:
        return given, repeat
    if given.get("duration_min") and not given.get("target_min"):
        given = {k: v for k, v in given.items() if k != "duration_min"} | {"target_min": given["duration_min"]}
    return given, repeat | {"every": "week"}


def from_text(ctx: Ctx, text: str) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """Quick-add fields in API form, the parser's warnings, and the repeat and dependency parts."""
    now_local = to_local(ctx.now_utc, ctx.tz)
    result = parse(
        text,
        now_local,
        ctx.day_start,
        area_names(ctx.conn, ctx.user_id).values(),
        in_use(ctx.settings["presets"], ctx.settings["school"]),
        lambda title: find_item(ctx, title),
    )
    fields = dict(result.fields)
    repeat = {k: fields.pop(k) for k in ("rrule", "per_window", "dtstart_local", "after", "before") if k in fields}
    given: dict[str, Any] = {}
    for name, value in fields.items():
        if name in PARSED_TIMES:
            given[PARSED_TIMES[name]] = value
        elif name in PARSED_UNITS:
            given[PARSED_UNITS[name]] = value * UNIT_MIN
        else:
            given[name] = value
    if "start" in given:
        given["when"] = "fixed"
    return given, list(result.warnings), repeat


def find_item(ctx: Ctx, title: str) -> int | None:
    wanted = identity_text(norm(title, ctx.settings["text"].rules()))
    for row in rows(
        ctx.conn, "SELECT id, title FROM items WHERE user_id = ? AND status = 'todo' ORDER BY id DESC", [ctx.user_id]
    ):
        if identity_text(norm(row["title"], ctx.settings["text"].rules())) == wanted:
            return int(row["id"])
    return None


def resolve_ref(ctx: Ctx, ref: int | str, warnings: list[str]) -> int:
    if isinstance(ref, int):
        return ref
    found = find_item(ctx, ref)
    if found is None:
        raise FieldError("after", f"no item called {ref!r}")
    return found


def estimated_length(ctx: Ctx, values: dict[str, Any], given: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Friday's estimate for every new fixed-amount flexible item; it sets the length only when none was given."""
    if values.get("start_utc") or values.get("amount", "fixed") != "fixed":
        return {}
    settings = ctx.settings["estimate"]
    area = area_names(ctx.conn, ctx.user_id).get(values.get("area_id")) if values.get("area_id") else None
    past = history(ctx.conn, area, values.get("preset"), ctx.now_utc, settings.window_days, ctx.user_id)
    estimate = learned_estimate(ctx, values, area) or estimate_length(
        values.get("title", ""), area, past, settings, ctx.settings["text"].rules()
    )
    out: dict[str, Any] = {}
    if estimate is not None:
        out = {
            "friday_estimate_units": estimate.units,
            "estimate_detail": {"method": estimate.method, **estimate.detail},
        }
    if "duration_min" in given:
        out |= {"duration_source": "you", "your_estimate_units": values["duration_units"]}
        ratio = bias_ratio(past, settings)
        if ratio is not None:
            suggested = math.ceil(values["duration_units"] * ratio) * UNIT_MIN
            where = f" for {area}" if area else ""
            warnings.append(f"your estimates{where} run ×{ratio:.2f}: maybe {suggested} min")
    elif estimate is not None:
        out |= {"duration_units": estimate.units, "duration_source": "estimate"}
    else:
        out |= {"duration_source": "preset"}
    return out


def guessed_minutes(ctx: Ctx, fields: dict[str, Any]) -> int | None:
    """The length Friday would give a suggested task that has none, made the way `add` makes it but without adding
    anything (no new tag): the Inbox shows it ("1h 30m, Friday's guess") so it isn't accepted unseen."""
    if fields.get("duration_min") or fields.get("start") or fields.get("when") == "fixed":
        return None
    given = with_guesses(ctx, {k: fields[k] for k in ("title", "preset", "area", "due") if fields.get(k)})
    presets = ctx.settings["presets"]
    title = str(given.get("title") or "")
    typed = str(given.get("preset") or fallback_kind(title, bool(given.get("due")), presets, ctx.settings["school"]))
    preset = next((p for p in presets if p.lower() == typed.lower().replace("_", " ")), None)
    kind = presets.get(preset) if preset else None
    if kind is None or (kind.amount or "fixed") != "fixed":
        return None
    wanted = "".join(plain_words(str(given.get("area") or "")))
    area = next((n for n in area_names(ctx.conn, ctx.user_id).values() if "".join(plain_words(n)) == wanted), None)
    settings = ctx.settings["estimate"]
    past = history(ctx.conn, area, preset, ctx.now_utc, settings.window_days, ctx.user_id)
    title = str(given.get("title") or "")
    estimate = learned_estimate(ctx, {"title": title, "preset": preset}, area) or estimate_length(
        title, area, past, settings, ctx.settings["text"].rules()
    )
    units = estimate.units if estimate is not None else kind.duration_units
    return units * UNIT_MIN if units else None


def learned_estimate(ctx: Ctx, values: dict[str, Any], area: str | None) -> Estimate | None:
    """Learned durations, when in use (§21.7): the cautious p80 for hard-deadline work, else p50."""
    preset = values.get("preset")
    firmness = values.get("firmness") or (
        ctx.settings["presets"][preset].firmness if preset in ctx.settings["presets"] else None
    )
    found = learned_minutes(ctx, values.get("title", ""), area, preset, firmness == "hard")
    if found is None:
        return None
    minutes, detail = found
    return Estimate(max(1, -(-minutes // UNIT_MIN)), "learned", detail)


def fitted_chunk(ctx: Ctx, before: Item, after: Item) -> int:
    """The smallest piece after a new length: a 15-minute assignment is done in one go, as when it's added; made
    longer again, it's back to its kind's smallest piece rather than split into 15-minute bits."""
    kind = ctx.settings["presets"].get(after.preset) if after.preset else None
    usual = max(before.min_chunk_units, kind.min_chunk_units if kind and kind.min_chunk_units else 1)
    amount = amount_units(after)
    return min(usual, amount) if amount else usual


def due_is_a_deadline(item: Item, values: dict[str, Any]) -> Item:
    """A due you give is a deadline: on a kind that usually has none (a form to send), and on one that had no due
    yet ("PS 3" added before its date was out, or brought over from your to-do list without one, then given one).
    Edited in, it had stayed "none", and Friday planned CS A4 as if it could wait forever."""
    if item.due_utc and item.amount == "fixed" and item.firmness == "none" and "firmness" not in values:
        return dataclasses.replace(item, firmness="hard")
    return item


@command("edit", affects_plan=True)
def edit(ctx: Ctx, inp: EditInput) -> ItemResult:
    """Change an item's fields; `from_date` changes a repeating item's series from that date on."""
    item = require_item(ctx, inp.id)
    given = given_fields(inp)
    if inp.from_date is not None:
        if item.series_id is None:
            raise FieldError("from_date", f"T{item.id} doesn't repeat")
        return edit_from(ctx, item, inp.from_date, given)
    values = to_item_values(ctx, given)
    if "duration_min" in given and values.get("duration_units"):  # your new length is your estimate now (audit, 8 Nov:
        # an essay cut from 4 h to 1 h still had 8 h planned, the old estimate times the cushion)
        values |= {"duration_source": "you", "your_estimate_units": values["duration_units"]}
    changed = dataclasses.replace(item, **values)
    if "preset" in values and changed.when == "fixed" and "event_kind" not in values:
        # an event made a Class or an Exam keeps a class's or an exam's time around it (audit, 8 Nov)
        kind = ctx.settings["presets"].get(changed.preset or "")
        changed = dataclasses.replace(changed, event_kind=(kind.event_kind if kind else None) or "other")
    if "due_utc" in values and values["due_utc"] is None:
        if changed.firmness == "hard" and "firmness" not in values:  # "No due date": no deadline either (audit)
            changed = dataclasses.replace(changed, firmness="none")
    elif "due_utc" in values:
        changed = due_is_a_deadline(changed, values)
    if changed.series_id is not None:
        changed.detached = True  # regeneration leaves an edited occurrence alone
    if "min_chunk_min" not in given and amount_units(changed) != amount_units(item):
        changed.min_chunk_units = fitted_chunk(ctx, item, changed)
    validate(changed)
    if changed.parent_id != item.parent_id:
        check_parent(ctx, item.id, changed.parent_id)
    update_item(ctx, item, changed)
    # one time of a repeat goes where its repeat goes ("Only Friday" stays in Friday; 8 Nov it went to Google)
    queue_event_write(ctx, changed, "save", target=calendar_of(ctx, changed.series_id) if changed.series_id else None)
    return ItemResult(item=item_out(ctx, changed, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)))


def edit_from(ctx: Ctx, item: Item, from_date: str, given: dict[str, Any]) -> ItemResult:
    """This occurrence and the later ones changed where they are, and the series' template for those not made yet.
    Each keeps its id and the work recorded on it: remaking them lost both, and failed on the one being edited. New
    times are this one's, and the series' from then on, so each later one moves to them on its own day."""
    assert item.series_id is not None
    refuse_external(ctx, item.series_id)  # a calendar's own repeat changes there (review, 8 Nov)
    values = to_item_values(ctx, given)
    times = {k: v for k, v in values.items() if k in TIME_KEYS}
    values = without_times(values)
    series = load_series(ctx, item.series_id)
    if times and item.occurrence_date and moves_day(ctx, item, times):
        return ItemResult(
            item=item_out(
                ctx, move_from(ctx, item, times, values), minutes_by_item(ctx.conn, ctx.user_id).get(item.id, 0)
            )
        )
    if times and item.occurrence_date:
        series = retimed(ctx, series, item, times)
    template = json.loads(series["template"]) | values
    series["template"] = json.dumps(template)
    kept = ("template", "dtstart_local", "release_offset_min", "due_offset_min")
    ctx.db.update("series", {"id": item.series_id}, {k: series[k] for k in kept} | {"updated_utc": ctx.now_text})
    for row in rows(
        ctx.conn,
        "SELECT id, occurrence_date FROM items WHERE series_id = ? AND status = 'todo' AND (detached = 0 OR id = ?) "
        "AND occurrence_date >= ?",
        [item.series_id, item.id, from_date],
    ):
        before = require_item(ctx, row["id"])
        moved = timing_on(ctx, series, row["occurrence_date"]) if row["id"] != item.id else times
        after = dataclasses.replace(before, **values, **{k: v for k, v in moved.items() if k in times})
        if "min_chunk_min" not in given and amount_units(after) != amount_units(before):
            after.min_chunk_units = fitted_chunk(ctx, before, after)
        validate(after)
        update_item(ctx, before, after)
        # On its calendar too: each time is its own event there (series.materialize_series).
        queue_event_write(ctx, after, "save", target=calendar_of(ctx, item.series_id))
    return ItemResult(
        item=item_out(ctx, require_item(ctx, item.id), minutes_by_item(ctx.conn, ctx.user_id).get(item.id, 0))
    )


def set_status(ctx: Ctx, item_id: int, status: str, completed: str | None = None) -> Item:
    item = require_item(ctx, item_id)
    ctx.db.update("items", {"id": item_id}, {"status": status, "completed_utc": completed, "updated_utc": ctx.now_text})
    return dataclasses.replace(item, status=status, completed_utc=completed)  # type: ignore[arg-type]


@command("drop", affects_plan=True)
def drop(ctx: Ctx, inp: ItemRef) -> ItemResult:
    """Drop an item; a timer on it stops (its time kept), and any other goes on."""
    if ctx.conn.execute("SELECT 1 FROM timer WHERE user_id = ? AND item_id = ?", [ctx.user_id, inp.id]).fetchone():
        stop_timer(ctx, item_id=inp.id)
    dropped = set_status(ctx, inp.id, "dropped")
    queue_event_write(ctx, dropped, "delete")
    return ItemResult(item=item_out(ctx, dropped))


@command("reopen", affects_plan=True)
def reopen(ctx: Ctx, inp: ItemRef) -> ItemResult:
    """Undo a drop or a done."""
    for row in rows(ctx.conn, "SELECT id FROM completions WHERE item_id = ?", [inp.id]):
        ctx.db.delete("completions", {"id": row["id"]})
    done = minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)
    opened = set_status(ctx, inp.id, "todo")
    put_back(ctx, inp.id)  # dropped, and gone from its calendar: back there too
    back_to_its_app(ctx, inp.id, "reopen")
    return ItemResult(item=item_out(ctx, opened, done))


@command("done", affects_plan=True)
def done(ctx: Ctx, inp: DoneInput) -> ItemResult:
    """Complete an item, optionally with the time it really took."""
    item = require_item(ctx, inp.id)
    if item.status == "done":
        raise FieldError("id", "That's done already")
    if item.status == "dropped":  # audit, 8 Nov: a dropped one was marked done, and counted as finished work
        raise FieldError("id", "That one was dropped: open it again first if you did it after all")
    if inp.actual_min is not None and inp.actual_min < 0:  # it taught Friday a negative length (audit, 12 Nov)
        raise FieldError("actual_min", "the time it took can't be less than nothing")
    if ctx.conn.execute("SELECT 1 FROM timer WHERE user_id = ? AND item_id = ?", [ctx.user_id, inp.id]).fetchone():
        stop_timer(ctx, item_id=inp.id)  # its own: another may be running alongside
    progress = progress_rows(ctx.conn, ctx.user_id).get(inp.id, [])
    planned = (amount_units(item) or 0) * UNIT_MIN
    actual, source = (inp.actual_min, "retro") if inp.actual_min is not None else actual_minutes(progress, planned)
    area = area_names(ctx.conn, ctx.user_id).get(item.area_id) if item.area_id else None
    ctx.db.insert(
        "completions",
        {
            "item_id": inp.id,
            "area": area,
            "preset": item.preset,
            "norm_title": identity_text(norm(item.title, ctx.settings["text"].rules(), area)),
            "your_estimate_units": item.your_estimate_units,
            "friday_estimate_units": item.friday_estimate_units,
            "actual_minutes": actual,
            "actual_source": source,
            "completed_utc": ctx.now_text,
        },
    )
    finished = set_status(ctx, inp.id, "done", ctx.now_text)
    back_to_its_app(ctx, inp.id, "done")
    return ItemResult(item=item_out(ctx, finished, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)))


def back_to_its_app(ctx: Ctx, item_id: int, op: str) -> None:
    """Done or opened again here: the same in the to-do app it came from (C96), in this command's transaction."""
    from friday.integrations.sync import queue_write  # the sync runs commands: imported here, not at the top

    queue_write(ctx.conn, item_id, op, ctx.actor, ctx.now_utc, ctx.user_id)


@command("depend", affects_plan=True)
def depend(ctx: Ctx, inp: DependInput) -> Changed:
    """B may start once a fraction of A is done, after a lag."""
    add_dependency(ctx, inp.item_id, inp.depends_on_id, inp.fraction, inp.lag_min)
    return Changed(message=f"T{inp.item_id} waits for T{inp.depends_on_id}")


def add_dependency(ctx: Ctx, item_id: int, depends_on_id: int, fraction: float, lag_min: int) -> None:
    item, other = require_item(ctx, item_id), require_item(ctx, depends_on_id)
    if other.amount == "open" and other.when != "fixed":
        endless = "it's open-ended, so it never finishes"
        raise FieldError("depends_on_id", f"Nothing can wait for “{other.title}”: {endless}")
    if not 0 < fraction <= 1:
        raise FieldError("fraction", "must be above 0 and at most 1")
    edges: dict[int, list[int]] = {}
    for row in rows(ctx.conn, "SELECT item_id, depends_on_id FROM dependencies WHERE user_id = ?", [ctx.user_id]):
        edges.setdefault(row["item_id"], []).append(row["depends_on_id"])
    if item_id == depends_on_id or would_create_cycle(edges, item_id, depends_on_id):
        raise FieldError(
            "depends_on_id",
            (
                f"“{item.title}” can't wait for itself"
                if item.id == other.id
                else f"“{item.title}” can't wait for “{other.title}”: that one already waits for it, a loop"
            ),
        )
    found = one(
        ctx.conn,
        "SELECT id FROM dependencies WHERE user_id = ? AND item_id = ? AND depends_on_id = ?",
        [ctx.user_id, item_id, depends_on_id],
    )
    if found is not None:  # it already waits: the new fraction and lag replace the old
        ctx.db.update("dependencies", {"id": found["id"]}, {"fraction": fraction, "lag_min": lag_min})
        return
    ctx.db.insert(
        "dependencies", {"item_id": item_id, "depends_on_id": depends_on_id, "fraction": fraction, "lag_min": lag_min}
    )


@command("undepend", affects_plan=True)
def undepend(ctx: Ctx, inp: DependInput) -> Changed:
    """Remove a dependency."""
    found = one(
        ctx.conn,
        "SELECT id FROM dependencies WHERE user_id = ? AND item_id = ? AND depends_on_id = ?",
        [ctx.user_id, inp.item_id, inp.depends_on_id],
    )
    if found is None:
        raise FieldError("depends_on_id", f"T{inp.item_id} doesn't wait for T{inp.depends_on_id}")
    ctx.db.delete("dependencies", {"id": found["id"]})
    return Changed(message=f"T{inp.item_id} no longer waits for T{inp.depends_on_id}")


@command("area_add")
def area_add(ctx: Ctx, inp: AreaInput) -> AreaOut:
    """Add an area."""
    if not inp.name.strip():
        raise FieldError("name", "give the tag a name")
    if any(name.lower() == inp.name.lower() for name in area_names(ctx.conn, ctx.user_id).values()):
        raise FieldError("name", f"an area called {inp.name} exists")
    area_id = ctx.db.insert("areas", {"name": inp.name, "color": inp.color})
    return AreaOut(id=area_id, name=inp.name, color=inp.color, archived=False)


def follow_rename(ctx: Ctx, old: str, new: str) -> None:
    """The rules that name a tag follow it to its new name: a buffer by tag and a rule about a tag's work named it by
    its old one, so they stopped reaching anything (audit, 12 Nov)."""
    rules = [r.model_dump() for r in ctx.settings["rules"]]
    moved = False
    for r in rules:
        by_area = (r.get("params") or {}).get("by_area")
        if isinstance(by_area, dict) and old in by_area:
            r["params"]["by_area"] = {new if k == old else k: v for k, v in by_area.items()}
            moved = True
        area = (r.get("scope") or {}).get("area")
        if area == old:
            r["scope"]["area"] = new
            moved = True
        elif isinstance(area, list) and old in area:
            r["scope"]["area"] = [new if a == old else a for a in area]
            moved = True
    if moved:
        write_setting(ctx, "rules", rules)


@command("area_edit", affects_plan=True)
def area_edit(ctx: Ctx, inp: AreaEditInput) -> AreaOut:
    """Rename, recolour or archive an area."""
    found = one(ctx.conn, "SELECT * FROM areas WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None:
        raise FieldError("id", f"no area {inp.id}")
    if inp.name is not None:  # renamed to one you have was a database error (audit, 12 Nov)
        if not inp.name.strip():
            raise FieldError("name", "give the tag a name")
        others = [n for i, n in area_names(ctx.conn, ctx.user_id).items() if i != inp.id]
        if any(n.lower() == inp.name.lower() for n in others):
            raise FieldError("name", f"an area called {inp.name} exists")
    changes = {k: v for k, v in {"name": inp.name, "color": inp.color}.items() if v is not None}
    if inp.archived is not None:
        changes["archived"] = int(inp.archived)
    ctx.db.update("areas", {"id": inp.id}, changes)
    if inp.name is not None and inp.name != found["name"]:
        follow_rename(ctx, found["name"], inp.name)
    after = found | changes
    return AreaOut(id=inp.id, name=after["name"], color=after["color"], archived=bool(after["archived"]))
