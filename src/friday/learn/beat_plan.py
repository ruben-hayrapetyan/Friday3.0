"""Work a plan showed late that you finished on time anyway (2 Nov: "it consistently proposes schedules that have
things late but i don't do anything late (which means that I schedule my time differently then it proposes)").
Pure: no database or clock.

Late work in Friday's plan that you finish on time means Friday had your time wrong. Each such finish is read for
where its time came from, by what you recorded:

- faster: it took under `FASTER` of the length Friday planned;
- nights: you worked inside a night Friday keeps free (from bedtime's margin to waking), its evening half;
- mornings: the same night's morning half;
- events: you worked through an event Friday counted as busy;
- daytime: recorded, but at your usual speed in time Friday plans in (something else gave way);
- untold: nothing recorded says how.

What happens in `MIN_CASES` finishes is offered as a change, never made on its own: nights reached into on the
evenings it happened become planning time (their margin grows), and a kind you finish faster is planned at the
share of its length you take. Mornings, events and daytime are reported only: no setting says them better.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median

from friday.core.time import WEEKDAYS

FASTER = 0.8  # under this share of the planned length is faster
MIN_CASES = 3  # finishes before a pattern is offered
MIN_MIN = 15  # minutes inside a night or an event before they count
SHARE_FLOOR = 0.5  # a kind is never planned at less than half its length
MARGIN_MAX = 240  # the most a night's margin can be (settings' SleepDay)
QUARTER = 15

Span = tuple[int, int]  # UTC minutes, end excluded


@dataclass(frozen=True)
class Night:
    """A night Friday keeps free: from bedtime's margin (`start`) until waking (`end`)."""

    evening: str  # the weekday the night begins on
    start: int
    end: int


@dataclass(frozen=True)
class Event:
    title: str
    start: int
    end: int


@dataclass(frozen=True)
class Finish:
    """Work a saved plan showed late, finished by its due."""

    item_id: int
    title: str
    kind: str | None  # its preset
    planned_min: int | None  # the length Friday planned it at
    actual_min: int | None  # what you recorded, when you did
    worked: tuple[Span, ...] = ()  # recorded sittings with their times
    scalable: bool = False  # its length is yours or the kind's (Friday's own estimates learn from your times)


@dataclass(frozen=True)
class How:
    """Where one finish's time came from."""

    finish: Finish
    speed: float | None  # actual ÷ planned
    evening_min: int  # inside nights, their evening half
    morning_min: int  # inside nights, their morning half
    event_min: int
    reach: Mapping[str, int] = field(default_factory=dict)  # evening → minutes past its night's start, at most
    events: tuple[str, ...] = ()  # worked through, at least `MIN_MIN` each

    @property
    def ways(self) -> tuple[str, ...]:
        """faster, nights, mornings, events; else daytime when anything was recorded, else untold."""
        found = tuple(
            name
            for name, yes in (
                ("faster", self.speed is not None and self.speed < FASTER),
                ("nights", self.evening_min >= MIN_MIN),
                ("mornings", self.morning_min >= MIN_MIN),
                ("events", self.event_min >= MIN_MIN),
            )
            if yes
        )
        if found:
            return found
        return ("daytime",) if self.speed is not None or self.finish.worked else ("untold",)


@dataclass(frozen=True)
class LaterNights:
    """Offer: the margins those evenings would have (minutes past bedtime Friday may plan in)."""

    margins: Mapping[str, int]  # evening → new margin
    extra_min: int
    cases: int


@dataclass(frozen=True)
class Speed:
    """Offer: plan `kind` at `share` of its length."""

    kind: str
    share: float
    cases: int


@dataclass(frozen=True)
class Summary:
    hows: list[How]
    nights: LaterNights | None
    speeds: list[Speed]
    counts: Mapping[str, int]  # way → finishes that used it


def merged(spans: Iterable[Span]) -> list[Span]:
    """The spans as disjoint, sorted runs: a minute worked twice counts once."""
    out: list[Span] = []
    for lo, hi in sorted(s for s in spans if s[1] > s[0]):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def overlap(spans: Sequence[Span], lo: int, hi: int) -> int:
    return sum(max(0, min(b, hi) - max(a, lo)) for a, b in spans)


def read(finish: Finish, nights: Sequence[Night], events: Sequence[Event]) -> How:
    """Where `finish`'s time came from. A night's evening half runs to its midpoint, its morning half from it."""
    worked = merged(finish.worked)
    evening = morning = 0
    reach: dict[str, int] = {}
    for night in nights:
        middle = (night.start + night.end) // 2
        late = overlap(worked, night.start, middle)
        evening += late
        morning += overlap(worked, middle, night.end)
        if late:
            last = max(min(b, middle) for a, b in worked if a < middle and b > night.start)
            reach[night.evening] = max(reach.get(night.evening, 0), last - night.start)
    through = [(e.title, overlap(worked, e.start, e.end)) for e in events]
    speed = (
        finish.actual_min / finish.planned_min
        if finish.actual_min is not None and finish.planned_min
        else None
    )  # fmt: skip
    return How(
        finish=finish,
        speed=speed,
        evening_min=evening,
        morning_min=morning,
        event_min=sum(m for _, m in through),
        reach=reach,
        events=tuple(dict.fromkeys(t for t, m in through if m >= MIN_MIN)),
    )


def summarize(hows: Sequence[How], margins: Mapping[str, int]) -> Summary:
    """The finishes' patterns and what each would change; `margins` are each evening's margin now."""
    counts: dict[str, int] = {}
    for how in hows:
        for way in how.ways:
            counts[way] = counts.get(way, 0) + 1
    return Summary(list(hows), later_nights(hows, margins), speeds(hows), counts)


def later_nights(hows: Sequence[How], margins: Mapping[str, int]) -> LaterNights | None:
    """Once `MIN_CASES` finishes reached into nights' evenings: those evenings' margins, grown by the median reach
    rounded up to a quarter hour (at most `MARGIN_MAX`). None when no evening could grow."""
    used = [h for h in hows if "nights" in h.ways]
    if len(used) < MIN_CASES:
        return None
    reaches = [m for h in used for m in h.reach.values() if m >= MIN_MIN]
    if not reaches:
        return None
    extra = math.ceil(median(reaches) / QUARTER) * QUARTER
    evenings = {e for h in used for e, m in h.reach.items() if m >= MIN_MIN}
    grown = {
        e: min(MARGIN_MAX, margins.get(e, 0) + extra)
        for e in WEEKDAYS
        if e in evenings and margins.get(e, 0) < MARGIN_MAX
    }  # fmt: skip
    return LaterNights(grown, extra, len(used)) if grown else None


def speeds(hows: Sequence[How]) -> list[Speed]:
    """Each kind finished faster in `MIN_CASES` timed finishes of lengths it can scale, by its median share
    rounded up to a twentieth (never under `SHARE_FLOOR`), the most cases first."""
    by_kind: dict[str, list[float]] = {}
    for how in hows:
        f = how.finish
        if f.kind and f.scalable and how.speed is not None:
            by_kind.setdefault(f.kind, []).append(how.speed)
    out = []
    for kind, shares in by_kind.items():
        middle = median(shares)
        if len(shares) >= MIN_CASES and middle < FASTER:
            share = max(SHARE_FLOOR, math.ceil(round(middle * 20, 6)) / 20)
            out.append(Speed(kind, share, len(shares)))
    return sorted(out, key=lambda s: (-s.cases, s.kind))
