"""Items, dependencies and areas: add, edit, drop, reopen, done, depend, undepend, area_add, area_edit."""

import dataclasses
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
)
from friday.commands.estimates import learned_minutes
from friday.commands.eventwrites import queue_event_write
from friday.commands.fields import (
    check_parent,
    given_fields,
    insert_item,
    item_out,
    new_item,
    preset_name,
    require_item,
    to_item_values,
)
from friday.commands.registry import Ctx, command
from friday.commands.series import create_series, edit_series_from
from friday.commands.timer import stop_timer
from friday.core.db import one, rows
from friday.core.guess import course_of, guess_preset
from friday.core.items import FieldError, Item, amount_units, validate, would_create_cycle
from friday.core.quickadd import parse
from friday.core.rows import item_to_row
from friday.core.textnorm import identity_text, norm
from friday.core.time import UNIT_MIN, to_local
from friday.estimate.durations import Estimate, bias_ratio, estimate_length, history
from friday.planner.progress import actual_minutes, minutes_by_item, progress_rows
from friday.planner.store import area_names

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
    given |= given_fields(inp)
    given = exact_length(ctx, with_guesses(ctx, given))
    after, before = repeat.pop("after", []) + inp.after, repeat.pop("before", []) + inp.before
    if inp.every:
        repeat["every"] = inp.every
    given, repeat = weekly_target(ctx, given, repeat)
    if inp.per_window:
        repeat["per_window"] = inp.per_window
    if "every" in repeat or "rrule" in repeat:
        series_id, made = create_series(ctx, given, repeat)
        return AddOutput(series_id=series_id, occurrences=made, warnings=warnings)
    values = to_item_values(ctx, given)
    values |= estimated_length(ctx, values, given, warnings)
    item = new_item(ctx, values)
    if item.due_utc and item.amount == "fixed" and item.firmness == "none" and "firmness" not in values:
        item.firmness = "hard"  # a due you give is a deadline, even on a kind that usually has none (a form to send)
    check_parent(ctx, None, item.parent_id)
    item_id = insert_item(ctx, item)
    queue_event_write(ctx, require_item(ctx, item_id), "save")
    for other in after:
        add_dependency(ctx, item_id, resolve_ref(ctx, other, warnings), 1.0, 0)
    for other in before:
        add_dependency(ctx, resolve_ref(ctx, other, warnings), item_id, 1.0, 0)
    return AddOutput(item=item_out(ctx, require_item(ctx, item_id)), warnings=warnings)


def with_guesses(ctx: Ctx, given: dict[str, Any]) -> dict[str, Any]:
    """A kind and a course tag read from the title when you gave neither (COMBINED.md 55); events are left alone."""
    title = given.get("title") or ""
    if not title or given.get("when") == "fixed" or given.get("start"):
        return given
    out = dict(given)
    if not out.get("preset"):
        guessed = guess_preset(title, ctx.settings["presets"])
        if guessed:
            out["preset"] = guessed
            if ctx.settings["presets"][guessed].firmness == "hard" and not out.get("due") and not out.get("firmness"):
                out["firmness"] = "none"  # "PS 3" with no due date yet is still a problem set, just not a deadline
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
        ctx.settings["presets"],
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


@command("edit", affects_plan=True)
def edit(ctx: Ctx, inp: EditInput) -> ItemResult:
    """Change an item's fields; `from_date` changes a repeating item's series from that date on."""
    item = require_item(ctx, inp.id)
    given = given_fields(inp)
    if inp.from_date is not None:
        if item.series_id is None:
            raise FieldError("from_date", f"T{item.id} doesn't repeat")
        edit_series_from(ctx, item.series_id, inp.from_date, given)
        return ItemResult(item=item_out(ctx, require_item(ctx, inp.id)))
    changed = dataclasses.replace(item, **to_item_values(ctx, given))
    if changed.series_id is not None:
        changed.detached = True  # regeneration leaves an edited occurrence alone
    if "min_chunk_min" not in given and amount_units(changed) != amount_units(item):
        changed.min_chunk_units = fitted_chunk(ctx, item, changed)
    validate(changed)
    if changed.parent_id != item.parent_id:
        check_parent(ctx, item.id, changed.parent_id)
    update_item(ctx, item, changed)
    queue_event_write(ctx, changed, "save")
    return ItemResult(item=item_out(ctx, changed, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)))


def update_item(ctx: Ctx, before: Item, after: Item) -> None:
    old, new = item_to_row(before), item_to_row(after)
    changes = {k: v for k, v in new.items() if old.get(k) != v}
    if changes:
        ctx.db.update("items", {"id": before.id}, changes | {"updated_utc": ctx.now_text})


def set_status(ctx: Ctx, item_id: int, status: str, completed: str | None = None) -> Item:
    item = require_item(ctx, item_id)
    ctx.db.update("items", {"id": item_id}, {"status": status, "completed_utc": completed, "updated_utc": ctx.now_text})
    return dataclasses.replace(item, status=status, completed_utc=completed)  # type: ignore[arg-type]


@command("drop", affects_plan=True)
def drop(ctx: Ctx, inp: ItemRef) -> ItemResult:
    """Drop an item."""
    dropped = set_status(ctx, inp.id, "dropped")
    queue_event_write(ctx, dropped, "delete")
    return ItemResult(item=item_out(ctx, dropped))


@command("reopen", affects_plan=True)
def reopen(ctx: Ctx, inp: ItemRef) -> ItemResult:
    """Undo a drop or a done."""
    for row in rows(ctx.conn, "SELECT id FROM completions WHERE item_id = ?", [inp.id]):
        ctx.db.delete("completions", {"id": row["id"]})
    done = minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)
    return ItemResult(item=item_out(ctx, set_status(ctx, inp.id, "todo"), done))


@command("done", affects_plan=True)
def done(ctx: Ctx, inp: DoneInput) -> ItemResult:
    """Complete an item, optionally with the time it really took."""
    item = require_item(ctx, inp.id)
    if item.status == "done":
        raise FieldError("id", f"T{inp.id} is already done")
    if ctx.conn.execute("SELECT 1 FROM timer WHERE user_id = ? AND item_id = ?", [ctx.user_id, inp.id]).fetchone():
        stop_timer(ctx)
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
    return ItemResult(item=item_out(ctx, finished, minutes_by_item(ctx.conn, ctx.user_id).get(inp.id, 0)))


@command("depend", affects_plan=True)
def depend(ctx: Ctx, inp: DependInput) -> Changed:
    """B may start once a fraction of A is done, after a lag."""
    add_dependency(ctx, inp.item_id, inp.depends_on_id, inp.fraction, inp.lag_min)
    return Changed(message=f"T{inp.item_id} waits for T{inp.depends_on_id}")


def add_dependency(ctx: Ctx, item_id: int, depends_on_id: int, fraction: float, lag_min: int) -> None:
    item, other = require_item(ctx, item_id), require_item(ctx, depends_on_id)
    if other.amount == "open" and other.when != "fixed":
        raise FieldError("depends_on_id", f"nothing can wait for T{other.id}: an open item never finishes")
    if not 0 < fraction <= 1:
        raise FieldError("fraction", "must be above 0 and at most 1")
    edges: dict[int, list[int]] = {}
    for row in rows(ctx.conn, "SELECT item_id, depends_on_id FROM dependencies WHERE user_id = ?", [ctx.user_id]):
        edges.setdefault(row["item_id"], []).append(row["depends_on_id"])
    if item_id == depends_on_id or would_create_cycle(edges, item_id, depends_on_id):
        raise FieldError("depends_on_id", f"T{item.id} waiting for T{other.id} would make a loop")
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
    if any(name.lower() == inp.name.lower() for name in area_names(ctx.conn, ctx.user_id).values()):
        raise FieldError("name", f"an area called {inp.name} exists")
    area_id = ctx.db.insert("areas", {"name": inp.name, "color": inp.color})
    return AreaOut(id=area_id, name=inp.name, color=inp.color, archived=False)


@command("area_edit", affects_plan=True)
def area_edit(ctx: Ctx, inp: AreaEditInput) -> AreaOut:
    """Rename, recolour or archive an area."""
    found = one(ctx.conn, "SELECT * FROM areas WHERE user_id = ? AND id = ?", [ctx.user_id, inp.id])
    if found is None:
        raise FieldError("id", f"no area {inp.id}")
    changes = {k: v for k, v in {"name": inp.name, "color": inp.color}.items() if v is not None}
    if inp.archived is not None:
        changes["archived"] = int(inp.archived)
    ctx.db.update("areas", {"id": inp.id}, changes)
    after = found | changes
    return AreaOut(id=inp.id, name=after["name"], color=after["color"], archived=bool(after["archived"]))
