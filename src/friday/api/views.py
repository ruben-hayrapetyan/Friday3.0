"""Answers of the queries (DESIGN §9.3): plan, now, status, the calendar and the rest. Inputs are in `commands.py`."""

from typing import Any, Literal

from friday.api.commands import TimerOut
from friday.api.types import BlockOut, ItemOut, Model


class PlanOut(Model):
    plan_id: int | None
    blocks: list[BlockOut]
    fixed: list[ItemOut]
    day_hours: dict[str, float]
    provisional: bool = False
    sessions: list[BlockOut] = []  # what you timed in the range, when you did it (keys S<id>@<start>)


class ItemDetail(Model):
    item: ItemOut
    blocks: list[BlockOut]
    progress: list[dict[str, Any]]
    depends_on: list[dict[str, Any]]


class ParseOutput(Model):
    fields: dict[str, Any]
    spans: list[dict[str, Any]]
    warnings: list[str]


class Swap(Model):
    item_id: int
    title: str
    minutes: int
    price: int
    slack_hours: float | None


class Alert(Model):
    item_id: int
    title: str
    kind: str
    latest_start: str


class NowOut(Model):
    current: BlockOut | None
    current_source: str
    timer_minutes: int = 0
    next: BlockOut | None
    swaps: list[Swap]
    alerts: list[Alert]
    fits: list[Swap]
    gap_minutes: int


class ReviewOut(Model):
    date: str
    reviewed: bool
    blocks: list[BlockOut]
    sessions: list[dict[str, Any]]
    finished: list[ItemOut]  # remaining reached 0: confirm with `done`
    settled: dict[str, int] = {}  # block key → minutes already answered (by `settle` or an earlier review)
    sleep: list["SleepAsk"] = []  # tracked sleep: the taps that day is missing, to add or skip


class SleepAsk(Model):
    kind: Literal["up", "ready", "bed"]
    date: str  # the day the review is of
    at: str  # a local time to start from: your usual one
    question: str


class PacesOut(Model):
    default: str
    paces: dict[str, dict[str, float]]
    now_label: str
    now_dials: dict[str, float]
    period_end: str | None


class LockConflict(Model):
    pin_id: int
    item_id: int
    title: str
    start: str
    extra_late_hours: float


class StatusOut(Model):
    demo: bool = False  # `fridayd demo`: made-up sample data, said on every page
    generation: int
    plan_id: int | None
    plan_generation: int | None
    timer: TimerOut | None
    settings_version: int
    ready: bool  # timezone and sleep are set
    notices: list[str]
    problems: list[str] = []  # the server's banners: a failing worker, plugins that didn't load
    conflicts: list[LockConflict] = []  # a newer plan waits on these locks (`resolve`)
    config_keys: list[str] = []  # settings friday.toml sets: read-only in the app
    suggestions: int = 0  # waiting in the inbox (repeating calendar events wait in Settings → Repeating)
    late: dict[str, float] = {}  # hard work the plan finishes after its due: hours late, by title
    late_items: list["LateItem"] = []  # the same, each with its id and due, soonest due first


class LateItem(Model):
    item_id: int
    title: str
    due: str | None  # local
    hours: float  # how late the plan finishes it


class KindAccuracy(Model):
    kind: str
    n: int
    median: float  # actual time over the estimate: 1.0 is on estimate
    low: float  # the quartiles, for the spread
    high: float


class InsightsOut(Model):
    weeks: int
    done: int
    hours: float
    estimate_ratio: float | None
    by_kind: list[KindAccuracy]
    heat: list[list[int]]  # minutes worked by weekday (Monday first) and hour, 08:00 to 23:00
    best_hours: str | None  # when you get the most done, in words


class StatsOut(Model):
    done_this_week: int
    hours_this_week: float
    late_items: int
    estimate_ratio: float | None


class CalendarDay(Model):
    date: str
    cap_hours: float
    pace: str | None  # the pace's name on days that don't use the default
    bedtime: str  # local; sleep's margin runs from here to `core`
    core: str  # the core night, from here to `wake`
    wake: str  # the next morning


class DueMarker(Model):
    item_id: int
    title: str
    due: str


class CalendarOut(Model):
    now: str  # the server's local time, so the client's clock can follow it
    today: str
    axis_start_min: int  # the earliest wake, minutes after local midnight
    axis_end_min: int  # the latest start of core sleep (bedtime + margin); past 1440 means after midnight
    days: list[CalendarDay]
    dues: list[DueMarker]


class Happening(Model):
    """One thing in `diagnose`'s timeline."""

    at: str
    kind: str  # command, plan, job, report
    summary: str


class LogEntry(Model):
    id: int
    at: str
    actor: str
    command: str
    input: dict[str, Any]
    undone_by: int | None


class ProjectOut(Model):
    item: ItemOut
    children: list[ItemOut]  # every descendant; `parent_id` gives the tree
    done_min: int
    remaining_min: int
    planned_finish: str | None  # the last planned work: a block's end, or a date when the allocator plans it
    status: Literal["done", "on_track", "late", "unplanned"]


class ExamPrepOut(Model):
    item: ItemOut
    planned_finish: str | None  # its last planned work, when all it has left is planned


class ExamOut(Model):
    item: ItemOut  # the exam itself, a fixed event
    prep: list[ExamPrepOut]  # what prepares for it, done and to do, soonest due first
    done_min: int
    remaining_min: int
    planned_finish: str | None  # when the last prep is planned to end, once all of it is planned
    status: Literal["no_prep", "ready", "on_track", "late", "unplanned"]
    focus_from: str | None  # when exam focus starts for it (other courses wait), if that rule is on


class WeekLoad(Model):
    start: str  # the week's first day
    hours: float  # planned work: the plan's blocks inside the horizon, the allocator's forecast past it
    capacity: float  # hours the allocator may fill
    forecast: bool  # some of the week is past the horizon
    due: list[DueMarker]  # hard deadlines that week


class Rock(Model):
    item_id: int
    title: str
    planned_min: int  # planned today
    due: str | None
    hard: bool


class BriefOut(Model):
    """The morning brief (DESIGN §20.4), as data and as plain text."""

    rocks: list[Rock]  # today's big things, 3–5
    fixed: list[ItemOut]  # today's fixed items
    alerts: list[Alert]
    pace: str | None  # "Easy pace until Fri", "Back to Normal today"; None on an ordinary day
    sleep: str | None = None  # tracked sleep: a short night, with an Easy day offered beside it
    summary: str
    text: str


class AreaWeek(Model):
    area: str
    planned_h: float  # what each morning's plan held
    actual_h: float  # what was recorded


class DeadlineWeek(Model):
    item_id: int
    title: str
    due: str
    outcome: Literal["on_time", "late", "open"]


class WeekItem(Model):
    item_id: int
    title: str
    area: str | None
    when: str  # local time: when it was finished, is due, or happens
    note: str = ""


class WeekOut(Model):
    """The weekly review (DESIGN §18.9): planned against actual by area, deadlines, moves and notifications."""

    start: str
    end: str  # the last day
    areas: list[AreaWeek]
    fixed_h: dict[str, float]  # fixed time by event kind
    deadlines: list[DeadlineWeek]
    moves: int  # pins, unpins and shoves you made
    notifications: dict[str, int]  # sent, acted, dismissed
    learned: list[str] = []  # what Friday learned (M9)
    finished: list[WeekItem] = []  # done this week
    carried: list[WeekItem] = []  # planned this week, still open
    coming: list[WeekItem] = []  # due or fixed in the next seven days
    note: dict[str, str] = {}  # how the week felt and anything to remember (`week_note`)


class Question(Model):
    id: int
    day: str
    a: list[dict[str, Any]]  # that day's blocks in version A: item_id, title, start, end
    b: list[dict[str, Any]]
    fixed: list[dict[str, Any]] = []  # the day's classes and events (title, start, end), the same in both


class QuestionsOut(Model):
    """What the evening review asks (DESIGN §18.9): at most two comparisons a day, a rule proposal or a wall
    question, and a check-in when state inference is on."""

    comparisons: list[Question]
    proposal: dict[str, str] | None  # {name, sentence}
    wall: dict[str, str] | None  # {rule, sentence}
    checkin: bool


class LearningOut(Model):
    mode: str  # learn.weights
    version: int  # the profile in use; 0 before anything was learned
    multipliers: dict[str, float]
    suggested: dict[str, Any] | None  # {version, changes: [{rule, from, to}], evidence}
    comparisons: int
    drags: int
    answer_noise: float
    state: dict[str, Any] | None  # {on, gain, mood} while state inference is on
    proposals: dict[str, Any]  # pending, accepted, refused
    digest: list[str]
    durations: dict[str, Any] | None = None  # learned lengths: in use, n, error against the old estimator
    energy: dict[str, Any] | None = None  # learned hours: in use, observations, the hours where work slips most


class SuggestionOut(Model):
    id: int
    source: str
    origin: str  # what it came from: an email subject, a document's name, an event's summary
    command: str  # add, or edit for a change to something accepted earlier
    input: dict[str, Any]
    quotes: dict[str, str]
    confidence: float
    duplicate_of: int | None
    batch: str | None
    created: str
    repeat: str | None = None  # the repeat in words, when there is one
    source_kind: str = ""  # ics, gcal, gmail or upload
    source_text: str | None = None  # what was read, when it is text (not a PDF or image), for the quotes to sit in
    guess_min: int | None = None  # a task with no length: the one Friday would give it on accept


class ModelCheck(Model):
    model: str
    job: str  # what Friday uses it for
    ok: bool
    said: str  # "Answered", or the error


class RepeatFound(Model):
    batch: str
    title: str
    kind: str  # what Friday read it as
    calendar: str
    pattern: str  # "Every Mon, Wed and Fri, 12:20–13:10"
    count: int  # how many times within the planning horizon
    first: str | None  # the next one's start or due, local
    tag: str | None = None  # the course its title names, as a tag to start with ("CS 2110")


class MailOut(Model):
    id: int
    subject: str
    sender: str
    received: str
    status: Literal["read", "skipped", "failed", "waiting"]
    why: str | None  # why it was skipped or failed
    found: int  # suggestions it made


class GoogleCalendarOut(Model):
    id: str
    name: str
    primary: bool
    on: bool
    kind: str  # a kind's name, or "auto"
    trusted: bool
    last_sync: str | None
    error: str | None
    writable: bool = False  # Google lets you write to it
    editable: bool = False  # changes made in Friday are saved back to it
    account: str | None = None  # the Google account it's read through, or a Mac calendar's account
    also_google: bool = False  # a Mac calendar Friday also reads from Google, under the same name


class GoogleAccountOut(Model):
    """A connected Google account and what it lets Friday do."""

    email: str  # "" for the one signed in before Friday kept several, until the next sync finds its address
    gmail: bool  # lets Friday read its mail
    events: bool  # lets Friday save changes to its events
    mail_error: str | None = None  # why its mail couldn't be read last time


class GoogleConnectOut(Model):
    """Connecting Google from the app: how the sign-in started there is going, and what Google allows Friday."""

    state: Literal["idle", "waiting", "connected", "failed"]  # idle: no sign-in started since the server started
    message: str | None = None  # why it failed, in a sentence
    url: str | None = None  # while waiting: Google's page, to open again
    account: str | None = None  # the sign-in's account: the one asked for (None: any), the one it connected after
    client_file: bool  # the OAuth client JSON Friday signs in with is there
    calendar: bool  # some Google account is connected
    gmail: bool  # and one lets Friday read its mail
    events: bool  # and one lets Friday save changes to its events
    accounts: list[GoogleAccountOut] = []  # in the order you added them


class SourceOut(Model):
    id: int
    kind: str
    name: str
    trusted: bool
    enabled: bool
    last_sync: str | None
    last_error: str | None


class InboxOut(Model):
    suggestions: list[SuggestionOut]
    sources: list[SourceOut]
    llm: dict[str, Any]  # calls and tokens used today against the budget, and whether a key is set
    repeats: int = 0  # repeating calendar events waiting to be imported in Settings → Repeating


class TokenOut(Model):
    name: str
    scope: str
    created: str
    last_used: str | None


class MacWriteOut(Model):
    """A change to one of the Mac's events, for the Mac app to make through EventKit: its times (timed with an offset,
    or whole days with the end the day after the last) and, if you renamed it, its title; or a delete."""

    id: int
    op: Literal["save", "delete"]
    calendar: str  # EventKit's calendarIdentifier
    event: str  # the occurrence's id, as the Mac app sent it ("<identifier>@<occurrence start, Unix seconds>")
    title: str | None = None  # only when you renamed it in Friday: otherwise the calendar's own stays
    start: str | None = None
    end: str | None = None
    all_day: bool = False


class RuleReadOut(Model):
    reading: dict[str, Any] | None  # what the grammar read, with your overrides; None when it can't
    strength: str
    sentence: str
    effect: str
    conflicts: list["RuleConflict"] = []  # the switched-on rules it would contradict or overlap


class RuleConflict(Model):
    """Two rules at odds, found from the rules themselves (`planner/contradictions.py`)."""

    other: str  # the other rule's name
    other_sentence: str
    why: str  # "together they leave no time for deep work on Saturdays"
    days: list[str] = []  # the weekdays it bites on; empty for all of them
    overlap: bool = False  # the same kind of rule for the same work, not a contradiction: the stricter counts


class RuleOut(Model):
    name: str
    type: str
    sentence: str
    source: Literal["you", "learned", "default"]
    strength: str  # Prefer, Strongly or Always
    enabled: bool
    kept: str  # how often the current plan keeps it
    effect: str
    editable: bool  # strength can change (deadline rules always hold)
    background: bool = False  # the planner's own workings, folded away below the rules people tune
    wins_over: list[str] = []  # rules you said this one beats when they clash ("Which should win?")
    gives_way_to: list[str] = []  # rules you said beat this one
    contradicts: list[RuleConflict] = []  # switched-on rules this one can't be kept together with


class SetupOut(Model):
    """Setup's questions, answered with what Friday does now; `done` once you've been through them."""

    done: bool
    answers: dict[str, Any]  # SetupInput's fields, from the settings in effect
    events: dict[str, int] = {}  # each calendar's events in the next two weeks


class RuleClashOut(Model):
    """What a rule is up against, when the plan bends it: the rule that gives way when it's kept, on which days."""

    rule: str
    other: str | None  # None: it bends for deadlines, or nothing else would give
    days: list[str] = []  # ISO dates
    sentence: str = ""
    other_sentence: str = ""


class SeriesRow(Model):
    id: int
    title: str
    area: str | None
    fixed: bool  # a class or commitment at a set time, rather than flexible work
    pattern: str  # the repeat in words
    next: str | None  # the next open occurrence's start or due, local
    source: str  # "you", or the feed or calendar it came from
    active: bool
    external: bool = False  # it repeats in a calendar, which makes its times: changed there, not here


class DuplicateGroup(Model):
    key: str  # the words the copies share
    keep: int  # the copy Friday would keep: the most done, else one from a calendar it still reads, else the first
    items: list[ItemOut]


class DuplicatesOut(Model):
    groups: list[DuplicateGroup]
    sources: dict[int, str]  # where each copy came from: a calendar, mail, or you


class ToReviewOut(Model):
    items: list[ItemOut]
    sources: dict[int, str]
    started: bool  # a review is under way (Review again was pressed and not everything is checked yet)


class SleepNightOut(Model):
    date: str  # the evening's day
    bed: str | None = None  # local times
    up: str | None = None  # the next morning
    ready: str | None = None
    ready_timed: bool = False  # ready is the first timer you started, not a tap
    bed_id: int | None = None
    up_id: int | None = None
    ready_id: int | None = None
    slept_min: int | None = None
    planned_min: int  # the sleep your bedtime and wake time give that night
    planned_bed: str | None = None  # local: the bedtime and wake time set for that night
    planned_up: str | None = None
    routine_min: int | None = None


class SleepChangeOut(Model):
    days: list[str]
    field: Literal["bedtime", "wake"]
    now: str  # HH:MM
    learned: str


class SleepOut(Model):
    on: bool
    next: Literal["up", "ready", "bed"] | None = None  # the tap the Now bar offers now
    up: str | None = None  # this morning's, local
    ready: str | None = None
    nights: list[SleepNightOut] = []  # the last two weeks, newest first
    average_slept_min: int | None = None  # over the last seven recorded nights
    routine_min: dict[str, int] = {}  # learned, by the weekday of the morning
    changes: list[SleepChangeOut] = []  # learned times half an hour or more off the ones set
    suggested: dict[str, Any] | None = None  # the whole sleep setting with them, for `settings_set`
    recorded_nights: int = 0
    min_nights: int = 4
