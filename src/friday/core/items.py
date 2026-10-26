"""Items: facets, presets and validation (DESIGN §6). Pure types, no I/O."""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from typing import Any, Literal

When = Literal["fixed", "window", "anytime"]
Amount = Literal["fixed", "elastic", "target", "open"]
Shape = Literal["one_sitting", "split"]
Spread = Literal["none", "spread", "cluster"]
Firmness = Literal["hard", "soft", "none"]
Energy = Literal["deep", "light", "physical", "social"]
Certainty = Literal["planned", "tentative"]
Status = Literal["todo", "done", "dropped", "skipped"]
DurationSource = Literal["you", "estimate", "preset"]

# personal's pigments (UI/Sources/Calendar/EventColors.swift), by id: Vermilion, Amber, Ochre, Verdigris, Sap Green,
# Cerulean, Ultramarine, Magenta, Payne's Grey, Cobalt Violet. The web app holds their colours.
PIGMENTS = ("red", "orange", "yellow", "green", "sapgreen", "blue", "purple", "pink", "graphite", "violet")

DEFAULT_DAILY_CEILING_UNITS = 4  # an hour a day: at 3 h, a book or Leetcode took every free afternoon (M15)


class FieldError(ValueError):
    def __init__(self, field_name: str, message: str):
        super().__init__(f"{field_name}: {message}")
        self.field = field_name


@dataclass
class Item:
    title: str
    id: int | None = None
    notes: str = ""
    preset: str | None = None
    area_id: int | None = None
    tags: list[str] = field(default_factory=list)
    parent_id: int | None = None
    when: When = "window"
    start_utc: str | None = None
    end_utc: str | None = None
    release_utc: str | None = None
    due_utc: str | None = None
    amount: Amount = "fixed"
    duration_units: int | None = None
    min_units: int | None = None
    ideal_units: int | None = None
    max_units: int | None = None
    target_units: int | None = None
    cap_units: int | None = None
    daily_ceiling_units: int | None = None
    shape: Shape = "split"
    min_chunk_units: int = 2
    max_chunk_units: int | None = None
    chunk_cost: float = 0.0
    spread: Spread = "none"
    firmness: Firmness = "none"
    importance: int = 3
    neglect_carry: float = 0.5
    energy: Energy | None = None
    location: str | None = None
    color: str | None = None  # an event's pigment (COMBINED.md 17): one of PIGMENTS, or None for its calendar's
    certainty: Certainty = "planned"
    event_kind: str | None = None
    blocks_time: bool = True
    free: bool = False  # marked free in its calendar: kept, but not busy unless you count free events
    long_term: bool = False  # on the long-term list (personal's), not the short-term one
    background: bool = False  # runs by itself once started (laundry): only its first quarter hour needs you
    expires: bool | None = None  # pointless once late: never planned after its due; None follows `pointless_late`
    buffer_before_min: int | None = None
    buffer_after_min: int | None = None
    status: Status = "todo"
    series_id: int | None = None
    occurrence_date: str | None = None
    occurrence_n: int | None = None
    detached: bool = False
    duration_source: DurationSource | None = None
    your_estimate_units: int | None = None
    friday_estimate_units: int | None = None
    estimate_detail: dict[str, Any] | None = None
    created_utc: str | None = None
    updated_utc: str | None = None
    completed_utc: str | None = None


ITEM_FIELDS = frozenset(f.name for f in fields(Item))


def apply_preset(given: Mapping[str, Any], preset: Mapping[str, Any]) -> dict[str, Any]:
    """Preset defaults under the fields you gave; preset keys that aren't item fields (pacing) are dropped."""
    return {k: v for k, v in preset.items() if k in ITEM_FIELDS} | dict(given)


def with_defaults(item: Item) -> Item:
    if item.amount == "target" and item.target_units is not None and item.cap_units is None:
        item.cap_units = math.ceil(1.5 * item.target_units)
    if item.amount == "open" and item.daily_ceiling_units is None:
        item.daily_ceiling_units = DEFAULT_DAILY_CEILING_UNITS
    amount = amount_units(item)
    if amount:
        # A 15-minute errand on a preset with a 30-minute minimum chunk is simply done in one piece.
        item.min_chunk_units = min(item.min_chunk_units, amount)
    return item


def amount_units(item: Item) -> int | None:
    """The most units the item can ever need, or None when it is open-ended or not known yet."""
    return {
        "fixed": item.duration_units,
        "elastic": item.max_units,
        "target": item.cap_units or item.target_units,
        "open": None,
    }[item.amount]


def validate(item: Item) -> None:
    """Raise FieldError naming the first field that breaks a rule in DESIGN §6.5."""
    check_ranges(item)
    if item.when == "fixed":
        check_fixed(item)
        return
    check_window(item)
    check_amount(item)
    check_shape(item)


def check_ranges(item: Item) -> None:
    if not item.title.strip():
        raise FieldError("title", "must not be empty")
    if not 1 <= item.importance <= 5:
        raise FieldError("importance", "must be 1 to 5")
    if not 0 <= item.chunk_cost <= 1:
        raise FieldError("chunk_cost", "must be between 0 and 1")
    if not 0 <= item.neglect_carry <= 1:
        raise FieldError("neglect_carry", "must be between 0 and 1")
    if item.color is not None and item.color not in PIGMENTS:
        raise FieldError("color", f"must be one of {', '.join(PIGMENTS)}")
    for name in ("duration_units", "min_units", "ideal_units", "max_units", "target_units", "cap_units"):
        value = getattr(item, name)
        if value is not None and value < 0:
            raise FieldError(name, "must not be negative")


def check_fixed(item: Item) -> None:
    if item.start_utc is None or item.end_utc is None:
        raise FieldError("start_utc", "a fixed item needs a start and an end")
    if item.start_utc >= item.end_utc:  # ISO strings in one format compare in time order
        raise FieldError("end_utc", "must be after the start")


def check_window(item: Item) -> None:
    if item.when == "window" and item.firmness == "hard" and item.due_utc is None:
        raise FieldError("due_utc", "a hard deadline needs a due time")
    if item.release_utc and item.due_utc and item.release_utc >= item.due_utc:
        raise FieldError("due_utc", "must be after the release")
    if item.certainty == "tentative" and item.when != "window":
        raise FieldError("certainty", "a tentative item needs a window")


def check_amount(item: Item) -> None:
    if item.amount == "target" and (item.release_utc is None or item.due_utc is None):
        raise FieldError("release_utc", "a target needs a window with a release and a due time")
    if item.amount == "target" and item.target_units is None:
        raise FieldError("target_units", "a target needs an amount")
    if item.amount == "elastic":
        if None in (item.min_units, item.ideal_units, item.max_units):
            raise FieldError("min_units", "an elastic amount needs min, ideal and max")
        if not item.min_units <= item.ideal_units <= item.max_units:  # type: ignore[operator]
            raise FieldError("ideal_units", "needs min ≤ ideal ≤ max")
    if item.amount == "open":
        if item.due_utc is not None:
            raise FieldError("due_utc", "an open item has no due time")
        if item.firmness != "none":
            raise FieldError("firmness", "an open item is never late, so its firmness is none")
        if item.shape == "one_sitting":
            raise FieldError("shape", "an open item can't be one sitting")


def check_shape(item: Item) -> None:
    if item.shape == "one_sitting" and item.max_chunk_units is not None:
        raise FieldError("max_chunk_units", "a one-sitting item has no maximum chunk")
    if item.max_chunk_units is not None and item.max_chunk_units < item.min_chunk_units:
        raise FieldError("max_chunk_units", "must be at least the minimum chunk")
    amount = amount_units(item)
    if item.shape == "split" and amount is not None and item.min_chunk_units > amount:
        raise FieldError("min_chunk_units", "must not exceed the item's amount")


def would_create_cycle(edges: Mapping[int, Iterable[int]], source: int, target: int) -> bool:
    """Whether adding source → target closes a loop, given each node's outgoing edges."""
    seen, stack = set(), [target]
    while stack:
        node = stack.pop()
        if node == source:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(edges.get(node, ()))
    return False
