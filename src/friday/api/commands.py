"""Input and output of every command and query (DESIGN §9.3). The CLI imports only this package."""

__all__ = ["Empty"]

from datetime import date as calendar_date
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field

from friday.api.types import BlockOut, Empty, ItemFields, ItemOut, Model


def real_day(text: str | None) -> str | None:
    """A day that exists, "YYYY-MM-DD" (the audit, 8 Nov: 2026-02-30 was a crash inside Friday, not a word)."""
    if text is not None:
        try:
            calendar_date.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"{text!r} isn't a day: write it as YYYY-MM-DD, a date that exists") from error
    return text


Day = Annotated[str, AfterValidator(real_day)]


class OccurrenceChange(Model):
    """One time of a repeat that isn't like the others (27 Oct: "salsa every Saturday except 11/14, and this Saturday
    it's in Willard Straight Hall"): not that day, or another place, time or title that day."""

    date: Day  # "YYYY-MM-DD": the occurrence that day
    skip: bool = False
    start: str | None = None  # that day's own times, local "YYYY-MM-DDTHH:MM"
    end: str | None = None
    location: str | None = None
    title: str | None = None


class AddInput(ItemFields):
    text: str | None = None  # a quick-add line; fields given alongside it win
    after: list[int] = []
    before: list[int] = []
    every: str | None = None  # repeat shorthand (DESIGN §6.3) or `rrule:…`
    per_window: int | None = None
    calendar: str | None = None  # an event's calendar (its id): "" for only Friday, else "New events go to"
    exceptions: list[OccurrenceChange] = []  # with `every`: the times that differ


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


class ConflictInput(Model):
    """An answer to a disagreement between what Friday learned and a rule (commands/conflicts.py)."""

    key: str
    option: str


class EffectInput(Model):
    """A waiting suggestion of an event, at its own time or at one you've edited it to (local)."""

    id: int
    start: str | None = None
    end: str | None = None


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


class TermsOut(Model):
    """Friday's terms as they are now, and whether you have yet to accept them (PROGRESS.md C71)."""

    version: str
    text: str  # markdown
    changes: list[str]  # what changed since the last version, shown to someone who accepted an earlier one
    accepted: str | None  # the version you last accepted; None for never
    needed: bool  # Friday stays locked until you accept these


class TermsAcceptInput(Model):
    version: str  # the version you read: a change while it was open is refused, to be read again


class Changed(Model):
    """A command that changed something without a richer answer."""

    message: str


class ProgressInput(Model):
    id: int
    share: float  # 0 … 1 of the amount


class StartInput(Model):
    id: int
    alongside: bool = False  # keep what's being timed going too: two things at once (2 Nov)


class StuckInput(Model):
    id: int
    note: str = ""  # what's in the way, if you say


class StopInput(Model):
    id: int | None = None  # which of the things being timed; the one started last when not said
    done: bool = False
    at: str | None = None  # when you stopped, if it was earlier than now (you forgot the timer): local time


class SittingInput(Model):
    """A timed sitting as the calendar shows it: the item and its span (local), every timer record in it."""

    id: int
    start: str
    end: str


class SittingEditInput(SittingInput):
    new_start: str  # when you really started and stopped (local)
    new_end: str


class ReportInput(Model):
    """Something the app saw go wrong on your screen."""

    where: str  # the page or the part of it
    message: str
    detail: str | None = None  # a stack trace, or what was on screen


class DiagnoseInput(Model):
    hours: float = Field(3, gt=0, le=24 * 14)


class TimerOut(Model):
    item_id: int | None
    title: str | None = None
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


class ReviewTaskInput(Model):
    date: Day | None = None  # a planning date; today when left out
    item_id: int
    status: Literal["done", "partial", "not_done", "finished"]  # finished: done, and the whole task with it
    minutes: int | None = None  # partial: how much of the planned time you did


class ReviewSubmitInput(Model):
    date: Day | None = None  # a planning date; today when left out
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
    day: Day | None = None  # the first day cleared (YYYY-MM-DD, a planning day), for the calendar to show it


MealKind = Literal["breakfast", "lunch", "dinner", "snack"]


class FitInput(Model):
    """Do I have time for this? A change Friday tries on a copy of your plan and never keeps."""

    command: Literal["add", "edit", "series_add", "shove", "rule_add", "pin", "day_override"]
    input: dict[str, Any]  # that command's input, as you'd send it
    exact: bool = False  # plan the changed week as a replan would (seconds), not just check the deadlines (instant)


WhatIfCommand = Literal[
    "add", "edit", "series_add", "shove", "rule_add", "pin", "unpin", "day_override", "skip", "drop", "repeat"
]


class WhatIfChange(Model):
    """A change staged in What if, as the command that would make it. An item another staged change makes is named
    by a placeholder id: -(1000 × that change's place + the item's place + 1)."""

    command: WhatIfCommand
    input: dict[str, Any]


class WhatIfInput(Model):
    """What if: changes tried together on a copy of your plan; nothing is kept until you keep them."""

    changes: list[WhatIfChange]
    start: str  # the range the calendar shows, local
    end: str


class WhatIfKeepInput(Model):
    changes: list[WhatIfChange]  # kept together: one Undo takes them all back


class MealStartInput(Model):
    kind: MealKind | None = None  # by the time when left out: the routine whose window it is, else the hour
    at: str | None = None  # local time; now when left out


class MealEndInput(Model):
    at: str | None = None  # local time; now when left out


class MealLogInput(Model):
    """A meal you didn't tap: when you ate it, after the fact."""

    kind: MealKind
    start: str  # local
    end: str  # local


class MealSkipInput(Model):
    kind: MealKind
    date: Day | None = None  # the planning day; today when left out


class MealEditInput(Model):
    id: int
    start: str | None = None  # local
    end: str | None = None  # local


class MealRef(Model):
    id: int


class MealLengthInput(Model):
    kind: MealKind  # its routine is planned at the length you usually take, from today


class MealPlanInput(Model):
    kind: Literal["breakfast", "lunch", "dinner"]
    plan: bool  # plan it every day at the time and length you have it, or stop planning it


class SleepMarkInput(Model):
    kind: Literal["done", "bed", "up", "ready"]  # done with work, going to bed, up, ready to work
    at: str | None = None  # local time; now when left out


class SleepMarkEditInput(Model):
    id: int
    at: str  # local time


class SleepMarkRef(Model):
    id: int


class NapStartInput(Model):
    at: str | None = None  # local time you lay down; now when left out


class NapEndInput(Model):
    at: str | None = None  # local time you got up; now when left out


class NapLogInput(Model):
    """A nap you didn't tap: when you lay down and when you got up, after the fact."""

    start: str  # local
    end: str  # local


class NapEditInput(Model):
    id: int
    start: str | None = None  # local
    end: str | None = None  # local


class NapRef(Model):
    id: int


class SleepSkipInput(Model):
    date: Day  # the reviewed day
    kind: Literal["done", "bed", "up", "ready"]


class UnshoveInput(Model):
    id: int | None = None  # the most recent shove when left out


class SeriesAddInput(ItemFields):
    every: str
    start_date: str | None = None  # local date; today when left out
    per_window: int = 1
    release_offset_min: int | None = None
    due_offset_min: int | None = None


class RepeatInput(Model):
    id: int
    every: str  # as `every` in add: "week", "fri", "mon,wed", "other week", "day", "month", "3 days"


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


class SeriesSpacingInput(Model):
    id: int
    days: float | None = None  # at least this many days from one time's start to the next's; None for none (C50)


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
    date: Day
    bedtime: str | None = None
    wake: str | None = None
    margin_min: int | None = None
    cap_hours: float | None = Field(None, ge=0, le=24)  # a day's most work, 0 to 24 h (audit: -3 was taken)


class ReplanOutput(Model):
    plan_id: int | None
    status: str
    message: str


class ResolveInput(Model):
    unlock_pin_ids: list[int]  # let these move: a lock becomes a pin, an event's hold lets work in


class LockKeepInput(Model):
    pin_ids: list[int]  # keep these where they are: not asked again unless they make work an hour later


class LateAcceptInput(Model):
    item_ids: list[int]  # work you accept will be late: not asked again unless it gets an hour later


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
    signature: str = ""  # which blocks it has: two ways with the same one are the same way


class OtherWayInput(Model):
    seed: int  # 1, 2, …: each seed weighs the rules differently


class OneWayOut(Model):
    """One way, asked for one at a time so each shows as it comes; None when it came out as your plan."""

    way: OtherWay | None
    tries: int  # seeds worth trying, from 1, for two ways unlike your plan and each other
    wanted: int  # ways to show


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
    # It only adds, moves, repeats or deletes a calendar event: with claude.events_without_asking on, it applies at
    # once.
    event: bool = False


class AskClaudeOut(Model):
    reply: str  # what Claude says, in a sentence or two
    actions: list[ProposedAction]


class EventGoingInput(Model):
    title: str  # an event you go to: never offered to skip again


class EventCategoryInput(Model):
    id: int  # an event; its category is chosen for every event with its title
    category: str | None = None  # a category's name; "" for none; None to let Friday decide again


class CategoryMergeInput(Model):
    name: str  # the category that goes
    into: str  # the one its events join


class EventKeepInput(Model):
    id: int  # one occurrence of an optional event (gym on Thursday)
    going: bool = True  # you're going this time, so work keeps off it; False leaves it to Friday again


class EventHoldInput(Model):
    id: int  # the event
    task_id: int | None = None  # the task its time is for; None makes it an event like any other again


class EventsInput(Model):
    text: str = ""
    limit: int = 12


class DateInput(Model):
    date: Day | None = None  # a planning date; today when left out


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
    day: Day | None = None


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


class SettleInput(Model):
    """A past block settled before the review: done, partly or not done."""

    block_key: str
    status: Literal["done", "partial", "not_done"] = "done"
    share: float = 1.0
    until: str | None = None  # local: the block as the calendar showed it, pieces joined, to here


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


class LearnOrderInput(Model):
    first: str
    then: str
    use: bool  # plan `first` ahead of `then` from now (kind_order), or don't offer it again


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
    media_type: str = "text/plain"  # text/plain, text/html (read as its text), application/pdf, image/png, image/jpeg
    content: str


class GoogleClientInput(Model):
    """The OAuth client JSON downloaded from Google Cloud (a Desktop app's), as text."""

    content: str


class GoogleConnectInput(Model):
    """Which account to sign in: none to add one (Google's page asks which), or one already connected to sign it in
    again (to allow Gmail, or when its sign-in expired)."""

    account: str | None = None


class GoogleAccountInput(Model):
    account: str  # a connected account's address


class SuggestionInput(Model):
    id: int
    edits: dict[str, Any] = {}  # fields to change before accepting


class RepeatBatch(Model):
    batch: str  # a repeating calendar event waiting to come in: "repeat:<its id>"


class BatchInput(Model):
    batch: str
    edits: dict[str, Any] = {}  # applied to every suggestion in it: a repeating event's kind or tag, say


class AskInput(Model):
    text: str


class GmailAppInput(Model):
    """A Gmail address and its app password (16 letters, spaces allowed), kept in secrets.toml, never sent back;
    an empty password forgets the address."""

    address: str = Field(max_length=320)
    password: str = Field("", max_length=100)


class AiKeyInput(Model):
    """An AI service's key, kept in secrets.toml (never in settings, never sent back); "" forgets it."""

    provider: Literal["claude", "openai", "gemini", "grok", "muse", "compatible"]
    key: str = Field(max_length=500)


class AiModelsInput(Model):
    """Whose models to list: a provider (and the address you gave, for another service), chosen or not yet."""

    provider: Literal["claude", "openai", "gemini", "grok", "muse", "compatible", "local"]
    base_url: str | None = None


class LocalModelInput(Model):
    """An open model for Ollama to run on this Mac, by its name ("llama3.2:3b", "nate/instinct")."""

    name: str = Field(min_length=1, max_length=120)


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


class PhoneSetInput(Model):
    on: bool


class PhoneRef(Model):
    id: str


class EventModeInput(Model):
    title: str


class EventOptionalInput(Model):
    """Whether work may take an event's time (its editor's "Can work take its time?")."""

    title: str
    mode: Literal["kept", "optional", "ahead"]


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
    location: str = ""  # where it is, as Calendar has it


class MacWrittenInput(Model):
    """What the Mac app made of a change to one of the Mac's events (`mac_writes`)."""

    id: int  # the change's id
    ok: bool
    error: str | None = None  # why not, when it couldn't
    gone: bool = False  # the event wasn't on its calendar any more
    event: MacEvent | None = None  # the event as it is after the change (its id moves with a one-off event's start)


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
