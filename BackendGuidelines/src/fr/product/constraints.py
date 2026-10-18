"""Typed constraints: what the LLM must produce from the user's text, and how each one becomes engine input.

The LLM never plans. It maps text onto these types; the user confirms the paraphrase; the stored constraint is
compiled here, deterministically, into the engine's own vocabulary (sleep settings, buffers, fixed events, item facets,
extra rules). Hard constraints become walls (forbidden slots, chunk limits, earlier deadlines, the daily cap); soft ones
become rule weights at three strengths.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.builder import ItemSpec, spec as make_spec
from ..core.generate import Scenario
from ..core.settings import WEEKDAYS, Sleep
from . import clock

Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Strength = Literal["hard", "strong", "medium", "mild"]
Kind = Literal["assignment", "reading", "project", "exam_prep", "errand", "chore", "routine", "habit", "goal",
               "side_project"]
_CLOCK = re.compile(r"^([01]?\d|2[0-4]):[0-5]\d$")

# Soft strengths, in points per hour (prices) or as weights (measures). The reference's own soft rules sit at 1-10.
PRICE = {"mild": 1.0, "medium": 3.0, "strong": 8.0}
WEIGHT = {"mild": 1.0, "medium": 3.0, "strong": 8.0}


def _clock_ok(v: str | None) -> str | None:
    if v is not None and not _CLOCK.match(v):
        raise ValueError(f"time must be HH:MM (24 h), got {v!r}")
    return v


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field("", description="the words of the user's text this constraint comes from")
    paraphrase: str = Field("", description="one short sentence restating it, shown to the user to confirm")


class Target(BaseModel):
    """Which flexible items a constraint is about. Every field empty = all flexible work."""

    model_config = ConfigDict(extra="forbid")
    courses: list[str] | None = Field(None, description="course / area names exactly as listed in the context")
    kinds: list[Kind] | None = None
    titles: list[str] | None = Field(None, description="case-insensitive substrings of task titles")
    energy: list[Literal["deep", "light", "physical"]] | None = None

    def is_all(self) -> bool:
        return not (self.courses or self.kinds or self.titles or self.energy)

    def matches(self, s: ItemSpec) -> bool:
        if self.courses and s.area not in self.courses:
            return False
        if self.kinds and s.preset not in self.kinds:
            return False
        if self.titles and not any(t.lower() in s.title.lower() for t in self.titles):
            return False
        if self.energy and s.energy not in self.energy:
            return False
        return True

    def scope(self) -> dict | None:
        if self.is_all():
            return None
        out: dict = {}
        if self.courses:
            out["area"] = list(self.courses)
        if self.kinds:
            out["preset"] = list(self.kinds)
        if self.energy:
            out["energy"] = list(self.energy)
        if self.titles:
            out["title_regex"] = ["(?i)" + re.escape(t) for t in self.titles]
        return out


class Window(_Base):
    days: list[Day] | None = Field(None, description="null = every day")
    start: str | None = Field(None, description="HH:MM, 24 h; null = start of day")
    end: str | None = Field(None, description="HH:MM, 24 h, may be earlier than start (wraps midnight); null = end of day")

    _c1 = field_validator("start", "end")(classmethod(lambda cls, v: _clock_ok(v)))


class SleepC(_Base):
    """Usual bedtime and wake time. The engine never schedules inside the sleep core."""

    kind: Literal["sleep"] = "sleep"
    nights: list[Day] | None = Field(None, description="nights that start on these days; null = every night")
    bedtime: str | None = Field(None, description="HH:MM; after midnight is fine (01:30)")
    wake: str | None = Field(None, description="HH:MM the next morning")

    _c = field_validator("bedtime", "wake")(classmethod(lambda cls, v: _clock_ok(v)))


class AvoidTime(Window):
    """Don't schedule (hard) or prefer not to schedule (soft) the target's work in this window."""

    kind: Literal["avoid_time"] = "avoid_time"
    strength: Strength = "hard"
    target: Target = Field(default_factory=Target)


class PreferTime(Window):
    """Prefer to do the target's work in this window (soft): time elsewhere costs a little."""

    kind: Literal["prefer_time"] = "prefer_time"
    strength: Literal["strong", "medium", "mild"] = "medium"
    target: Target = Field(default_factory=Target)


class Commitment(_Base):
    """A recurring or one-off fixed event that blocks time (gym, job, practice, commute)."""

    kind: Literal["commitment"] = "commitment"
    title: str
    days: list[Day] | None = Field(None, description="weekly on these days; null with dates = one-off")
    dates: list[str] | None = Field(None, description="YYYY-MM-DD for one-off or irregular dates")
    start: str
    end: str
    event_kind: Literal["class", "meeting", "other"] = "other"

    _c = field_validator("start", "end")(classmethod(lambda cls, v: _clock_ok(v)))


class DailyLimit(_Base):
    """At most `hours` of the target's work per day."""

    kind: Literal["daily_limit"] = "daily_limit"
    hours: float = Field(gt=0, le=24)
    days: list[Day] | None = None
    strength: Strength = "strong"
    target: Target = Field(default_factory=Target)


class KeepFree(_Base):
    """Keep at least `hours` free of scheduled work in this window."""

    kind: Literal["keep_free"] = "keep_free"
    days: list[Day] | None = None
    start: str | None = None
    end: str | None = None
    hours: float = Field(gt=0, le=24)
    strength: Literal["strong", "medium", "mild"] = "medium"

    _c = field_validator("start", "end")(classmethod(lambda cls, v: _clock_ok(v)))


class SessionLength(_Base):
    """Bounds on one sitting of the target's work."""

    kind: Literal["session_length"] = "session_length"
    min_hours: float | None = Field(None, gt=0, le=12)
    max_hours: float | None = Field(None, gt=0, le=12)
    strength: Strength = "hard"
    target: Target = Field(default_factory=Target)


class OneSitting(_Base):
    kind: Literal["one_sitting"] = "one_sitting"
    target: Target


class Pacing(_Base):
    """spread: a bit every day; cluster: few long days; batch: same course on the same day."""

    kind: Literal["pacing"] = "pacing"
    style: Literal["spread", "cluster", "batch_by_course"]
    target: Target = Field(default_factory=Target)


class FinishEarly(_Base):
    """Finish the target's work `days` before it is due."""

    kind: Literal["finish_early"] = "finish_early"
    days: float = Field(gt=0, le=14)
    strength: Strength = "medium"
    target: Target = Field(default_factory=Target)


class Buffer(_Base):
    """Minutes kept clear before / after a kind of event (walking to class, winding down after a meeting)."""

    kind: Literal["buffer"] = "buffer"
    event_kind: Literal["class", "meeting", "other"]
    before_min: int = Field(0, ge=0, le=180)
    after_min: int = Field(0, ge=0, le=180)


class Order(_Base):
    """Finish `first` before starting `then` (title substrings of two tasks)."""

    kind: Literal["order"] = "order"
    first: str
    then: str


Constraint = Annotated[Union[SleepC, AvoidTime, PreferTime, Commitment, DailyLimit, KeepFree, SessionLength, OneSitting,
                             Pacing, FinishEarly, Buffer, Order], Field(discriminator="kind")]


class Unsupported(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    reason: str


class Parse(BaseModel):
    """The whole reply: constraints, things Friday can't express, and questions when the text is ambiguous."""

    model_config = ConfigDict(extra="forbid")
    constraints: list[Constraint] = Field(default_factory=list)
    unsupported: list[Unsupported] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list, description="ask instead of guessing")


# ---------------------------------------------------------------- compile


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _days(days: list[str] | None) -> list[int]:
    return list(range(7)) if not days else sorted({WEEKDAYS.index(d) for d in days})


def _units(hours: float) -> str:
    return f"{int(round(hours * 60))}m"


def apply(sc: Scenario, constraints: list[Constraint]) -> tuple[Scenario, list[str]]:
    """A new scenario with the constraints compiled in, plus notes on anything that could not be applied."""
    out = sc.copy()
    notes: list[str] = []
    rules = out.extra_rules
    ids = max((s.id for s in out.specs), default=0)
    flexible = [s for s in out.specs if s.when != "fixed"]
    for k, c in enumerate(constraints):
        name = f"user:{k}:{c.kind}"
        if isinstance(c, SleepC):
            bed, wake = list(out.settings.sleep.bedtime), list(out.settings.sleep.wake)
            for wd in _days(c.nights):
                if c.bedtime:
                    b = _mins(c.bedtime)
                    bed[wd] = b + 1440 if b < 12 * 60 else b
                if c.wake:
                    wake[(wd + 1) % 7] = _mins(c.wake)
            out.settings = replace(out.settings, sleep=Sleep(tuple(bed), tuple(wake), out.settings.sleep.margin))
        elif isinstance(c, (AvoidTime, PreferTime)):
            if isinstance(c, AvoidTime):
                price = "forbid" if c.strength == "hard" else PRICE[c.strength]
                rules.append(dict(type="time_preference", name=name, stage="preferences", scope=c.target.scope(),
                                  params=dict(days=c.days, start=c.start, end=c.end, price=price)))
            else:  # everything outside the window costs a little
                if c.start or c.end:
                    rules.append(dict(type="time_preference", name=name + ":outside", scope=c.target.scope(),
                                      params=dict(days=c.days, start=c.end or "00:00", end=c.start or "24:00",
                                                  price=PRICE[c.strength])))
                if c.days:
                    rules.append(dict(type="time_preference", name=name + ":other_days", scope=c.target.scope(),
                                      params=dict(days_except=c.days, price=PRICE[c.strength])))
        elif isinstance(c, Commitment):
            s0, e0 = _mins(c.start), _mins(c.end)
            e0 = e0 + 1440 if e0 <= s0 else e0
            first = out.now // 1440 - 1
            dates = [clock.parse(d) // 1440 for d in c.dates] if c.dates else []
            if c.days:
                wds = _days(c.days)
                dates += [d for d in range(first, first + out.settings.horizon_days + 2) if d % 7 in wds]
            if not dates:
                notes.append(f"{name}: no days or dates; not added")
            for d in sorted(set(dates)):
                ids += 1
                out.specs.append(make_spec("commitment", ids, c.title, start=d * 1440 + s0, end=d * 1440 + e0,
                                           event_kind=c.event_kind))
        elif isinstance(c, DailyLimit):
            if c.strength == "hard" and c.target.is_all() and not c.days:
                out.settings = replace(out.settings, day_cap_units=min(out.settings.day_cap_units, round(c.hours * 4)))
            else:
                if c.strength == "hard":
                    notes.append(f"{name}: a hard limit on part of the work or some days is applied as a strong preference")
                rules.append(dict(type="daily_load", name=name, scope=c.target.scope(),
                                  weight=WEIGHT["strong" if c.strength == "hard" else c.strength],
                                  params=dict(threshold=_units(c.hours))))
                if c.days:
                    notes.append(f"{name}: daily limits apply every day (the engine's daily_load has no day filter)")
        elif isinstance(c, KeepFree):
            rules.append(dict(type="reserve", name=name, weight=WEIGHT[c.strength],
                              params=dict(days=c.days, start=c.start, end=c.end, free=_units(c.hours))))
        elif isinstance(c, SessionLength):
            hit = [s for s in flexible if c.target.matches(s)]
            if c.strength == "hard":
                for s in hit:
                    if c.max_hours:
                        s.max_chunk_min = int(round(c.max_hours * 60))
                        s.min_chunk_min = min(s.min_chunk_min, s.max_chunk_min)
                    if c.min_hours:
                        s.min_chunk_min = int(round(c.min_hours * 60))
                        if s.max_chunk_min:
                            s.max_chunk_min = max(s.max_chunk_min, s.min_chunk_min)
            elif c.max_hours:
                rules.append(dict(type="deep_run", name=name, weight=WEIGHT[c.strength], scope=c.target.scope() or {},
                                  params=dict(threshold=_units(c.max_hours))))
            if c.strength != "hard" and c.min_hours:
                for s in hit:
                    s.chunk_cost = max(s.chunk_cost, 0.2)
                notes.append(f"{name}: a soft minimum session is applied as a higher cost per session")
            if not hit and not c.target.is_all():
                notes.append(f"{name}: no current task matches; it applies to future ones")
        elif isinstance(c, OneSitting):
            for s in flexible:
                if c.target.matches(s) and s.amount == "fixed":
                    s.shape = "one_sitting"
        elif isinstance(c, Pacing):
            if c.style == "batch_by_course":
                rules.append(dict(type="batch_by_day", name=name, weight=2.0, scope=c.target.scope(), params=dict(by="area")))
            else:
                for s in flexible:
                    if c.target.matches(s) and s.amount == "fixed":
                        s.spread = c.style
        elif isinstance(c, FinishEarly):
            if c.strength == "hard":
                for s in flexible:
                    if c.target.matches(s) and s.due is not None:
                        s.due = s.due - int(c.days * 1440)
            else:
                rules.append(dict(type="finish_early", name=name, weight=WEIGHT[c.strength], scope=c.target.scope(),
                                  params=dict(days=c.days)))
        elif isinstance(c, Buffer):
            b = dict(out.settings.buffers)
            old = b.get(c.event_kind, (0, 0))
            b[c.event_kind] = (max(old[0], c.before_min), max(old[1], c.after_min))
            out.settings = replace(out.settings, buffers=b)
        elif isinstance(c, Order):
            a = [s for s in flexible if c.first.lower() in s.title.lower()]
            b = [s for s in flexible if c.then.lower() in s.title.lower()]
            if len(a) != 1 or len(b) != 1:
                notes.append(f"{name}: '{c.first}' matches {len(a)} tasks and '{c.then}' {len(b)}; need exactly one each")
            elif a[0].id != b[0].id and not any(d[0] == a[0].id for d in b[0].deps):
                b[0].deps = b[0].deps + ((a[0].id, 1.0, 0),)
    return out, notes
