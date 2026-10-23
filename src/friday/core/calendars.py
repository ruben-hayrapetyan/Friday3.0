"""Calendar events as personal's Mac app saw them (COMBINED.md 17, 19, 28, 59): categories that colour an event by its
title, a filter for the ones you'd rather not see (office hours), and which events count as busy when planning.

Categories come from Chroma's `categories.json` (imported once) and are edited in Settings. An event is left out of
planning, the way personal's Busy.swift left it out, when it is only a reminder that something is due, marked free,
filtered (unless you count those), or on a calendar of room bookings (unless you count that calendar). Pure: no I/O.
"""

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
    pattern: str  # a regular expression, matched against the title without regard to case
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
ROOMS = re.compile(r"\b(rooms?|bookings?|reservations?)\b", re.IGNORECASE)
REASONS = ("calendar", "reminder", "free", "filtered")


@lru_cache(maxsize=256)
def compiled(pattern: str) -> re.Pattern[str] | None:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return None  # a broken rule matches nothing rather than breaking every view


def category_of(title: str, settings: CategorySettings) -> Category | None:
    """The first category whose pattern finds the title, in the order they're listed."""
    for category in settings.categories:
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
    if REMINDER.search(title) and not busy.count_reminders:
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
