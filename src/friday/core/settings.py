"""Settings: one validated model per key, defaults, and TOML export and import (DESIGN §17)."""

import re
import tomllib
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from friday.core.calendars import STARTER_CATEGORIES, BusySettings, CalendarLook, CategorySettings, check_colors
from friday.core.integrations import INTEGRATION_DEFAULTS, INTEGRATION_TYPES
from friday.core.pace import DEFAULT_PACES, Dials
from friday.core.presets import DEFAULT_PRESETS, Preset
from friday.core.textnorm import TextRules
from friday.core.time import WEEKDAYS, Clock, GridSpec

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def minutes_of(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def bedtime_minutes(bedtime: str, wake: str, day_start: int) -> int:
    """A bedtime as minutes from its evening's midnight: past 1440 when it's after midnight, as it is when it comes
    before the day starts (1am) or before you wake (4:30am, waking at noon: that's the next morning, not this one)."""
    bed = minutes_of(bedtime)
    return bed + 1440 if bed < day_start or bed < minutes_of(wake) else bed


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def check_hhmm(value: str) -> str:
    if not HHMM.match(value):
        raise ValueError(f"{value!r} is not a time like 04:00")
    return value


class TimeSettings(Model):
    timezone: str | None = None  # asked at first run
    day_start: str = "04:00"
    week_start: Weekday = "mon"
    horizon_days: int = Field(14, ge=1, le=28)
    fine_days: int = Field(7, ge=0, le=28)
    fine_slot_min: Literal[15, 30] = 15
    coarse_slot_min: Literal[15, 30, 60] = 30
    allocator_weeks: int = Field(12, ge=1, le=52)
    materialize_days: int = Field(120, ge=1)

    _check_day_start = field_validator("day_start")(check_hhmm)

    @field_validator("timezone")
    @classmethod
    def check_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError(f"unknown timezone {value!r}") from error
        return value

    def grid_spec(self) -> GridSpec:
        if self.timezone is None:
            raise ValueError("timezone: not set yet; run `fridayd init`")
        return GridSpec(
            timezone=self.timezone,
            day_start=minutes_of(self.day_start),
            week_start=WEEKDAYS.index(self.week_start),
            horizon_days=self.horizon_days,
            fine_days=self.fine_days,
            fine_slot_units=self.fine_slot_min // 15,
            coarse_slot_units=self.coarse_slot_min // 15,
        )


class StepBudget(Model):
    max_items: int
    cold: int
    warm: int


DEFAULT_MOVE_WEIGHTS = {
    "shift": 1.0,
    "far_shift": 1.5,
    "swap": 1.0,
    "split": 1.0,
    "merge": 1.0,
    "transfer": 1.0,
    "grow": 1.0,
    "shrink": 0.5,
    "insert": 1.0,
    "drop": 0.3,
    "eject": 0.5,
}


class EngineSettings(Model):
    stage_policy: Literal["lexpolish", "weighted", "strict"] = "lexpolish"
    weighted_ratio: float = Field(1000, gt=0)
    stage_weights: tuple[int, int, int] = (1_000_000, 1000, 1)
    seed: int = 0
    chains: int | None = Field(None, ge=1)  # None: performance cores − 1, detected at run time
    step_budgets: tuple[StepBudget, ...] = (
        StepBudget(max_items=20, cold=300_000, warm=150_000),
        StepBudget(max_items=60, cold=800_000, warm=300_000),
        StepBudget(max_items=150, cold=2_000_000, warm=600_000),
    )
    warm_t0: float = 0.01
    t0: float = 0.1
    t1: float = 0.003
    tabu_after_steps: int = 2_500_000
    repair_steps: int = 400_000
    fallback_threshold: int = 60
    fallback_s: float = 5
    fallback_overload_s: float = 15
    # A warm replan with work late starts from a plan that had the full overload search: 5 s finds what changed as
    # well as 15 did in the stress worlds (1 s didn't), so ticks and commands with work late take ~7 s, not ~20.
    fallback_overload_warm_s: float = 5
    fallback_warm_s: float = 1
    fallback_workers: int = 8
    move_weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_MOVE_WEIGHTS))
    scale: int = 100

    @field_validator("move_weights")
    @classmethod
    def check_moves(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != set(DEFAULT_MOVE_WEIGHTS) or min(value.values()) < 0:
            raise ValueError(f"needs a weight ≥ 0 for each of {', '.join(DEFAULT_MOVE_WEIGHTS)}")
        return value


class PlannerSettings(Model):
    debounce_s: float = 3
    cancel_after_s: float = 1
    assume_unreviewed: Literal["done", "not_done"] = "done"
    timer_hold_min: int = 30
    # A timer stopped sooner than this records nothing (7 Nov: "can you ignore work sessions less then 5 minutes").
    shortest_sitting_min: int = Field(5, ge=1, le=60)
    lock_conflict_tolerance: float = 1
    tentative_match_min: int = 30
    utilization: float = Field(0.8, gt=0, le=0.95)
    pacing_weight: float = Field(2, ge=0)


class ExecutorSettings(Model):
    swap_run_min: int = 30
    swap_count: int = 3
    soon_hours: float = 24
    notify_minutes: int = 120


class SleepDay(Model):
    bedtime: str  # a time before day_start means after midnight
    wake: str
    margin_min: int = Field(ge=0, le=240)

    _check_times = field_validator("bedtime", "wake")(check_hhmm)


class EventKind(Model):
    before_min: int = Field(0, ge=0)
    after_min: int = Field(0, ge=0)


class RuleSpec(Model):
    type: str
    name: str
    weight: float = Field(1.0, ge=0)
    stage: Literal["deadlines", "wellbeing", "preferences"] | None = None
    scope: dict[str, Any] | None = None
    reason: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True  # switched off in Rules, kept for when you switch it back


def rule(type: str, name: str, weight: float = 1.0, **params: Any) -> RuleSpec:
    return RuleSpec(type=type, name=name, weight=weight, params=params)


NOT_ROUTINES = {"except_preset": ["Routine"]}
REFERENCE_RULES = (
    rule("late_work", "late_work", 10, overflow_extra_hours=48),
    # personal's (COMBINED.md 49): each late task counts, and lateness costs more the later it is.
    rule("late_tasks", "late_tasks", 10, hours=48, square_hours=96),
    rule("quota", "quota", 3),
    # Meals and other routines aren't work: counted as load, any wellbeing cost outweighed a whole meal (M16).
    RuleSpec(
        type="late_night",
        name="late_night",
        scope=NOT_ROUTINES,
        params={"gradient_start": "22:00", "a": 2, "b": 20, "debt_factor": 0.5},
    ),
    # Reading too (light work): a 5-hour reading in one go was as long as any problem set allowed to run (M15).
    RuleSpec(
        type="deep_run", name="deep_run", weight=4, scope={"energy": ["deep", "light"]}, params={"threshold": "3h"}
    ),
    RuleSpec(
        type="reserve",
        name="weekday_evenings",
        weight=2,
        scope=NOT_ROUTINES,
        params={"days_except": ["sat", "sun"], "start": "18:00", "end": "23:00", "free": "2h"},
    ),
    RuleSpec(
        type="reserve",
        name="weekends",
        weight=2,
        scope=NOT_ROUTINES,
        params={"days": ["sat", "sun"], "start": "10:00", "end": "23:00", "free": "4h"},
    ),
    RuleSpec(type="daily_load", name="daily_load", weight=5, scope=NOT_ROUTINES, params={"threshold": "8h"}),
    # A preference, not wellbeing: there, evening out a day by half an hour beat keeping work in one sitting, and a
    # heavy week's 2-hour readings were cut into scraps to hold every day at 3 hours (M15).
    RuleSpec(type="even_load", name="even_load", weight=1, stage="preferences"),
    rule("energy", "energy", 1),
    rule("soft_late", "soft_late", 3),
    rule("unscheduled", "unscheduled", 0.5, base=1),
    rule("chunk_cost", "chunk_cost", 10),
    # Off until you set a buffer (Settings → Schedule, or per tag and kind): 0 minutes makes no measures.
    rule("buffer", "buffer", 3, minutes="0m", by_area={}, by_preset={}),
    rule("spread", "spread", 3),
    rule("cluster", "cluster", 3, per_day=2),
    # One course for a stretch (8 Nov: "math for the entire time not 3 different things"), a count per switch.
    rule("same_course", "same_course", 2),
    rule("target_shortfall", "target_shortfall", curve=[[0.4, 8], [1.0, 3]]),
    rule("elastic_shortfall", "elastic_shortfall", steep=20, gentle=2),
    # A meal below its minimum is a skipped meal: wellbeing, which a preference lost to every evening kept free. Its
    # ideal length stays a preference above, or a 60-minute dinner beat keeping work in one sitting (M16).
    RuleSpec(type="elastic_shortfall", name="elastic_minimum", stage="wellbeing", params={"steep": 20, "gentle": 0}),
    rule("open_value", "open_value", curve=[[0.5, 1], [1.0, 0.5]]),
    # With nothing else to choose between free hours, work landed on its due evening while side projects took the
    # days before; a day's lead costs nothing else. Exam prep belongs in the days just before the exam (M15).
    RuleSpec(
        type="finish_early", name="finish_early", weight=1, scope={"except_preset": ["Exam prep"]}, params={"days": 1}
    ),
    # In the wellbeing stage, not its type's default (preferences): there, any wellbeing gain outweighed keeping the
    # plan, and replans reshuffled hours of work for nothing (PROGRESS decision 120).
    RuleSpec(
        type="minimize_changes",
        name="minimize_changes",
        weight=1,
        stage="wellbeing",
        params={"preferred_multiplier": 10},
    ),
)


class TemplateStep(Model):
    """One child of a project made from a template: its share of the project's hours, in order."""

    title: str
    share: float = Field(gt=0)
    preset: str | None = None


DEFAULT_TEMPLATES = {
    "Essay": (TemplateStep(title="Outline", share=0.15), TemplateStep(title="Draft", share=0.5),
              TemplateStep(title="Revise", share=0.35)),
    "Presentation": (TemplateStep(title="Research", share=0.4), TemplateStep(title="Slides", share=0.4),
                     TemplateStep(title="Rehearse", share=0.2)),
}  # fmt: skip


class PaceSettings(Model):
    default: str = "Normal"
    weekly: dict[str, str] = {}  # weekday → pace, every week ("go easier on Saturdays"): {"sat": "Easy"}
    switch_stability: float = Field(0.2, ge=0, le=1)


class LearnSettings(Model):
    weights: Literal["off", "suggest", "auto"] = "suggest"
    durations: Literal["off", "suggest", "auto"] = "suggest"  # learned lengths (§21.7)
    energy: Literal["off", "suggest", "auto"] = "suggest"  # learned good and bad hours (§21.7)
    drag_weight: float = 3
    prior_sd: float = 1
    theta_min: float = 0.02
    answer_scale: float = 0.05
    state_inference: Literal["off", "on"] = "off"
    state_gate_nats: float = 2
    proposals: Literal["off", "ask"] = "ask"
    proposal_from_week: int = 6
    proposal_every_weeks: int = 2
    proposal_min_gain: float = 0.114
    proposal_min_comparisons: int = 40  # fewer answers give false proposals (M9 measurements, PROGRESS decision 119)
    questions_per_day: int = 3  # one-tap comparisons in the evening review; §21.4 had 2 a week, too few to learn
    questions_per_week: int = 15
    query_stop_disagreement: float = 0.2


class FadingLate(Model):
    """Work that matters less the longer it's overdue (3 Nov: "have the importance of doing a reading on time
    deteriorate as time goes on"; "Half every 3 days", and once faded it stays, planned only in spare time). Its
    importance halves every `half_life_days` it is late, so a reading a week late gives way to work still on time,
    where by default the later work is, the more urgent it gets. Pointless once late (`pointless_late`) wins over it."""

    kinds: tuple[str, ...] = ()
    titles: tuple[str, ...] = ()  # patterns (regular expressions, any case)
    half_life_days: float = Field(3.0, gt=0, le=60)

    def covers(self, preset: str | None, title: str) -> bool:
        if preset in self.kinds:
            return True
        return any(_matches(pattern, title) for pattern in self.titles)

    def factor(self, overdue_min: float) -> float:
        """What's left of its importance after `overdue_min` minutes late: 1 on time, ½ one half-life late."""
        return 0.5 ** (max(0.0, overdue_min) / (self.half_life_days * 1440))


class PointlessLate(Model):
    """Work that's pointless once its deadline has passed (COMBINED.md 50): never planned after it."""

    kinds: tuple[str, ...] = ("Exam prep",)  # prep for an exam is no use after the exam
    titles: tuple[str, ...] = ()  # patterns (regular expressions, any case), from rules like "no point … after …"

    def covers(self, preset: str | None, title: str) -> bool:
        if preset in self.kinds:
            return True
        return any(_matches(pattern, title) for pattern in self.titles)


def _matches(pattern: str, title: str) -> bool:
    try:
        return re.search(pattern, title, re.IGNORECASE) is not None
    except re.error:
        return False


class ExamFocus(Model):
    """personal's exam focus (COMBINED.md 38): in the days before an exam, other courses' work that is due after it
    waits until the exam is over, when a day and half again its length are left before its own due. Off until you ask
    for it, in Rules ("I want to focus on an exam before it")."""

    on: bool = False
    days_before: int = Field(3, ge=1, le=14)
    words: tuple[str, ...] = ("exam", "prelim", "midterm", "final")

    def finds(self, title: str) -> bool:
        """Whether a title is an exam's: one of the words in it, as a word. No words (or blank ones) find nothing: an
        empty pattern matched every event, so every event was an exam (audit, 12 Nov)."""
        said = [w.strip() for w in self.words if w.strip()]
        if not said:
            return False
        return re.search(r"\b(" + "|".join(re.escape(w) for w in said) + r")\b", title, re.IGNORECASE) is not None


class PhoneAccess(Model):
    """Friday on your phone over Tailscale (C61): off, Friday answers on this Mac alone; on, also at its Tailscale
    address, to phones you've paired (Settings → Phone)."""

    on: bool = False


class MealTracking(Model):
    """Recording your meals (Sleep & meals): off until you turn it on. When on, the Now bar offers "Eating now" around
    mealtimes and "Done eating" while you eat, and Friday learns when you eat, for how long and what you skip
    (`learn/meals.py`); a meal's real length is offered for its routine, never changed without a yes."""

    on: bool = False
    min_days: int = Field(4, ge=2, le=30)  # days of a meal a weekday group needs before Friday says what's usual


class SleepTracking(Model):
    """Recording your sleep (Settings → Schedule): off until you turn it on. When on, the Now bar has one-tap "I'm up",
    "Ready to work" and "Going to bed", and Friday learns from them (`learn/sleep.py`): your real bedtime and wake time
    (offered, never changed without a yes), your morning routine (kept light) and your sleep debt."""

    on: bool = False
    min_nights: int = Field(4, ge=2, le=30)  # recorded nights a weekday group needs before Friday suggests times
    morning_hours: float = Field(4.0, ge=1, le=8)  # how long after waking "Ready to work" stays on offer


class Sittings(Model):
    """personal's split preference (COMBINED.md 38): "I like to do things in one go, but split problem sets first".
    `one_go` makes splitting cost `factor` times more, except for the kinds in `split_first`, which cost half."""

    one_go: bool = False
    split_first: tuple[str, ...] = ()
    factor: float = Field(3.0, ge=1, le=10)


class TextSettings(Model):
    abbreviations: dict[str, str] = Field(
        default_factory=lambda: {
            "ps": "problem set",
            "pset": "problem set",
            "hw": "homework",
            "ch": "chapter",
            "chap": "chapter",
            "lec": "lecture",
            "assn": "assignment",
            "proj": "project",
        }
    )
    numbered_words: tuple[str, ...] = (
        "part", "chapter", "unit", "week", "lecture", "lab", "homework", "set", "exam", "midterm", "quiz",
        "project", "assignment", "module", "section", "volume", "book", "phase", "session", "lesson",
    )  # fmt: skip
    stopwords: tuple[str, ...] = ("a", "an", "the", "of", "for", "on", "to")

    def rules(self) -> TextRules:
        return TextRules(self.abbreviations, frozenset(self.numbered_words), frozenset(self.stopwords))


class EstimateSettings(Model):
    window_days: int = 365
    area_bonus: float = 0.2
    min_similarity: float = 0.6
    k: int = 5
    min_samples: int = 3
    bias_window: int = 20
    bias_min_samples: int = 5
    bias_threshold: float = 1.15
    bias_consistency: float = 0.7
    cushion: bool = True  # plan your estimates at how far over you consistently run (COMBINED.md 41)
    cushion_cap: float = Field(2.0, ge=1)


class NotifySettings(Model):
    """What notifications left when they were removed (27 Oct: "remove notifications"): the morning brief's switch,
    and the address your phone reaches Friday at, for the links in the Friday calendar's events. A setting saved
    before then (its channels, quiet hours, kinds) still reads: what's gone is dropped, and its brief switch kept."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    app_url: str | None = None  # e.g. a tailnet https URL
    morning_brief: bool = True  # open the brief with Friday's first look each morning

    @model_validator(mode="before")
    @classmethod
    def brief_from_before(cls, value: Any) -> Any:
        if isinstance(value, dict) and "morning_brief" not in value and isinstance(value.get("types"), dict):
            return {**value, "morning_brief": value["types"].get("morning_brief", True)}
        return value


class JobsSettings(Model):
    nightly_replan_at: str = "03:30"
    tick_replan_min: int = 15
    backup_keep: int = 14

    @field_validator("nightly_replan_at")
    @classmethod
    def a_time(cls, value: str) -> str:
        """A clock time, "03:30" or "3:30": the job loop reads it before each pass, and "noon" stopped every job until
        Friday started again (audit, 12 Nov)."""
        if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", value):
            raise ValueError(f"{value!r} is not a time like 03:30")
        return value


class ServerSettings(Model):
    port: int = 8765
    data_dir: str = "~/.local/share/friday"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    allow_plugins: bool = True


class UpdateSettings(Model):
    """When a downloaded update is swapped in (HOSTED.md H146): right away, or when you quit Friday."""

    restart: Literal["now", "quit"] = "now"


SETTINGS_TYPES: dict[str, Any] = {
    "time": TimeSettings,
    # the clock every time is shown on (Settings → Appearance → Clock): the app, the server's sentences, the command
    # line and Siri; a key of its own, so a friday.toml that sets [time] leaves it yours to change in the app
    "clock": Clock,
    "engine": EngineSettings,
    "planner": PlannerSettings,
    "executor": ExecutorSettings,
    "sleep": dict[Weekday, SleepDay] | None,  # set at first run
    "daily_cap": dict[Weekday, float],
    "event_kinds": dict[str, EventKind],
    "presets": dict[str, Preset],
    "kind_order": tuple[str, ...],  # presets, most important first: who gets the time when it can't all fit
    "short_term_first": bool,  # the Short term list's work comes before anything on the Long term list
    "school": bool,  # in school (Setup asks, C97): school kinds and schoolwork shown and guessed; off, never
    "mac_plan": bool,  # the plan as a "Friday" calendar on this Mac, in iCloud, so the iPhone shows it (C113)
    "sleep_tracking": SleepTracking,
    "meal_tracking": MealTracking,
    "phone": PhoneAccess,  # Friday on your phone over Tailscale (C61)
    "rules": tuple[RuleSpec, ...],
    "templates": dict[str, tuple[TemplateStep, ...]],
    "paces": dict[str, Dials],
    "pace": PaceSettings,
    "energy_map": tuple[tuple[float, ...], ...],
    "learn": LearnSettings,
    "text": TextSettings,
    "estimate": EstimateSettings,
    "notify": NotifySettings,
    "jobs": JobsSettings,
    "server": ServerSettings,
    "updates": UpdateSettings,  # Friday's own updater (HOSTED.md H146)
    "notes": tuple[str, ...],  # what you've told Friday about yourself, read by the AI with everything it reads
    "categories": CategorySettings,  # events colored by their titles, and the filter (COMBINED.md 17, 59)
    "busy": BusySettings,  # which events count as busy when planning (COMBINED.md 28)
    "pointless_late": PointlessLate,  # work never planned after its due (COMBINED.md 50)
    "fading_late": FadingLate,  # work that matters less the longer it's overdue (3 Nov)
    "exam_focus": ExamFocus,  # other courses wait while you prepare for an exam (COMBINED.md 38)
    "sittings": Sittings,  # one go, and which kinds to split first (COMBINED.md 38)
    "calendar_look": CalendarLook,  # each calendar's pigment and toolbar button (COMBINED.md 17, 19)
    **INTEGRATION_TYPES,
}
ADAPTERS = {key: TypeAdapter(kind) for key, kind in SETTINGS_TYPES.items()}
MAX_NOTES, MAX_NOTE_CHARS = 40, 300

DEFAULTS: dict[str, Any] = {
    "time": TimeSettings(),
    "clock": "12h",
    "engine": EngineSettings(),
    "planner": PlannerSettings(),
    "executor": ExecutorSettings(),
    "sleep": None,
    "daily_cap": dict.fromkeys(WEEKDAYS, 10.0),
    "event_kinds": {
        "class": EventKind(before_min=10, after_min=10),
        "meeting": EventKind(before_min=5, after_min=5),
        "exam": EventKind(before_min=15),
        "shove": EventKind(),
        "other": EventKind(),
    },
    "presets": DEFAULT_PRESETS,
    "kind_order": (),
    "short_term_first": False,
    "school": True,  # Friday began as a student's; Setup asks anyone new (C97)
    "mac_plan": False,  # off until you switch it on in its box
    "sleep_tracking": SleepTracking(),
    "meal_tracking": MealTracking(),
    "phone": PhoneAccess(),
    "rules": REFERENCE_RULES,
    "templates": DEFAULT_TEMPLATES,
    "paces": DEFAULT_PACES,
    "pace": PaceSettings(),
    "energy_map": tuple((0.0,) * 48 for _ in WEEKDAYS),
    "learn": LearnSettings(),
    "text": TextSettings(),
    "estimate": EstimateSettings(),
    "notify": NotifySettings(),
    "jobs": JobsSettings(),
    "server": ServerSettings(),
    "updates": UpdateSettings(),
    "notes": (),
    "categories": CategorySettings(categories=STARTER_CATEGORIES),
    "busy": BusySettings(),
    "pointless_late": PointlessLate(),
    "fading_late": FadingLate(),
    "exam_focus": ExamFocus(),
    "sittings": Sittings(),
    "calendar_look": CalendarLook(),
    **INTEGRATION_DEFAULTS,
}


def validate_value(key: str, value: Any) -> Any:
    """The validated value for one key; raises ValueError naming the key and field."""
    if key not in ADAPTERS:
        raise ValueError(f"{key}: no such settings key")
    try:
        parsed = ADAPTERS[key].validate_python(value)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in (key, *first["loc"]))
        raise ValueError(f"{where}: {first['msg']}") from error
    check_whole_value(key, parsed)
    return parsed


def check_whole_value(key: str, value: Any) -> None:
    if key == "sleep" and value is not None and set(value) != set(WEEKDAYS):
        raise ValueError("sleep: needs every weekday")
    if key == "daily_cap" and (set(value) != set(WEEKDAYS) or min(value.values()) < 0):
        raise ValueError("daily_cap: needs hours ≥ 0 for every weekday")
    if key == "energy_map" and (len(value) != 7 or any(len(row) != 48 or min(row) < 0 for row in value)):
        raise ValueError("energy_map: needs 7 rows of 48 half-hour prices ≥ 0")
    if key == "templates" and any(not steps for steps in value.values()):
        raise ValueError("templates: each needs at least one step")
    if key == "notes" and (len(value) > MAX_NOTES or any(len(n) > MAX_NOTE_CHARS or not n.strip() for n in value)):
        raise ValueError(f"notes: at most {MAX_NOTES}, each 1–{MAX_NOTE_CHARS} characters")
    if key == "rules" and len({r.name for r in value}) != len(value):
        raise ValueError("rules: names must be unique")
    if key in ("categories", "calendar_look"):
        check_colors(value)


def to_json(key: str, value: Any) -> Any:
    return ADAPTERS[key].dump_python(value, mode="json")


def export_toml(values: dict[str, Any]) -> str:
    document = {key: drop_none(to_json(key, values[key])) for key in SETTINGS_TYPES if values.get(key) is not None}
    return tomli_w.dumps(document)


def import_toml(text: str) -> dict[str, Any]:
    """Every key from TOML, validated before anything is returned; keys left out keep their defaults."""
    document = tomllib.loads(text)
    unknown = set(document) - set(SETTINGS_TYPES)
    if unknown:
        raise ValueError(f"{sorted(unknown)[0]}: no such settings key")
    return DEFAULTS | {key: validate_value(key, value) for key, value in document.items()}


def drop_none(value: Any) -> Any:
    # TOML has no null; a missing key reads back as the model's default, which is None for these fields.
    if isinstance(value, dict):
        return {k: drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_none(v) for v in value]
    return value
