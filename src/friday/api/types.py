"""Response types shared by commands, the server and the CLI. Times are local `YYYY-MM-DDTHH:MM`; lengths minutes."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemFields(Model):
    """Item fields as the API speaks them. Every field is optional so `edit` can send only what changes."""

    title: str | None = None
    notes: str | None = None
    preset: str | None = None
    area: str | None = None
    tags: list[str] | None = None
    parent_id: int | None = None
    when: Literal["fixed", "window", "anytime"] | None = None
    start: str | None = None
    end: str | None = None
    release: str | None = None
    due: str | None = None
    amount: Literal["fixed", "elastic", "target", "open"] | None = None
    duration_min: int | None = None
    min_min: int | None = None
    ideal_min: int | None = None
    max_min: int | None = None
    target_min: int | None = None
    cap_min: int | None = None
    daily_ceiling_min: int | None = None
    shape: Literal["one_sitting", "split"] | None = None
    min_chunk_min: int | None = None
    max_chunk_min: int | None = None
    chunk_cost: float | None = None
    spread: Literal["none", "spread", "cluster"] | None = None
    firmness: Literal["hard", "soft", "none"] | None = None
    importance: int | None = None
    neglect_carry: float | None = None
    energy: Literal["deep", "light", "physical", "social"] | None = None
    location: str | None = None
    color: str | None = None
    certainty: Literal["planned", "tentative"] | None = None
    event_kind: str | None = None
    blocks_time: bool | None = None
    free: bool | None = None
    long_term: bool | None = None
    expires: bool | None = None
    background: bool | None = None  # runs by itself once started: only its first quarter hour needs you
    buffer_before_min: int | None = None
    buffer_after_min: int | None = None


class ItemOut(Model):
    id: int
    title: str
    preset: str | None
    area: str | None
    tags: list[str]
    parent_id: int | None
    when: str
    start: str | None
    end: str | None
    release: str | None
    due: str | None
    amount: str
    duration_min: int | None
    firmness: str
    importance: int
    energy: str | None
    shape: str
    color: str | None = None
    notes: str = ""
    long_term: bool = False
    background: bool = False  # runs by itself once started: other work is planned on top of it
    expires: bool | None = None  # your own say on pointless-if-late; None follows the kinds in settings
    pointless_late: bool = False  # what's in effect: never planned after its due
    fading_late: bool = False  # matters less the longer it's overdue (settings `fading_late`)
    cushion: float = 1.0  # how far over you consistently run on work like this; the plan reserves that much more
    calendar: str | None = None  # the calendar an event came from
    calendar_color: str | None = None  # its pigment, set in Settings → Calendars
    saves_to_calendar: bool = False  # changes made here are saved back to its calendar
    category: str | None = None  # its category (commands/categories.py)
    category_color: str | None = None
    category_by: str | None = None  # who said: "you", "always" (your words), "similar" (its clues), "claude"
    category_like: str | None = None  # the event it's like, when its clues decided
    category_hint: str | None = None  # the clues' unsure guess, offered on the card and not painted
    chroma_color: str | None = None  # the pigment Chroma showed it in, before your own or its category's
    left_out: str | None = None  # why it doesn't count as busy: calendar, reminder, free, filtered, skipped or through
    filtered: bool = False  # the categories' filter hides it (office hours), when you hide what it hides
    # An optional event (gym, climbing club) the plan gives to work, with the work that takes it: you're skipping it,
    # and the calendar says so rather than draw the work over it (plan query). `going`: you said you'd go this time.
    gives_way_to: str | None = None
    optional: bool = False
    going: bool = False
    holds: dict[str, Any] | None = None  # an event whose time is for a task: {id, title} (`event_hold`)
    certainty: str
    event_kind: str | None = None
    status: str
    series_id: int | None
    done_min: int  # recorded progress
    remaining_min: int | None  # None for open items
    estimate: dict[str, Any] | None = None
    guess_min: int | None = None  # Friday's own guess at its length, beside yours when you gave one
    buffer_before_min: int | None = None  # an event's gap, or a task's time to get there
    buffer_after_min: int | None = None  # and to get back
    location: str | None = None  # where an event is: its calendar's, or what you typed
    waiting_on: list[int] = []  # unfinished items this one depends on (filled by the `items` query)


class BlockOut(Model):
    key: str  # T42@2026-10-20T14:00
    item_id: int
    title: str
    area: str | None = None
    preset: str | None = None  # its kind: work with no tag wears its kind's paint
    estimated: bool = False  # the item's length is Friday's estimate, drawn with a `~`
    start: str
    end: str
    pinned: Literal["preferred", "locked"] | None = None
    tentative: bool = False
    fixed: bool = False  # a class or event at a set time, not planned work
    cost: dict[str, int] = {}
    # A past block, what became of it: done (finished, marked done, or counted done while unmarked blocks count),
    # timed (a timer sitting covers it: the sitting shows instead), missed (not done: Friday plans it again), gone
    # (the item was deleted or skipped). None for what's still ahead.
    state: Literal["done", "timed", "missed", "gone"] | None = None
    background: bool = False  # it runs by itself: its first quarter hour needs you, other work goes on top of the rest


class ChangeOut(Model):
    added: list[BlockOut] = []
    moved: list[dict[str, Any]] = []
    removed: list[BlockOut] = []
    inputs: list[dict[str, Any]] = []
    rule_totals_before: dict[str, int] = {}
    rule_totals_after: dict[str, int] = {}
    notices: list[str] = []
    late_hours: dict[str, float] = {}  # hard work finishing after its due, by title


class CommandResult(Model):
    command_id: int | None  # None for queries and previews
    result: Any
    provisional: list[BlockOut] | None = None  # the executor's quick placement, drawn as ghosts
    changes: ChangeOut | None = None  # preview "full": what a warm solve would change
    preview: bool = False
    repeated: bool = False  # an idempotency key matched an earlier run
    # The plan generation this change made: the plan view has seen it once its `generation` is this or later.
    generation: int | None = None
    # What the quick placement needs, when it's made after the answer (server/placer.py): the generation, the items
    # changed, and the span a dragged block left, by item.
    _placing: tuple[int, set[int], dict[int, list[tuple[int, int]]]] | None = PrivateAttr(default=None)


class Empty(Model):
    pass


@dataclass(frozen=True)
class Verb:
    """One registry entry as the CLI sees it (the list is generated into `api/verbs.py`)."""

    method: str
    path: str
    input: type[BaseModel]
    mutates: bool
    affects_plan: bool
    summary: str
