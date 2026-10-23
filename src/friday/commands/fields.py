"""API item fields ↔ stored items: local times to UTC, minutes to units, area names to ids, presets applied."""

import math
from typing import Any

from friday.api.types import ItemFields, ItemOut
from friday.commands.eventwrites import writes_to
from friday.commands.registry import Ctx
from friday.core.calendars import category_of, is_filtered, left_out
from friday.core.items import FieldError, Item, apply_preset, validate, with_defaults
from friday.core.rows import item_to_row
from friday.core.textnorm import plain_words
from friday.core.time import UNIT_MIN
from friday.planner.cushion import cushion
from friday.planner.progress import remaining_minutes
from friday.planner.store import EventLink, area_names, event_links, load_item

UNIT_FIELDS = {
    "duration_min": "duration_units",
    "min_min": "min_units",
    "ideal_min": "ideal_units",
    "max_min": "max_units",
    "target_min": "target_units",
    "cap_min": "cap_units",
    "daily_ceiling_min": "daily_ceiling_units",
    "min_chunk_min": "min_chunk_units",
    "max_chunk_min": "max_chunk_units",
}
TIME_FIELDS = {"start": "start_utc", "end": "end_utc", "release": "release_utc", "due": "due_utc"}


def given_fields(fields: ItemFields) -> dict[str, Any]:
    """The item fields a request set (null included, so an edit can clear a due time)."""
    return {k: v for k, v in fields.model_dump(exclude_unset=True).items() if k in ItemFields.model_fields}


def to_item_values(ctx: Ctx, given: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in given.items():
        if name in UNIT_FIELDS:
            out[UNIT_FIELDS[name]] = math.ceil(value / UNIT_MIN) if value is not None else None
        elif name in TIME_FIELDS:
            out[TIME_FIELDS[name]] = ctx.utc(value, name) if value else None
        elif name == "area":
            out["area_id"] = area_id(ctx, value) if value else None
        elif name == "preset":
            out["preset"] = preset_name(ctx, value) if value else None
        else:
            out[name] = value
    return out


def preset_name(ctx: Ctx, typed: str) -> str:
    found = next((name for name in ctx.settings["presets"] if name.lower() == typed.lower().replace("_", " ")), None)
    if found is None:
        raise FieldError("preset", f"no preset named {typed!r}")
    return found


def area_id(ctx: Ctx, name: str) -> int:
    """The area with this name (compared as plain words, so #cs1110 finds CS 1110), created when new."""
    wanted = "".join(plain_words(name))
    for found_id, found_name in area_names(ctx.conn, ctx.user_id).items():
        if "".join(plain_words(found_name)) == wanted:
            return found_id
    return ctx.db.insert("areas", {"name": name})


def inferred_preset(values: dict[str, Any]) -> str:
    if values.get("start_utc"):
        return "Event"
    if values.get("certainty") == "tentative":
        return "Maybe"
    if values.get("amount") == "open":
        return "Side project"
    return "Assignment" if values.get("due_utc") else "Errand"


def new_item(ctx: Ctx, values: dict[str, Any]) -> Item:
    """An item from given values over its preset's defaults, validated."""
    preset = values.get("preset") or inferred_preset(values)
    defaults = ctx.settings["presets"][preset].model_dump(exclude_none=True)
    item = with_defaults(Item(**apply_preset(values | {"preset": preset}, defaults)))
    if item.when == "fixed" and item.event_kind is None:
        item.event_kind = "other"
    validate(item)
    return item


def insert_item(ctx: Ctx, item: Item) -> int:
    row = item_to_row(item) | {"created_utc": ctx.now_text, "updated_utc": ctx.now_text}
    row.pop("id")
    return ctx.db.insert("items", row)


def pointless_late(item: Item, settings: dict[str, Any]) -> bool:
    """Whether work is never planned after its due: your say on the item, else the kinds and titles in settings."""
    if item.when == "fixed" or item.due_utc is None:
        return False
    if item.expires is not None:
        return item.expires
    return bool(settings["pointless_late"].covers(item.preset, item.title))


def item_cushion(ctx: Ctx, item: Item, area: str | None) -> float:
    """The learned cushion on your estimate (COMBINED.md 41), when you gave one."""
    if item.when == "fixed" or item.duration_source != "you":
        return 1.0
    memo = ctx.memo.setdefault("cushions", {})
    return round(cushion(ctx.conn, area, item.preset, ctx.now_utc, ctx.settings, ctx.user_id, memo), 2)


def links(ctx: Ctx) -> dict[int, EventLink]:
    if "event_links" not in ctx.memo:
        ctx.memo["event_links"] = event_links(ctx.conn, ctx.user_id)
    found: dict[int, EventLink] = ctx.memo["event_links"]
    return found


def saves(ctx: Ctx, source_id: int) -> bool:
    key = f"writes_to:{source_id}"
    if key not in ctx.memo:
        ctx.memo[key] = writes_to(ctx.conn, ctx.user_id, source_id)
    return bool(ctx.memo[key])


def event_facts(ctx: Ctx, item: Item) -> dict[str, Any]:
    """An event's calendar, category and whether it counts as busy (COMBINED.md 17, 28)."""
    if item.when != "fixed":
        return {}
    link = links(ctx).get(item.id or 0)
    calendar = link.calendar if link else None
    category = category_of(item.title, ctx.settings["categories"])
    reason = left_out(item.title, calendar, item.free, ctx.settings["categories"], ctx.settings["busy"])
    return {
        "calendar": calendar,
        "calendar_color": ctx.settings["calendar_look"].colors.get(calendar) if calendar else None,
        "saves_to_calendar": bool(link) and saves(ctx, link.source_id),
        "category": category.name if category else None,
        "category_color": category.color if category else None,
        "left_out": reason,
        "filtered": is_filtered(item.title, ctx.settings["categories"]),
    }


def item_out(ctx: Ctx, item: Item, done_minutes: int = 0) -> ItemOut:
    area = area_names(ctx.conn, ctx.user_id).get(item.area_id) if item.area_id else None
    return ItemOut(
        id=item.id or 0,
        title=item.title,
        preset=item.preset,
        area=area,
        tags=item.tags,
        parent_id=item.parent_id,
        when=item.when,
        start=ctx.local(item.start_utc),
        end=ctx.local(item.end_utc),
        release=ctx.local(item.release_utc),
        due=ctx.local(item.due_utc),
        amount=item.amount,
        duration_min=item.duration_units * UNIT_MIN if item.duration_units is not None else None,
        firmness=item.firmness,
        importance=item.importance,
        energy=item.energy,
        shape=item.shape,
        color=item.color,
        notes=item.notes,
        long_term=item.long_term,
        expires=item.expires,
        pointless_late=pointless_late(item, ctx.settings),
        cushion=item_cushion(ctx, item, area),
        certainty=item.certainty,
        event_kind=item.event_kind,
        status=item.status,
        series_id=item.series_id,
        done_min=done_minutes,
        remaining_min=remaining_minutes(item, done_minutes) if item.when != "fixed" else None,
        estimate=item.estimate_detail,
        **event_facts(ctx, item),
    )


def check_parent(ctx: Ctx, item_id: int | None, parent_id: int | None) -> None:
    """A parent exists, isn't fixed, and isn't the item or one of its descendants (§6.5)."""
    seen = set()
    at = parent_id
    while at is not None and at not in seen:
        if at == item_id:
            raise FieldError("parent_id", f"T{item_id} can't be inside itself")
        parent = load_item(ctx.conn, at, ctx.user_id)
        if parent is None:
            raise FieldError("parent_id", f"no item T{at}")
        if at == parent_id and parent.when == "fixed":
            raise FieldError("parent_id", f"T{at} is at a set time, so it can't hold other items")
        seen.add(at)
        at = parent.parent_id


def require_item(ctx: Ctx, item_id: int) -> Item:
    item = load_item(ctx.conn, item_id, ctx.user_id)
    if item is None:
        raise FieldError("id", f"no item T{item_id}")
    return item
