"""Calendar events as personal's Mac app saw them (COMBINED.md 17, 19, 28, 59): categories that colour an event by its
title, a filter for the ones you'd rather not see (office hours), and which events count as busy when planning.

Categories come from Chroma's `categories.json` (imported once) and are edited in Settings. An event is left out of
planning, the way personal's Busy.swift left it out, when it is only a reminder that something is due, marked free,
filtered (unless you count those), or on a calendar of room bookings (unless you count that calendar). Pure: no I/O.
"""

import colorsys
import re
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from friday.core.items import PIGMENTS


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Category(Model):
    name: str
    slug: str = ""
    color: str  # one of PIGMENTS
    pattern: str = ""  # always this category: a regular expression found in the title, without regard to case
    note: str | None = None


class EventFilter(Model):
    label: str  # what the toggle says, e.g. "TA & Advising Hours"
    pattern: str
    except_: tuple[str, ...] = Field((), alias="except")  # category slugs it never hides

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class CategorySettings(Model):
    categories: tuple[Category, ...] = ()
    filter: EventFilter | None = None


class BusySettings(Model):
    count_filtered: bool = False  # filtered events (office hours) block time after all
    count_free: bool = False  # events marked free block time after all
    count_reminders: bool = False  # "Problem set 8 due" blocks time after all
    calendars: dict[str, bool] = Field(default_factory=dict)  # a calendar's name -> counted; else rooms aren't


class CalendarLook(Model):
    colors: dict[str, str] = Field(default_factory=dict)  # a calendar's name -> its pigment
    toolbar: tuple[str, ...] = ()  # calendars with a show/hide button in the title row (personal's, ⌥⌘1–9)


REMINDER = re.compile(r"\b(due|deadline)\b", re.IGNORECASE)
# A meeting about a deadline is still a meeting: "Thesis deadline check-in with advisor" takes the hour (26 Oct).
MEETING = re.compile(
    r"\b(with|meeting|meet|check-?in|call|session|office hours|review|interview|talk|chat|sync|1:1|appointment"
    r"|class|lecture|lab|discussion|seminar|workshop|presentation|defense)\b",
    re.IGNORECASE,
)
ROOMS = re.compile(r"\b(rooms?|bookings?|reservations?)\b", re.IGNORECASE)
REASONS = ("calendar", "reminder", "free", "filtered")


@lru_cache(maxsize=256)
def compiled(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None  # a broken rule matches nothing rather than breaking every view


def category_of(title: str, settings: CategorySettings) -> Category | None:
    """The first category whose pattern finds the title, in the order they're listed. A pattern is optional since
    clues and Claude place the rest (commands/categories.py): an empty one finds nothing, not everything."""
    for category in settings.categories:
        if not category.pattern.strip():
            continue
        found = compiled(category.pattern)
        if found is not None and found.search(title):
            return category
    return None


def is_filtered(title: str, settings: CategorySettings) -> bool:
    """Whether the filter hides the event: its pattern finds the title and no category it spares owns it."""
    rule = settings.filter
    found = compiled(rule.pattern) if rule else None
    if rule is None or found is None or not found.search(title):
        return False
    category = category_of(title, settings)
    return category is None or category.slug not in rule.except_


# The paints, as the website shows them on paper (web/src/lib/pigments.ts), for matching a calendar's own colour.
PIGMENT_HEX = {"red": "#c2402d", "orange": "#ce7c22", "yellow": "#be9a1f", "green": "#34877a", "sapgreen": "#74a03a",
               "blue": "#2a6c9c", "purple": "#4a48a0", "pink": "#a63f76", "graphite": "#6e7a8c",
               "violet": "#8a4cb5"}  # fmt: skip


# Paints that already say something: schoolwork's green and meals' yellow (web/src/theme/LookProvider.tsx KIND_PAINT),
# and red, kept for now and overdue. A calendar's own colour is never matched to one (27 Oct: the Cornell calendar's
# light cyan came out schoolwork green, so an event on it looked like an assignment). You can still choose one for a
# calendar in Settings → Calendars.
SAYS_SOMETHING = ("green", "yellow", "red")


def nearest_pigment(color: str | None) -> str | None:
    """The paint nearest a calendar's own colour ("#0088ff" is Cerulean), by hue, of those that don't already mean
    something; a grey one is Payne's Grey."""
    if not color or not re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
        return None
    hue, sat = hue_of(color)
    if sat < 0.18:
        return "graphite"
    choices = {name: hue_of(value) for name, value in PIGMENT_HEX.items() if name not in ("graphite", *SAYS_SOMETHING)}
    return min(choices, key=lambda name: min(abs(choices[name][0] - hue), 360 - abs(choices[name][0] - hue)))


def hue_of(color: str) -> tuple[float, float]:
    r, g, b = (int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s


def calendar_counts(calendar: str | None, busy: BusySettings) -> bool:
    """Whether a calendar's events block time: as you said, else all but calendars of room bookings."""
    if calendar is None:
        return True
    if calendar in busy.calendars:
        return busy.calendars[calendar]
    return ROOMS.search(calendar) is None


def left_out(
    title: str, calendar: str | None, free: bool, categories: CategorySettings, busy: BusySettings
) -> str | None:
    """Why an event doesn't count as busy (one of REASONS), or None when it does."""
    if not calendar_counts(calendar, busy):
        return "calendar"
    if REMINDER.search(title) and not MEETING.search(title) and not busy.count_reminders:
        return "reminder"
    if free and not busy.count_free:
        return "free"
    if is_filtered(title, categories) and not busy.count_filtered:
        return "filtered"
    return None


def check_colors(settings: CategorySettings | CalendarLook) -> None:
    if isinstance(settings, CalendarLook):
        wrong = [name for name, color in settings.colors.items() if color not in PIGMENTS]
        if wrong:
            raise ValueError(f"calendar_look: {wrong[0]}'s color must be one of {', '.join(PIGMENTS)}")
        return
    for category in settings.categories:
        if category.color not in PIGMENTS:
            raise ValueError(f"categories: {category.name}'s color must be one of {', '.join(PIGMENTS)}")


# How much an event needs attending, by its title alone (personal's events.py fallback; COMBINED.md 56): what the AI's
# rating falls back on, and what triage reads when nothing was rated yet.
_REQUIRED = re.compile(
    r"\b(lec(ture)?|lab|disc(ussion)?|recitation|section|seminar|exam|prelim|midterm|quiz|final|interview|"
    r"appointment|shift|class)\b",
    re.IGNORECASE,
)
_OPTIONAL = re.compile(
    r"\b(office hours|drop.?in|help session|talk|info session|social|networking|expo|open|conversation hours|poker|"
    r"ping ?pong|table tennis|chess|game|party)\b",
    re.IGNORECASE,
)


def rating_key(title: str) -> str:
    """One rating per series: case, spacing and trailing numbers don't make a new event."""
    return re.sub(r"\s+", " ", re.sub(r"\s*#?\d+\s*$", "", title.strip().lower()))


def fallback_level(title: str) -> str:
    if _REQUIRED.search(title):
        return "required"
    return "optional" if _OPTIONAL.search(title) else "likely"


def event_key(external_id: str) -> str:
    """The event's own id, from Chroma's key or the id a calendar sync keeps (`<calendar>:<event>@<start>`)."""
    return external_id.split("@")[0].split("/RID=")[0].split(":")[-1]
