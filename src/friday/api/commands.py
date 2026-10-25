"""Input and output of every command and query (DESIGN §9.3). The CLI imports only this package."""

__all__ = ["Empty"]

from typing import Any, Literal

from pydantic import Field

from friday.api.types import BlockOut, Empty, ItemFields, ItemOut, Model


class AddInput(ItemFields):
    text: str | None = None  # a quick-add line; fields given alongside it win
    after: list[int] = []
    before: list[int] = []
    every: str | None = None  # repeat shorthand (DESIGN §6.3) or `rrule:…`
    per_window: int | None = None


class AddOutput(Model):
    item: ItemOut | None = None
    series_id: int | None = None
    occurrences: int = 0
    warnings: list[str] = []


class EditInput(ItemFields):
    id: int
    from_date: str | None = None  # for a series occurrence: change the series from this date on


class ItemRef(Model):
    id: int


class DoneInput(Model):
    id: int
    actual_min: int | None = None


class ItemResult(Model):
    item: ItemOut


class DependInput(Model):
    item_id: int
    depends_on_id: int
    fraction: float = 1.0
    lag_min: int = 0


class AreaInput(Model):
    name: str
    color: str | None = None


class AreaEditInput(Model):
    id: int
    name: str | None = None
    color: str | None = None
    archived: bool | None = None


class AreaOut(Model):
    id: int
    name: str
    color: str | None
    archived: bool


class Changed(Model):
    """A command that changed something without a richer answer."""

    message: str


class ProgressInput(Model):
    id: int
    share: float  # 0 … 1 of the amount


class StartInput(Model):
    id: int


class StuckInput(Model):
    id: int
    note: str = ""  # what's in the way, if you say


class StopInput(Model):
    done: bool = False


class ReportInput(Model):
    """Something the app saw go wrong on your screen."""

    where: str  # the page or the part of it
    message: str
    detail: str | None = None  # a stack trace, or what was on screen


class DiagnoseInput(Model):
    hours: float = Field(3, gt=0, le=24 * 14)


class TimerOut(Model):
    item_id: int | None
    started: str | None
    minutes: int = 0
    elapsed_s: int = 0  # the running session so far; the bar ticks on from it
    message: str = ""


class LogInput(Model):
    """Past work on an item, or (with `title`) something that happened, recorded as a fixed item."""

    start: str
    end: str
    id: int | None = None
    title: str | None = None


class ReviewEntry(Model):
    block_key: str | None = None  # T42@2026-10-20T14:00, a block of the day
    item_id: int | None = None
    status: Literal["done", "partial", "not_done"] = "done"
    share: float = 1.0  # for partial
    start: str | None = None  # for something added that happened
    end: str | None = None


class ReviewSubmitInput(Model):
    date: str | None = None  # a planning date; today when left out
    entries: list[ReviewEntry] = []


class PinInput(Model):
    """The item's pins overlapping the new one, or the block it moves from (`from_start`–`from_end`), are replaced."""

    id: int
    start: str
    end: str | None = None  # default: the item's remaining time, up to its length
    kind: Literal["preferred", "locked"] = "locked"
    from_start: str | None = None
    from_end: str | None = None


class UnpinInput(Model):
    id: int
    pin_id: int | None = None  # one pin; every pin of the item when left out


class ShoveInput(Model):
    """`30m`, `1h`, `12:00-13:30` (today, or `12:00-13:30 wed`), `rest`, `day fri` (or several days)."""

    range: str
    decision: Literal["ask", "shove_anyway", "keep_must_dos", "cancel"] = "ask"


class MustDo(Model):
    item_id: int
    title: str
    extra_late_hours: float
    planned_hours_in_range: float


class ShoveOutput(Model):
    created: list[int] = []  # shove item ids
    must_do: list[MustDo] = []
    message: str = ""
    day: str | None = None  # the first day cleared (YYYY-MM-DD, a planning day), for the calendar to show it


class UnshoveInput(Model):
    id: int | None = None  # the most recent shove when left out


class SeriesAddInput(ItemFields):
    every: str
    start_date: str | None = None  # local date; today when left out
    per_window: int = 1
    release_offset_min: int | None = None
    due_offset_min: int | None = None


class SeriesOut(Model):
    id: int
    rule: str
    description: str
    occurrences: int


class SeriesEditInput(ItemFields):
    id: int
    from_date: str | None = None
    every: str | None = None
    per_window: int | None = None


class SeriesRef(Model):
    id: int


class SettingsSetInput(Model):
    key: str
    value: Any


class PaceInput(Model):
    name: str | None = None  # a saved pace; dials alone mean custom, starting from the dials in effect
    capacity: float | None = None
    rest: float | None = None
    spread: float | None = None
    growth: float | None = None
    for_days: int | None = None
    until: str | None = None  # a date or weekday


class PaceOut(Model):
    label: str
    dials: dict[str, float]
    start_date: str
    end_date: str | None
    message: str


class PaceSaveInput(Model):
    name: str
    capacity: float | None = None
    rest: float | None = None
    spread: float | None = None
    growth: float | None = None


class PaceDeleteInput(Model):
    name: str


class DayOverrideInput(Model):
    date: str
    bedtime: str | None = None
    wake: str | None = None
    margin_min: int | None = None
    cap_hours: float | None = None


class ReplanOutput(Model):
    plan_id: int | None
    status: str
    message: str


class ResolveInput(Model):
    unlock_pin_ids: list[int] = []


class UndoInput(Model):
    command_id: int


class RangeInput(Model):
    start: str | None = None  # local; now when left out
    end: str | None = None  # the scheduler horizon's end when left out


class ItemsInput(Model):
    status: Literal["todo", "done", "dropped", "skipped", "all"] = "todo"
    area: str | None = None
    text: str | None = None


class SetupCalendar(Model):
    name: str
    shown: bool = True  # False: a toggle, kept off your calendar until switched on under Show
    busy: bool = True  # its events block time when Friday plans


class SetupInput(Model):
    """Your answers to the questions Friday asks when it first opens (Setup): each sets the settings and rules it's
    about, all in one change you can undo."""

    wake: str = Field(pattern=r"^\d{2}:\d{2}$")
    bedtime: str = Field(pattern=r"^\d{2}:\d{2}$")
    weekend_wake: str = Field(pattern=r"^\d{2}:\d{2}$")  # Saturday and Sunday mornings
    weekend_bedtime: str = Field(pattern=r"^\d{2}:\d{2}$")  # Friday and Saturday nights
    normal_hours: float = Field(ge=1, le=16)  # a normal day's work: the daily-load rule
    most_hours: float = Field(ge=1, le=16)  # a heavy day's: the daily limit
    focus_hours: float = Field(ge=0.5, le=8)  # the longest stretch of focused work
    evening_free: float = Field(ge=0, le=6)  # hours kept free on weekday evenings; 0: the rule off
    evening_from: str = Field(pattern=r"^\d{2}:\d{2}$")
    weekend_free: float = Field(ge=0, le=13)  # hours kept free each weekend day; 0: the rule off
    finish_early_days: int = Field(ge=0, le=7)  # 0: the rule off
    brief: bool
    calendars: list[SetupCalendar] = []


class ImportPersonalInput(Model):
    todos_path: str | None = None  # Todo List's tasks; ~/Documents/Todo List/todos.json when left out
    categories_path: str | None = None  # Chroma's rules; ~/Library/Application Support/Chroma/categories.json


class ChromaColorsInput(Model):
    colors_path: str | None = None  # Chroma's colours; ~/Library/Application Support/Chroma/colors.json


class OtherWay(Model):
    """Another way to plan the same work (COMBINED.md 25)."""

    weights: dict[str, float]  # each learnable rule's factor
    seed: int  # the search seed it was made with
    summary: str  # how it differs from your plan, in words
    blocks: list[BlockOut]
    hours: float
    sessions: int
    late: dict[str, float]  # title → hours late
    rule_totals: dict[str, int]


class OtherWaysOut(Model):
    current: dict[str, int]  # your plan's cost by rule
    ways: list[OtherWay]


class OtherWayPickInput(Model):
    weights: dict[str, float]
    seed: int = 0
    rule_totals: dict[str, int]  # the way's, as `other_ways` gave them


class AskClaudeInput(Model):
    text: str
    purpose: Literal["anything", "rule"] = "anything"  # a rule the grammar couldn't read: only rule-shaped answers


class ProposedAction(Model):
    """One change Claude proposes, as the command that makes it; nothing runs until you apply it."""

    sentence: str
    command: str
    input: dict[str, Any]
    error: str | None = None  # the command wouldn't take it as written


class AskClaudeOut(Model):
    reply: str  # what Claude says, in a sentence or two
    actions: list[ProposedAction]


class EventGoingInput(Model):
    title: str  # an event you go to: never offered to skip again


class EventsInput(Model):
    text: str = ""
    limit: int = 12


class DateInput(Model):
    date: str | None = None  # a planning date; today when left out


class ReorderInput(Model):
    parent_id: int
    ids: list[int]  # the steps, first to last


class InsightsInput(Model):
    weeks: int = Field(4, ge=1, le=52)


class WeekNoteInput(Model):
    week: str  # the week's first day
    feel: str | None = None  # how it felt, one of a few words
    notes: str | None = None  # anything to remember; shown at the top of next week's review


class ParseInput(Model):
    text: str


class BlockRef(Model):
    key: str  # T42@2026-10-20T14:00


class WhyOut(Model):
    key: str
    sentence: str
    costs: dict[str, int]
    total: int


class WhyNotInput(Model):
    key: str
    start: str | None = None


class WhyNotOut(Model):
    key: str
    to_start: str | None
    wall: str | None
    difference: dict[str, int]
    total: int


class PreviewWeightsInput(Model):
    weights: dict[str, float] = {}
    off: list[str] = []
    rules: list[dict[str, Any]] | None = None  # a whole rules list to try in place of yours (changed params too)


class RuleTotalsInput(Model):
    day: str | None = None


class TriageStep(Model):
    command: str
    input: dict[str, Any]


class TriageOption(Model):
    action: str
    steps: list[TriageStep]  # applying the option runs these commands in order
    late_hours_saved: float
    side_effects: list[str] = []
    skip_title: str | None = None  # an event offered to skip; `event_going` stops offering it


class TriageOut(Model):
    late: dict[str, float]  # item title → late hours now
    options: list[TriageOption]


class LogListInput(Model):
    limit: int = 20
    item_id: int | None = None  # only commands naming this item


class FitsInput(Model):
    minutes: int | None = None  # the gap; until the next block when left out


class CalendarInput(Model):
    start: str | None = None  # a local date; today when left out
    days: int = Field(7, ge=1, le=42)  # six weeks: the month view


class LoadInput(Model):
    weeks: int = Field(12, ge=1, le=52)


class TemplateApplyInput(Model):
    """A project from a template: a parent item with one child per step, each after the one before."""

    template: str
    title: str
    hours: float = Field(gt=0)  # the whole project; steps get their share
    due: str | None = None
    release: str | None = None
    area: str | None = None


class TemplateSaveInput(Model):
    name: str
    project_id: int  # its children, in order, become the steps


class ActInput(Model):
    token: str  # from a notification's button, signed by the server and good once


class SettleInput(Model):
    """One block of today settled before the review: done, partly or not done."""

    block_key: str
    status: Literal["done", "partial", "not_done"] = "done"
    share: float = 1.0


class PushSubscription(Model):
    endpoint: str
    keys: dict[str, str]  # p256dh and auth, as the browser gives them


class EndpointInput(Model):
    endpoint: str


class CompareAnswerInput(Model):
    id: int  # the comparison
    answer: Literal["a", "b", "skip"]


class ProposalAnswerInput(Model):
    """Yes or no to a proposed rule (`kind` "rule") or to a wall question (`kind` "wall": yes keeps it hard)."""

    kind: Literal["rule", "wall"]
    name: str  # the template (`fri_sat:late:any`) or the rule
    yes: bool


class CheckinInput(Model):
    state: Literal["tired", "normal", "motivated"]


class VersionInput(Model):
    version: int


class ResetInput(Model):
    module: Literal["weights", "state", "proposals", "durations", "energy", "all"] = "all"


class LearnModuleInput(Model):
    module: Literal["durations", "energy"]
    use: bool


class SourceInput(Model):
    """A calendar feed (`ics`, with `url`). Feeds can also be listed in `friday.toml`."""

    kind: Literal["ics"] = "ics"
    name: str
    url: str
    trusted: bool = False


class SourceEditInput(Model):
    id: int
    name: str | None = None
    url: str | None = None
    trusted: bool | None = None
    enabled: bool | None = None


class SourceRemoveInput(Model):
    id: int
    forget: bool = False  # also delete what it brought in (its raw inputs and pending suggestions)


class DocumentInput(Model):
    """A document to read for tasks: a syllabus, a handout, a screenshot. Text, or base64 for a PDF or image."""

    name: str
    media_type: str = "text/plain"  # text/plain, application/pdf, image/png, image/jpeg
    content: str


class SuggestionInput(Model):
    id: int
    edits: dict[str, Any] = {}  # fields to change before accepting


class BatchInput(Model):
    batch: str
    edits: dict[str, Any] = {}  # applied to every suggestion in it: a repeating event's kind or tag, say


class AskInput(Model):
    text: str


class TokenInput(Model):
    name: str = Field(min_length=1, max_length=40)
    scope: Literal["read", "read-write"] = "read"


class TokenRef(Model):
    name: str


class TokenMade(Model):
    name: str
    scope: str
    token: str  # shown this once


class RuleTextInput(Model):
    text: str = ""
    overrides: str = "{}"  # JSON: Reading fields you set yourself (a query string can't carry a mapping)


class RuleAddInput(Model):
    text: str = ""
    overrides: dict[str, Any] = {}  # Reading fields you set yourself: subject, rel, at, until, days, amount, event
    strength: Literal["Prefer", "Strongly", "Always"] = "Prefer"


class RuleSetInput(Model):
    name: str
    strength: Literal["Prefer", "Strongly", "Always"] | None = None
    enabled: bool | None = None


class RuleRef(Model):
    name: str


class MailLogInput(Model):
    limit: int = Field(60, ge=1, le=500)


class RepeatPick(Model):
    batch: str  # "repeat:<event id>", as calendar_repeats lists it
    area: str | None = None  # the tag its occurrences get
    kind: str | None = None  # instead of the kind Friday read


class RepeatsImportInput(Model):
    repeats: list[RepeatPick] = Field(min_length=1)


class CalendarSetInput(Model):
    id: str  # the Google calendar's id, or the Mac's with `mac`
    mac: bool = False  # one of the Mac's calendars, which the Mac app feeds in
    on: bool | None = None
    kind: str | None = None  # a kind's name, or "auto" to decide per event
    trusted: bool | None = None  # its events skip the inbox
    editable: bool | None = None  # changes made in Friday are saved back to it


class RuleWinInput(Model):
    """Your answer to "Which should win?": `winner` beats `loser` whenever they clash."""

    winner: str
    loser: str


class MacCalendar(Model):
    """One of the Mac's calendars, as EventKit lists it."""

    id: str  # EventKit's calendarIdentifier
    name: str
    account: str = ""  # the account it belongs to: iCloud, an email address, On My Mac
    type: Literal["local", "caldav", "exchange", "subscription", "birthday", "other"] = "other"
    color: str | None = None  # "#rrggbb"
    writable: bool = False


class MacEvent(Model):
    """One occurrence of an event on the Mac: timed with an offset ("2026-10-23T09:00:00-04:00"), or whole days with
    the end the day after the last ("2026-10-23" to "2026-10-24"), as Google gives them."""

    id: str  # unique per occurrence
    calendar: str  # its calendar's id
    title: str = ""
    start: str
    end: str
    all_day: bool = False
    series: str | None = None  # the repeating event it is an occurrence of
    free: bool = False  # shown as free (availability)
    declined: bool = False  # you declined the invitation


class MacSyncInput(Model):
    """What the Mac app sees on the Mac's calendars, between `since` and `until` (times with an offset)."""

    calendars: list[MacCalendar]
    events: list[MacEvent]
    since: str
    until: str


class KindAddInput(Model):
    name: str
    like: str  # the kind it starts as a copy of


class KindRemoveInput(Model):
    name: str
    move_to: str  # where its items, series and settings go


class MergeGroup(Model):
    keep: int  # the copy that stays, with the others' time logged moved onto it
    drop: list[int]


class MergeInput(Model):
    groups: list[MergeGroup]


class ItemIds(Model):
    ids: list[int]


class ReviewedInput(Model):
    ids: list[int]
    keep: bool = True  # False takes them off your list (your calendar keeps its event)
